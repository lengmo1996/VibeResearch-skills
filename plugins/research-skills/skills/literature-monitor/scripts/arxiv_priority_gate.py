#!/usr/bin/env python3
"""Machine-wide priority coordination for arXiv MCP and digest HTTP calls."""

from __future__ import annotations

import json
import os
import tempfile
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator


STATE_SCHEMA_VERSION = 1
STATE_FILENAME = "state.json"
LOCK_FILENAME = "gate.lock"
DEFAULT_MIN_INTERVAL_SECONDS = 5
DEFAULT_RATE_LIMIT_COOLDOWN_SECONDS = 60
DEFAULT_POST_DIGEST_COOLDOWN_SECONDS = 60
DEFAULT_CALL_LEASE_SECONDS = 6 * 60 * 60
DEFAULT_DIGEST_SESSION_SECONDS = 4 * 60 * 60
DEFAULT_DIGEST_IDLE_SECONDS = 10 * 60
DEFAULT_QUEUE_ENTRY_SECONDS = 8 * 60 * 60


class PriorityGateError(RuntimeError):
    """Base error for priority-gate failures."""


class PriorityGateTimeout(PriorityGateError):
    """Raised when a queued request cannot acquire its lease in time."""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _aware_utc(value: datetime, label: str) -> datetime:
    if value.tzinfo is None:
        raise PriorityGateError(f"{label} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _timestamp(value: datetime) -> str:
    return (
        _aware_utc(value, "timestamp")
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _parse_timestamp(value: Any, label: str) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise PriorityGateError(f"invalid {label}: {value}") from exc
    return _aware_utc(parsed, label)


def _atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        text=True,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


@contextmanager
def _exclusive_lock(path: Path, timeout_seconds: float = 10.0) -> Iterator[None]:
    if timeout_seconds < 0:
        raise PriorityGateError("lock timeout must be non-negative")
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b", buffering=0)
    handle.seek(0, os.SEEK_END)
    if handle.tell() == 0:
        handle.write(b"\0")
    deadline = time.monotonic() + timeout_seconds
    locked = False
    try:
        while not locked:
            try:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
            except OSError as exc:
                if time.monotonic() >= deadline:
                    raise PriorityGateTimeout(
                        f"timed out acquiring priority-gate lock: {path}"
                    ) from exc
                time.sleep(0.05)
        yield
    finally:
        if locked:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def _default_state() -> dict[str, Any]:
    return {
        "schema_version": STATE_SCHEMA_VERSION,
        "active_call": None,
        "active_digest": None,
        "digest_waiters": [],
        "normal_waiters": [],
        "digest_call_waiters": [],
        "previous_started_at": None,
        "rate_limited_at": None,
        "normal_not_before": None,
        "last_digest_call_finished_at": None,
        "last_digest_expiry_reason": None,
    }


def _read_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return _default_state()
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PriorityGateError(f"invalid priority-gate state {path}: {exc}") from exc
    if not isinstance(state, dict) or state.get("schema_version") != STATE_SCHEMA_VERSION:
        raise PriorityGateError(f"unsupported priority-gate state: {path}")
    defaults = _default_state()
    for key, value in defaults.items():
        state.setdefault(key, value)
    for queue_name in ("digest_waiters", "normal_waiters", "digest_call_waiters"):
        if not isinstance(state[queue_name], list):
            raise PriorityGateError(f"{queue_name} must be an array")
    return state


def _pid_alive(pid: Any) -> bool:
    try:
        normalized = int(pid)
    except (TypeError, ValueError):
        return False
    if normalized <= 0:
        return False
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        process_query_limited_information = 0x1000
        synchronize = 0x00100000
        wait_object_0 = 0x00000000
        wait_timeout = 0x00000102
        error_access_denied = 5

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [
            wintypes.DWORD,
            wintypes.BOOL,
            wintypes.DWORD,
        ]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel32.WaitForSingleObject.restype = wintypes.DWORD
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL

        handle = kernel32.OpenProcess(
            process_query_limited_information | synchronize,
            False,
            normalized,
        )
        if not handle:
            return ctypes.get_last_error() == error_access_denied
        try:
            wait_result = kernel32.WaitForSingleObject(handle, 0)
            if wait_result == wait_object_0:
                return False
            if wait_result == wait_timeout:
                return True
            return True
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(normalized, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


class ArxivPriorityGate:
    """Crash-bounded, cross-process priority gate backed by two local files."""

    def __init__(
        self,
        root: Path,
        *,
        min_interval_seconds: int = DEFAULT_MIN_INTERVAL_SECONDS,
        rate_limit_cooldown_seconds: int = DEFAULT_RATE_LIMIT_COOLDOWN_SECONDS,
        post_digest_cooldown_seconds: int = DEFAULT_POST_DIGEST_COOLDOWN_SECONDS,
        call_lease_seconds: int = DEFAULT_CALL_LEASE_SECONDS,
        digest_session_seconds: int = DEFAULT_DIGEST_SESSION_SECONDS,
        digest_idle_seconds: int = DEFAULT_DIGEST_IDLE_SECONDS,
        queue_entry_seconds: int = DEFAULT_QUEUE_ENTRY_SECONDS,
    ) -> None:
        self.root = Path(root).resolve()
        self.state_path = self.root / STATE_FILENAME
        self.lock_path = self.root / LOCK_FILENAME
        values = {
            "min_interval_seconds": min_interval_seconds,
            "rate_limit_cooldown_seconds": rate_limit_cooldown_seconds,
            "post_digest_cooldown_seconds": post_digest_cooldown_seconds,
            "call_lease_seconds": call_lease_seconds,
            "digest_session_seconds": digest_session_seconds,
            "digest_idle_seconds": digest_idle_seconds,
            "queue_entry_seconds": queue_entry_seconds,
        }
        for label, value in values.items():
            if not isinstance(value, int) or value <= 0:
                raise PriorityGateError(f"{label} must be a positive integer")
        self.min_interval_seconds = min_interval_seconds
        self.rate_limit_cooldown_seconds = rate_limit_cooldown_seconds
        self.post_digest_cooldown_seconds = post_digest_cooldown_seconds
        self.call_lease_seconds = call_lease_seconds
        self.digest_session_seconds = digest_session_seconds
        self.digest_idle_seconds = digest_idle_seconds
        self.queue_entry_seconds = queue_entry_seconds

    def _cleanup(self, state: dict[str, Any], now: datetime) -> bool:
        changed = False
        active_call = state.get("active_call")
        if active_call is not None:
            expires_at = _parse_timestamp(active_call.get("expires_at"), "active_call.expires_at")
            if expires_at is None or expires_at <= now or not _pid_alive(active_call.get("pid")):
                if active_call.get("role") == "digest":
                    state["last_digest_call_finished_at"] = _timestamp(now)
                state["active_call"] = None
                changed = True

        active_digest = state.get("active_digest")
        if active_digest is not None:
            expires_at = _parse_timestamp(
                active_digest.get("expires_at"), "active_digest.expires_at"
            )
            last_activity = _parse_timestamp(
                state.get("last_digest_call_finished_at"),
                "last_digest_call_finished_at",
            )
            acquired_at = _parse_timestamp(
                active_digest.get("acquired_at"), "active_digest.acquired_at"
            )
            idle_expires_at = _parse_timestamp(
                active_digest.get("idle_expires_at"),
                "active_digest.idle_expires_at",
            )
            if idle_expires_at is None:
                idle_candidates = [
                    value for value in (acquired_at, last_activity) if value is not None
                ]
                idle_from = max(idle_candidates) if idle_candidates else None
                if idle_from is not None:
                    idle_expires_at = idle_from + timedelta(
                        seconds=self.digest_idle_seconds
                    )
                    active_digest["idle_expires_at"] = _timestamp(idle_expires_at)
                    changed = True
            # A digest session belongs to the stable run ID and opaque token rather
            # than to one MCP server process. Codex may replace the stdio server
            # between automatic continuations. Preserve that behavior while calls
            # continue, but recover an orphaned session after a bounded idle period
            # instead of blocking the machine-wide queue until the four-hour hard
            # limit. Never apply the idle expiry underneath an active digest call.
            hard_expired = expires_at is None or expires_at <= now
            idle_expired = (
                state.get("active_call") is None
                and idle_expires_at is not None
                and idle_expires_at <= now
            )
            if hard_expired or idle_expired:
                state["active_digest"] = None
                state["last_digest_expiry_reason"] = (
                    "hard_timeout" if hard_expired else "idle_timeout"
                )
                cooldown_from = last_activity or acquired_at
                if cooldown_from is not None:
                    candidate = cooldown_from + timedelta(
                        seconds=self.post_digest_cooldown_seconds
                    )
                    current = _parse_timestamp(
                        state.get("normal_not_before"), "normal_not_before"
                    )
                    if current is None or candidate > current:
                        state["normal_not_before"] = _timestamp(candidate)
                changed = True

        for queue_name in ("digest_waiters", "normal_waiters", "digest_call_waiters"):
            retained = []
            for entry in state[queue_name]:
                expires_at = _parse_timestamp(
                    entry.get("expires_at"), f"{queue_name}.expires_at"
                )
                if (
                    expires_at is not None
                    and expires_at > now
                    and _pid_alive(entry.get("pid"))
                ):
                    retained.append(entry)
            if len(retained) != len(state[queue_name]):
                state[queue_name] = retained
                changed = True
        return changed

    def _not_before(self, state: dict[str, Any], role: str) -> datetime | None:
        candidates: list[datetime] = []
        previous = _parse_timestamp(state.get("previous_started_at"), "previous_started_at")
        if previous is not None:
            candidates.append(previous + timedelta(seconds=self.min_interval_seconds))
        limited = _parse_timestamp(state.get("rate_limited_at"), "rate_limited_at")
        if limited is not None:
            candidates.append(
                limited + timedelta(seconds=self.rate_limit_cooldown_seconds)
            )
        if role == "normal":
            normal_not_before = _parse_timestamp(
                state.get("normal_not_before"), "normal_not_before"
            )
            if normal_not_before is not None:
                candidates.append(normal_not_before)
        return max(candidates) if candidates else None

    def _mutate(self, operation: Any, now: datetime | None = None) -> Any:
        current = _aware_utc(now or utc_now(), "now")
        self.root.mkdir(parents=True, exist_ok=True)
        with _exclusive_lock(self.lock_path):
            state = _read_state(self.state_path)
            changed = self._cleanup(state, current)
            result, operation_changed = operation(state, current)
            if changed or operation_changed:
                state["updated_at"] = _timestamp(current)
                _atomic_write_json(self.state_path, state)
            return result

    def begin_digest_session(
        self,
        run_id: str,
        *,
        wait_timeout_seconds: float = 900.0,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        normalized_run_id = str(run_id).strip()
        if not normalized_run_id:
            raise PriorityGateError("run_id must be non-empty")
        waiter_token = uuid.uuid4().hex
        deadline = time.monotonic() + wait_timeout_seconds
        fixed_now = now

        def attempt(state: dict[str, Any], current: datetime) -> tuple[dict[str, Any], bool]:
            active = state.get("active_digest")
            if active is not None and active.get("run_id") == normalized_run_id:
                changed = True
                if active.get("pid") != os.getpid():
                    active["pid"] = os.getpid()
                    active["resumed_at"] = _timestamp(current)
                active["idle_expires_at"] = _timestamp(
                    current + timedelta(seconds=self.digest_idle_seconds)
                )
                return (
                    {
                        "acquired": True,
                        "resumed": True,
                        "session_token": str(active["token"]),
                        "run_id": normalized_run_id,
                        "acquired_at": str(active["acquired_at"]),
                        "expires_at": str(active["expires_at"]),
                        "idle_expires_at": str(active["idle_expires_at"]),
                    },
                    changed,
                )
            existing = next(
                (
                    item
                    for item in state["digest_waiters"]
                    if item.get("token") == waiter_token
                ),
                None,
            )
            changed = False
            if existing is None:
                state["digest_waiters"].append(
                    {
                        "token": waiter_token,
                        "run_id": normalized_run_id,
                        "pid": os.getpid(),
                        "queued_at": _timestamp(current),
                        "expires_at": _timestamp(
                            current + timedelta(seconds=self.queue_entry_seconds)
                        ),
                    }
                )
                changed = True
            is_head = state["digest_waiters"][0]["token"] == waiter_token
            if is_head and state.get("active_digest") is None and state.get("active_call") is None:
                session_token = uuid.uuid4().hex
                state["digest_waiters"] = [
                    item
                    for item in state["digest_waiters"]
                    if item.get("token") != waiter_token
                ]
                state["active_digest"] = {
                    "token": session_token,
                    "run_id": normalized_run_id,
                    "pid": os.getpid(),
                    "acquired_at": _timestamp(current),
                    "expires_at": _timestamp(
                        current + timedelta(seconds=self.digest_session_seconds)
                    ),
                    "idle_expires_at": _timestamp(
                        current + timedelta(seconds=self.digest_idle_seconds)
                    ),
                }
                state["last_digest_expiry_reason"] = None
                return (
                    {
                        "acquired": True,
                        "resumed": False,
                        "session_token": session_token,
                        "run_id": normalized_run_id,
                        "acquired_at": _timestamp(current),
                        "expires_at": state["active_digest"]["expires_at"],
                        "idle_expires_at": state["active_digest"][
                            "idle_expires_at"
                        ],
                    },
                    True,
                )
            return (
                {
                    "acquired": False,
                    "reason": (
                        "active_call"
                        if state.get("active_call") is not None
                        else "digest_session_or_waiter"
                    ),
                },
                changed,
            )

        while True:
            result = self._mutate(attempt, fixed_now)
            if result["acquired"]:
                return result
            if fixed_now is not None or time.monotonic() >= deadline:
                self._drop_waiter("digest_waiters", waiter_token)
                raise PriorityGateTimeout("timed out waiting for digest priority session")
            time.sleep(0.1)

    def require_digest_session(
        self,
        session_token: str,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Validate a private token and return only its bound, non-secret run identity."""

        normalized = str(session_token).strip()
        if not normalized:
            raise PriorityGateError("session_token must be non-empty")

        def operation(state: dict[str, Any], current: datetime) -> tuple[dict[str, Any], bool]:
            active = state.get("active_digest")
            if active is None or active.get("token") != normalized:
                raise PriorityGateError("session token does not own the active digest")
            run_id = str(active.get("run_id", "")).strip()
            if not run_id:
                raise PriorityGateError("active digest session is missing its run ID")
            active["idle_expires_at"] = _timestamp(
                current + timedelta(seconds=self.digest_idle_seconds)
            )
            return ({"run_id": run_id}, True)

        return self._mutate(operation, now)

    def end_digest_session(
        self,
        session_token: str,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        normalized = str(session_token).strip()
        if not normalized:
            raise PriorityGateError("session_token must be non-empty")

        def operation(state: dict[str, Any], current: datetime) -> tuple[dict[str, Any], bool]:
            active = state.get("active_digest")
            if active is None or active.get("token") != normalized:
                raise PriorityGateError("session token does not own the active digest")
            active_call = state.get("active_call")
            if active_call is not None and active_call.get("digest_token") == normalized:
                raise PriorityGateError("cannot end digest session while its call is active")
            state["active_digest"] = None
            not_before = current + timedelta(seconds=self.post_digest_cooldown_seconds)
            existing = _parse_timestamp(
                state.get("normal_not_before"), "normal_not_before"
            )
            if existing is not None and existing > not_before:
                not_before = existing
            state["normal_not_before"] = _timestamp(not_before)
            state["last_digest_released_at"] = _timestamp(current)
            return (
                {
                    "released": True,
                    "released_at": _timestamp(current),
                    "normal_not_before": _timestamp(not_before),
                },
                True,
            )

        return self._mutate(operation, now)

    def acquire_call(
        self,
        role: str,
        owner: str,
        *,
        digest_token: str | None = None,
        wait_timeout_seconds: float = 21600.0,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if role not in {"normal", "digest"}:
            raise PriorityGateError(f"unsupported role: {role}")
        normalized_owner = str(owner).strip()
        if not normalized_owner:
            raise PriorityGateError("owner must be non-empty")
        request_token = uuid.uuid4().hex
        queue_name = "normal_waiters" if role == "normal" else "digest_call_waiters"
        deadline = time.monotonic() + wait_timeout_seconds
        fixed_now = now

        def attempt(state: dict[str, Any], current: datetime) -> tuple[dict[str, Any], bool]:
            changed = False
            if not any(item.get("token") == request_token for item in state[queue_name]):
                state[queue_name].append(
                    {
                        "token": request_token,
                        "owner": normalized_owner,
                        "pid": os.getpid(),
                        "digest_token": digest_token,
                        "queued_at": _timestamp(current),
                        "expires_at": _timestamp(
                            current + timedelta(seconds=self.queue_entry_seconds)
                        ),
                    }
                )
                changed = True

            if state[queue_name][0].get("token") != request_token:
                return ({"acquired": False, "reason": "fifo_wait"}, changed)
            if state.get("active_call") is not None:
                return ({"acquired": False, "reason": "active_call"}, changed)

            if role == "normal":
                if state.get("active_digest") is not None or state["digest_waiters"]:
                    return ({"acquired": False, "reason": "digest_priority"}, changed)
            else:
                active_digest = state.get("active_digest")
                if (
                    active_digest is None
                    or not digest_token
                    or active_digest.get("token") != digest_token
                ):
                    raise PriorityGateError(
                        "digest call requires the active digest session token"
                    )
                active_digest["idle_expires_at"] = _timestamp(
                    current + timedelta(seconds=self.digest_idle_seconds)
                )
                changed = True

            not_before = self._not_before(state, role)
            if not_before is not None and not_before > current:
                return (
                    {
                        "acquired": False,
                        "reason": "rate_limit_delay",
                        "not_before": _timestamp(not_before),
                    },
                    changed,
                )

            call_token = uuid.uuid4().hex
            state[queue_name] = [
                item
                for item in state[queue_name]
                if item.get("token") != request_token
            ]
            state["active_call"] = {
                "token": call_token,
                "role": role,
                "owner": normalized_owner,
                "pid": os.getpid(),
                "digest_token": digest_token,
                "started_at": _timestamp(current),
                "expires_at": _timestamp(
                    current + timedelta(seconds=self.call_lease_seconds)
                ),
            }
            state["previous_started_at"] = _timestamp(current)
            return (
                {
                    "acquired": True,
                    "token": call_token,
                    "role": role,
                    "owner": normalized_owner,
                    "started_at": _timestamp(current),
                },
                True,
            )

        while True:
            result = self._mutate(attempt, fixed_now)
            if result["acquired"]:
                return result
            if fixed_now is not None or time.monotonic() >= deadline:
                self._drop_waiter(queue_name, request_token)
                raise PriorityGateTimeout(
                    f"timed out waiting for {role} arXiv call lease"
                )
            time.sleep(0.1)

    def release_call(
        self,
        call_token: str,
        *,
        rate_limited: bool = False,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        normalized = str(call_token).strip()
        if not normalized:
            raise PriorityGateError("call token must be non-empty")

        def operation(state: dict[str, Any], current: datetime) -> tuple[dict[str, Any], bool]:
            active = state.get("active_call")
            if active is None or active.get("token") != normalized:
                raise PriorityGateError("call token does not own the active call")
            role = active.get("role")
            state["active_call"] = None
            state["last_call_finished_at"] = _timestamp(current)
            if role == "digest":
                state["last_digest_call_finished_at"] = _timestamp(current)
                active_digest = state.get("active_digest")
                if active_digest is not None:
                    active_digest["idle_expires_at"] = _timestamp(
                        current + timedelta(seconds=self.digest_idle_seconds)
                    )
            if rate_limited:
                state["rate_limited_at"] = _timestamp(current)
            return (
                {
                    "released": True,
                    "role": role,
                    "rate_limited": rate_limited,
                    "released_at": _timestamp(current),
                },
                True,
            )

        return self._mutate(operation, now)

    def _drop_waiter(self, queue_name: str, token: str) -> None:
        def operation(state: dict[str, Any], current: datetime) -> tuple[None, bool]:
            retained = [
                item for item in state[queue_name] if item.get("token") != token
            ]
            changed = len(retained) != len(state[queue_name])
            state[queue_name] = retained
            return None, changed

        self._mutate(operation)

    def status(self, *, now: datetime | None = None) -> dict[str, Any]:
        def operation(state: dict[str, Any], current: datetime) -> tuple[dict[str, Any], bool]:
            active_digest = state.get("active_digest")
            active_call = state.get("active_call")
            return (
                {
                    "schema_version": state["schema_version"],
                    "active_digest": (
                        {
                            "run_id": active_digest.get("run_id"),
                            "pid": active_digest.get("pid"),
                            "acquired_at": active_digest.get("acquired_at"),
                            "expires_at": active_digest.get("expires_at"),
                            "idle_expires_at": active_digest.get("idle_expires_at"),
                        }
                        if active_digest
                        else None
                    ),
                    "active_call": (
                        {
                            "role": active_call.get("role"),
                            "owner": active_call.get("owner"),
                            "pid": active_call.get("pid"),
                            "started_at": active_call.get("started_at"),
                            "expires_at": active_call.get("expires_at"),
                        }
                        if active_call
                        else None
                    ),
                    "digest_waiter_count": len(state["digest_waiters"]),
                    "normal_waiter_count": len(state["normal_waiters"]),
                    "digest_call_waiter_count": len(state["digest_call_waiters"]),
                    "previous_started_at": state.get("previous_started_at"),
                    "rate_limited_at": state.get("rate_limited_at"),
                    "normal_not_before": state.get("normal_not_before"),
                    "last_digest_expiry_reason": state.get(
                        "last_digest_expiry_reason"
                    ),
                    "checked_at": _timestamp(current),
                },
                False,
            )

        return self._mutate(operation, now)
