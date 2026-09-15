#!/usr/bin/env python3
"""Process-safe HTTP client for every arXiv caller in this repository.

All production arXiv network traffic must pass through this module.  The
cross-process lock intentionally covers cache lookup, throttling, retries, the
HTTP exchange, and cache publication.  That makes request spacing and cache
stampede prevention global across independently launched skills.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from contextlib import contextmanager
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping

ARXIV_API_URL = "https://export.arxiv.org/api/query"
ARXIV_EXPORT_BASE_URL = "https://export.arxiv.org"
ARXIV_USER_AGENT = "VibeResearch-ArxivClient/1.0"
ARXIV_STATE_ENV = "VIBE_RESEARCH_ARXIV_STATE_DIR"

DEFAULT_MIN_INTERVAL_SECONDS = 3.0
DEFAULT_LOCK_TIMEOUT_SECONDS = 60.0
DEFAULT_REQUEST_TIMEOUT_SECONDS = 30.0
DEFAULT_CACHE_TTL_SECONDS = 6 * 60 * 60
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_BASE_SECONDS = 2.0
DEFAULT_BACKOFF_CAP_SECONDS = 60.0
RETRYABLE_HTTP_STATUSES = frozenset({429, 503})


class ArxivClientError(RuntimeError):
    """Base error for centralized arXiv client failures."""


class ArxivLockTimeout(ArxivClientError, TimeoutError):
    """The global arXiv lock could not be acquired before its deadline."""


class ArxivUnavailable(ArxivClientError):
    """The arXiv service or transport was unavailable."""


class ArxivHTTPError(ArxivUnavailable):
    """An arXiv HTTP response remained unsuccessful after bounded retries."""

    def __init__(
        self,
        status: int,
        detail: str,
        *,
        body: bytes = b"",
        attempts: int = 1,
    ) -> None:
        super().__init__(f"arXiv HTTP {status}: {detail}")
        self.status = status
        self.detail = detail
        self.body = body
        self.attempts = attempts


@dataclass(frozen=True)
class ArxivResponse:
    body: bytes
    status: int
    headers: dict[str, str]
    from_cache: bool
    attempts: int


def default_state_dir() -> Path:
    """Return the machine-local state directory shared by every skill process."""

    configured = os.environ.get(ARXIV_STATE_ENV)
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path(tempfile.gettempdir()) / "vibe-research-arxiv-client").resolve()


def _ensure_lock_byte(handle: Any) -> None:
    handle.seek(0, os.SEEK_END)
    if handle.tell() == 0:
        handle.write(b"\0")
        handle.flush()
    handle.seek(0)


@contextmanager
def file_lock(
    path: str | Path,
    *,
    timeout_seconds: float = DEFAULT_LOCK_TIMEOUT_SECONDS,
    poll_interval_seconds: float = 0.05,
) -> Iterator[None]:
    """Acquire an OS-backed exclusive file lock and always release it.

    The lock file is persistent; the operating-system lock is not.  If a
    process exits or crashes, the OS releases the lock when its descriptor is
    closed.  A bounded polling loop prevents an indefinitely wedged caller.
    """

    if timeout_seconds < 0:
        raise ValueError("lock timeout must be non-negative")
    if poll_interval_seconds <= 0:
        raise ValueError("lock poll interval must be positive")

    lock_path = Path(path).resolve()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+b")
    acquired = False
    deadline = time.monotonic() + timeout_seconds
    try:
        _ensure_lock_byte(handle)
        while True:
            try:
                if os.name == "nt":
                    import msvcrt

                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                break
            except (BlockingIOError, OSError):
                if time.monotonic() >= deadline:
                    raise ArxivLockTimeout(
                        f"timed out after {timeout_seconds:.3f}s acquiring "
                        f"global arXiv lock: {lock_path}"
                    )
                time.sleep(
                    min(poll_interval_seconds, max(0.0, deadline - time.monotonic()))
                )
        yield
    finally:
        try:
            if acquired:
                if os.name == "nt":
                    import msvcrt

                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def build_query_url(
    parameters: Mapping[str, str | int],
    *,
    base_url: str = ARXIV_API_URL,
) -> str:
    return f"{base_url}?{urllib.parse.urlencode(parameters)}"


class ArxivClient:
    """Centralized cached, throttled, retrying arXiv HTTP client."""

    def __init__(
        self,
        *,
        state_dir: str | Path | None = None,
        min_interval_seconds: float = DEFAULT_MIN_INTERVAL_SECONDS,
        lock_timeout_seconds: float = DEFAULT_LOCK_TIMEOUT_SECONDS,
        request_timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
        cache_ttl_seconds: float = DEFAULT_CACHE_TTL_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        backoff_base_seconds: float = DEFAULT_BACKOFF_BASE_SECONDS,
        backoff_cap_seconds: float = DEFAULT_BACKOFF_CAP_SECONDS,
        user_agent: str = ARXIV_USER_AGENT,
        opener: Callable[..., Any] | None = None,
        sleeper: Callable[[float], None] | None = None,
        allow_non_arxiv_hosts: bool = False,
    ) -> None:
        if min_interval_seconds < 0:
            raise ValueError("minimum request interval must be non-negative")
        if lock_timeout_seconds < 0:
            raise ValueError("lock timeout must be non-negative")
        if request_timeout_seconds <= 0:
            raise ValueError("request timeout must be positive")
        if cache_ttl_seconds < 0:
            raise ValueError("cache TTL must be non-negative")
        if max_retries < 0:
            raise ValueError("max retries must be non-negative")
        if backoff_base_seconds < 0 or backoff_cap_seconds < 0:
            raise ValueError("backoff durations must be non-negative")

        self.state_dir = (
            Path(state_dir).expanduser().resolve()
            if state_dir is not None
            else default_state_dir()
        )
        self.min_interval_seconds = float(min_interval_seconds)
        self.lock_timeout_seconds = float(lock_timeout_seconds)
        self.request_timeout_seconds = float(request_timeout_seconds)
        self.cache_ttl_seconds = float(cache_ttl_seconds)
        self.max_retries = int(max_retries)
        self.backoff_base_seconds = float(backoff_base_seconds)
        self.backoff_cap_seconds = float(backoff_cap_seconds)
        self.user_agent = user_agent
        self.opener = opener
        self.sleeper = sleeper or time.sleep
        self.allow_non_arxiv_hosts = allow_non_arxiv_hosts

        self.lock_path = self.state_dir / "request.lock"
        self.throttle_state_path = self.state_dir / "throttle.json"
        self.cache_dir = self.state_dir / "cache"

    def _validate_url(self, url: str) -> None:
        parsed = urllib.parse.urlsplit(url)
        hostname = (parsed.hostname or "").lower()
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("arXiv URL must use http or https")
        if not self.allow_non_arxiv_hosts and not (
            hostname == "arxiv.org" or hostname.endswith(".arxiv.org")
        ):
            raise ValueError(f"central arXiv client refuses non-arXiv host: {hostname}")

    @staticmethod
    def _headers_dict(headers: Any) -> dict[str, str]:
        if headers is None:
            return {}
        if hasattr(headers, "items"):
            return {str(key).lower(): str(value) for key, value in headers.items()}
        return {}

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any] | None:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, UnicodeError, json.JSONDecodeError):
            return None
        return value if isinstance(value, dict) else None

    @staticmethod
    def _atomic_json_write(path: Path, value: Mapping[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        )
        temporary = Path(handle.name)
        try:
            with handle:
                json.dump(value, handle, sort_keys=True, separators=(",", ":"))
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass

    def _cache_path(self, url: str, headers: Mapping[str, str]) -> Path:
        vary = {
            key.lower(): value
            for key, value in headers.items()
            if key.lower() in {"accept"}
        }
        cache_identity = json.dumps(
            {"url": url, "vary": vary},
            sort_keys=True,
            separators=(",", ":"),
        )
        digest = hashlib.sha256(cache_identity.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{digest}.json"

    def _read_cache(
        self,
        url: str,
        headers: Mapping[str, str],
        *,
        now: float,
    ) -> ArxivResponse | None:
        entry = self._read_json(self._cache_path(url, headers))
        if not entry or entry.get("url") != url:
            return None
        expires_at = entry.get("expires_at")
        body_text = entry.get("body_base64")
        if not isinstance(expires_at, (int, float)) or expires_at <= now:
            return None
        if not isinstance(body_text, str):
            return None
        try:
            body = base64.b64decode(body_text.encode("ascii"), validate=True)
        except (ValueError, UnicodeError):
            return None
        cached_headers = entry.get("headers")
        return ArxivResponse(
            body=body,
            status=int(entry.get("status", 200)),
            headers=(
                {str(key): str(value) for key, value in cached_headers.items()}
                if isinstance(cached_headers, dict)
                else {}
            ),
            from_cache=True,
            attempts=0,
        )

    def _write_cache(
        self,
        url: str,
        request_headers: Mapping[str, str],
        response: ArxivResponse,
        *,
        ttl_seconds: float,
        now: float,
    ) -> None:
        self._atomic_json_write(
            self._cache_path(url, request_headers),
            {
                "url": url,
                "status": response.status,
                "headers": response.headers,
                "fetched_at": now,
                "expires_at": now + ttl_seconds,
                "body_base64": base64.b64encode(response.body).decode("ascii"),
            },
        )

    def _wait_for_global_slot(self) -> None:
        state = self._read_json(self.throttle_state_path) or {}
        previous = state.get("last_request_at")
        now = time.time()
        if isinstance(previous, (int, float)):
            delay = self.min_interval_seconds - (now - float(previous))
            if delay > 0:
                self.sleeper(delay)
        request_started_at = time.time()
        self._atomic_json_write(
            self.throttle_state_path,
            {
                "last_request_at": request_started_at,
                "pid": os.getpid(),
            },
        )

    def _retry_delay(self, attempt_index: int, headers: Mapping[str, str]) -> float:
        exponential = min(
            self.backoff_cap_seconds,
            self.backoff_base_seconds * (2**attempt_index),
        )
        retry_after = headers.get("retry-after")
        if retry_after:
            try:
                return max(exponential, min(self.backoff_cap_seconds, float(retry_after)))
            except ValueError:
                try:
                    parsed = parsedate_to_datetime(retry_after)
                    return max(
                        exponential,
                        min(self.backoff_cap_seconds, parsed.timestamp() - time.time()),
                    )
                except (TypeError, ValueError, OverflowError):
                    pass
        return max(0.0, exponential)

    def request(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        timeout_seconds: float | None = None,
        cache_ttl_seconds: float | None = None,
        use_cache: bool = True,
        max_retries: int | None = None,
        opener: Callable[..., Any] | None = None,
    ) -> ArxivResponse:
        """Perform one globally synchronized GET, with cache and bounded retry."""

        self._validate_url(url)
        timeout = (
            self.request_timeout_seconds
            if timeout_seconds is None
            else float(timeout_seconds)
        )
        if timeout <= 0:
            raise ValueError("request timeout must be positive")
        ttl = self.cache_ttl_seconds if cache_ttl_seconds is None else float(
            cache_ttl_seconds
        )
        if ttl < 0:
            raise ValueError("cache TTL must be non-negative")
        retry_count = self.max_retries if max_retries is None else int(max_retries)
        if retry_count < 0:
            raise ValueError("max retries must be non-negative")

        request_headers = {"User-Agent": self.user_agent}
        if headers:
            request_headers.update({str(key): str(value) for key, value in headers.items()})
        selected_opener = opener or self.opener or urllib.request.urlopen

        with file_lock(
            self.lock_path,
            timeout_seconds=self.lock_timeout_seconds,
        ):
            now = time.time()
            if use_cache and ttl > 0:
                cached = self._read_cache(url, request_headers, now=now)
                if cached is not None:
                    return cached

            attempts = 0
            while True:
                attempts += 1
                self._wait_for_global_slot()
                request = urllib.request.Request(
                    url,
                    headers=request_headers,
                    method="GET",
                )
                try:
                    with selected_opener(request, timeout=timeout) as raw_response:
                        status = int(getattr(raw_response, "status", 200))
                        body = raw_response.read()
                        response_headers = self._headers_dict(
                            getattr(raw_response, "headers", None)
                        )
                except urllib.error.HTTPError as exc:
                    try:
                        body = exc.read()
                    except Exception:
                        body = b""
                    response_headers = self._headers_dict(exc.headers)
                    status = int(exc.code)
                    detail = str(getattr(exc, "reason", exc))
                    try:
                        exc.close()
                    except Exception:
                        pass
                    if status in RETRYABLE_HTTP_STATUSES and attempts <= retry_count:
                        self.sleeper(self._retry_delay(attempts - 1, response_headers))
                        continue
                    raise ArxivHTTPError(
                        status,
                        detail,
                        body=body,
                        attempts=attempts,
                    ) from exc
                except (urllib.error.URLError, TimeoutError, OSError) as exc:
                    raise ArxivUnavailable(f"arXiv network error: {exc}") from exc
                except Exception as exc:
                    # Includes read-time HTTPException/IncompleteRead failures.
                    raise ArxivUnavailable(
                        f"arXiv response read failed: {exc}"
                    ) from exc

                if status in RETRYABLE_HTTP_STATUSES and attempts <= retry_count:
                    self.sleeper(self._retry_delay(attempts - 1, response_headers))
                    continue
                if status < 200 or status >= 300:
                    raise ArxivHTTPError(
                        status,
                        f"unexpected response status {status}",
                        body=body,
                        attempts=attempts,
                    )

                response = ArxivResponse(
                    body=body,
                    status=status,
                    headers=response_headers,
                    from_cache=False,
                    attempts=attempts,
                )
                if use_cache and ttl > 0:
                    self._write_cache(
                        url,
                        request_headers,
                        response,
                        ttl_seconds=ttl,
                        now=time.time(),
                    )
                return response

    def get_bytes(self, url: str, **kwargs: Any) -> bytes:
        return self.request(url, **kwargs).body

