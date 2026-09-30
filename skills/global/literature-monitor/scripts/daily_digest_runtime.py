#!/usr/bin/env python3
"""Deterministic runtime support for literature-monitor daily arXiv digests."""

from __future__ import annotations

import argparse
import copy
import hashlib
import html
import importlib.util
import json
import os
import re
import socket
import sys
import tempfile
import time
import uuid
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urlencode, urlparse
from urllib.request import getproxies, proxy_bypass, urlopen
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from arxiv_priority_gate import ArxivPriorityGate
import daily_digest_config as public_config


def _load_central_arxiv_module() -> Any:
    skill_root = Path(__file__).resolve().parent.parent
    candidates = (skill_root.parent / "_shared/arxiv_client.py", skill_root.parent.parent / "_shared/arxiv_client.py")
    for candidate in candidates:
        if not candidate.is_file():
            continue
        module_name = "_public_research_arxiv_client_" + hashlib.sha256(str(candidate.resolve()).encode()).hexdigest()[:12]
        spec = importlib.util.spec_from_file_location(module_name, candidate)
        if spec is None or spec.loader is None:
            continue
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module
    raise RuntimeError("Bundled public arXiv client is missing; keep the complete Skill package")


_CENTRAL_ARXIV = _load_central_arxiv_module()


SCHEMA_VERSION = 4
REVIEW_SCHEMA_VERSION = 3
LEGACY_SCHEMA_VERSIONS = (1, 2, 3)
LEGACY_DAILY_SCHEMA_VERSION = 2
DAILY_COVERAGE_POLICY = "configured-categories-summary-pdf-v4"
DEFAULT_REVIEW_CANDIDATE_LIMIT = 30
DEFAULT_REVIEW_PAGE_SIZE = 15
DEFAULT_REVIEW_PAGE_MAX_BYTES = 30_000
MAX_REVIEW_PAGES = 2
REVIEW_ABSTRACT_MAX_CHARS = 1_200
MAX_EMAIL_HTML_BYTES = 90_000
MAX_EMAIL_FOCUS = 10
MAX_EMAIL_WATCH = 10
FOCUS_SCORE_MINIMUM = 75
WATCH_SCORE_MINIMUM = 60
ARXIV_MCP_RATE_LIMIT_POLICY = {
    "max_in_flight": 1,
    "min_interval_seconds": 5,
    "rate_limit_cooldown_seconds": 60,
    "max_429_retries_per_call": 1,
    "max_transient_retries_per_call": 2,
    "transient_retry_delays_seconds": (15, 45),
    "lease_timeout_seconds": 240,
}
ARXIV_ANNOUNCEMENT_TIMEZONE = "America/New_York"
ARXIV_ANNOUNCEMENT_HOUR = 20
DAILY_DIGEST_REQUIRED_PYTHON_MODULES = ("reportlab", "pypdf")
ARXIV_STALE_REVALIDATION_DELAY_SECONDS = 15
ARXIV_STALE_REVALIDATION_RETRIES = 1
OFFICIAL_ARXIV_API_URL = _CENTRAL_ARXIV.ARXIV_API_URL
ARXIV_ANNOUNCEMENT_URL_TEMPLATE = "https://arxiv.org/list/{category}/new?show=2000"
ARXIV_CATCHUP_URL_TEMPLATE = (
    "https://arxiv.org/catchup/{category}/{announcement_date}?abs=True&page=1"
)
ARXIV_ABSTRACT_URL_TEMPLATE = "https://arxiv.org/abs/{identifier}"
OFFICIAL_ARXIV_API_TIMEOUT_SECONDS = 30
OFFICIAL_ARXIV_API_USER_AGENT = "VibeResearch-literature-monitor/0.1.0 (daily arXiv digest)"
ARXIV_RETRIEVAL_SOURCES = (
    "arxiv_announcement",
    "arxiv_mcp",
    "official_arxiv_api",
)
ARXIV_FAILURE_KINDS = (
    "rate_limited",
    "transient_transport",
    "sandbox_network_denied",
    "permanent_request",
    "response_integrity",
    "stale_announcement",
)
ARXIV_MCP_GATE_STATE = "arxiv-mcp-gate.json"
ARXIV_MCP_GATE_LOCK = "arxiv-mcp-gate.lock"
ARXIV_MCP_CALL_KINDS = (
    "category_inventory",
    "coverage_shard",
    "version_check",
    "download_paper",
    "read_paper",
)
ARXIV_MCP_REQUIRED_RETRIEVAL_KINDS = {
    "category_inventory",
    "coverage_shard",
}
ARXIV_MCP_FULL_TEXT_KINDS = {
    "download_paper",
    "read_paper",
}
TRACKED_CATEGORIES = ()
TOPIC_GROUPS = public_config.TOPIC_GROUPS
TOPIC_LABELS = dict(public_config.NEUTRAL_TOPIC_LABELS)
DIRECT_TOPIC_TERMS = ()
METHOD_TOPIC_TERMS = ()
TRANSFER_TOPIC_TERMS = ()
ARCHITECTURE_TERMS = ()
VISION_CONTEXT_TERMS = ()
DEFAULT_TOPIC_TIERS = {"A": (), "B": (), "C": ()}

_PUBLIC_DIGEST_CONFIG = None
CATEGORY_ORDER = TRACKED_CATEGORIES
REPORT_CATEGORY = None

def _require_public_configuration():
    if _PUBLIC_DIGEST_CONFIG is None:
        raise DigestValidationError("public_digest_not_configured: configure the user profile before daily operations")
    return _PUBLIC_DIGEST_CONFIG

def _validate_public_artifact_profile(value):
    config = _require_public_configuration()
    if (value.get("report_category") != config["report_category"]
            or value.get("public_profile_sha256") != config["_config_sha256"]
            or value.get("coverage_policy") != DAILY_COVERAGE_POLICY):
        raise DigestValidationError("public_digest_artifact_profile_mismatch: use this state root's original immutable profile and artifacts")

def _validate_public_report_accounting(digest):
    # The digest's count is a derived claim, not authority to omit a paper.
    config = _require_public_configuration()
    root = Path(config["digest_root"]).resolve()
    run_id = digest.get("run_id")
    if not isinstance(run_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,127}", run_id):
        raise DigestValidationError("public_digest_report_evidence_invalid: invalid run ID")
    run_dir = root / "runs" / run_id
    manifest_path = run_dir / "review-manifest-v3.json"
    ledger_path = run_dir / "review-inventory-v3.json"
    for path in (root / "runs", run_dir, manifest_path, ledger_path):
        if path.resolve() != path or path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
            raise DigestValidationError("public_digest_report_evidence_invalid: review evidence must use regular canonical paths inside this root")
    try:
        manifest = read_json(manifest_path)
        if Path(str(manifest.get("ledger_path", ""))) != ledger_path:
            raise DigestValidationError("public_digest_report_evidence_invalid: frozen ledger path differs from the canonical run path")
        payload = ledger_path.read_bytes()
        if hashlib.sha256(payload).hexdigest() != manifest.get("ledger_sha256"):
            raise DigestValidationError("public_digest_report_evidence_invalid: frozen ledger hash mismatch")
        ledger = json.loads(payload)
        for value in (manifest, ledger):
            if (not isinstance(value, dict) or value.get("schema_version") not in {REVIEW_SCHEMA_VERSION, SCHEMA_VERSION}
                    or value.get("run_id") != run_id or value.get("announcement_date") != digest.get("date")):
                raise DigestValidationError("public_digest_report_evidence_invalid: frozen review identity differs from this digest")
            _validate_public_artifact_profile(value)
    except (OSError, ValueError, TypeError) as exc:
        raise DigestValidationError("public_digest_report_evidence_invalid: readable bound review evidence is required") from exc
    inventory = ledger.get("inventory")
    if not isinstance(inventory, list) or any(
        not isinstance(item, dict) or not isinstance(item.get("paper"), dict)
        or not isinstance(item["paper"].get("arxiv_id"), str)
        or not isinstance(item["paper"].get("query_sources"), list)
        for item in inventory
    ):
        raise DigestValidationError("public_digest_report_evidence_invalid: frozen inventory is invalid")
    known_ids = {
        str(item["paper"]["arxiv_id"]) for item in inventory
        if item.get("local_classification") == "already_known"
        and REPORT_CATEGORY in item["paper"].get("query_sources", [])
    }
    if digest.get("report_already_known_count") != len(known_ids):
        raise DigestValidationError("digest.report_already_known_count differs from the frozen review inventory")

def configure_public_runtime(root: Path, config_path: Path | None = None):
    try:
        return public_config.apply_config(globals(), Path(root), config_path)
    except public_config.PublicDigestConfigError as exc:
        raise DigestValidationError(str(exc)) from exc

def configure_public_cli(args):
    root = getattr(args, "root", None)
    path = getattr(args, "public_config", None)
    if root is None:
        if path is None:
            raise DigestValidationError("public_digest_not_configured: rootless commands require --public-config before the subcommand")
        root = Path(path).resolve().parent
    config = configure_public_runtime(root, path)
    priority_root = getattr(args, "priority_root", None)
    if priority_root is not None and Path(priority_root).resolve() != Path(config["coordination_root"]):
        raise DigestValidationError("public_digest_coordination_mismatch")
    return config

V3_PAPER_FIELDS = (
    "title",
    "authors",
    "arxiv_id",
    "version",
    "announcement_date",
    "announcement_types",
    "query_sources",
    "categories",
    "submitted_or_updated",
    "arxiv_url",
    "pdf_url",
    "relevance_score",
    "recommendation",
    "core_conclusion",
    "research_problem",
    "method_overview",
    "contributions",
    "research_relation",
    "transferable_ideas",
    "limitations",
    "worth_reading",
    "follow_up",
    "evidence_level",
    "topic_group",
)
PAPER_FIELDS = (
    "title",
    "authors",
    "arxiv_id",
    "version",
    "announcement_date",
    "announcement_types",
    "query_sources",
    "categories",
    "submitted_or_updated",
    "arxiv_url",
    "pdf_url",
    "relevance_score",
    "recommendation",
    "core_conclusion",
    "research_problem",
    "method_overview",
    "contributions",
    "research_relation",
    "transferable_ideas",
    "limitations",
    "worth_reading",
    "follow_up",
    "evidence_level",
    "topic_group",
)
CV_DETAILED_FIELDS = (
    "title",
    "authors",
    "arxiv_id",
    "version",
    "announcement_date",
    "announcement_types",
    "query_sources",
    "categories",
    "submitted_or_updated",
    "arxiv_url",
    "pdf_url",
    "relevance_score",
    "core_conclusion",
    "research_problem",
    "method_overview",
    "contributions",
)
CV_COMPACT_FIELDS = (
    "title",
    "arxiv_id",
    "version",
    "announcement_date",
    "announcement_types",
    "query_sources",
    "submitted_or_updated",
    "arxiv_url",
    "pdf_url",
    "relevance_score",
    "core_conclusion",
)
# Untranslated metadata for the ranked remaining cs.CV papers. They are not
# rendered in the email or PDF; commit records them as delivered so later
# announcements do not resurface them.
CS_CV_REPORT_FIELDS = (
    "title",
    "arxiv_id",
    "version",
    "announcement_date",
    "announcement_types",
    "query_sources",
    "submitted_or_updated",
    "arxiv_url",
    "pdf_url",
    "relevance_score",
)
CHINESE_PROSE_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
PAPER_CHINESE_PROSE_FIELDS = (
    "recommendation",
    "core_conclusion",
    "research_problem",
    "method_overview",
    "contributions",
    "research_relation",
    "transferable_ideas",
    "limitations",
    "worth_reading",
    "follow_up",
)
CV_DETAILED_CHINESE_PROSE_FIELDS = (
    "core_conclusion",
    "research_problem",
    "method_overview",
    "contributions",
)
CV_COMPACT_CHINESE_PROSE_FIELDS = ("core_conclusion",)
TOP_LEVEL_FIELDS = (
    "date",
    "retrieval_window",
    "stats",
    "overview",
    "reading_order",
    "focus_papers",
    "watch_papers",
    "trends",
    "actionable_insights",
    "retrieval_coverage",
    "exclusion_stats",
    "cv_daily_remainder",
    "arxiv_tools",
)
STATS_FIELDS = (
    "retrieved",
    "unique",
    "candidates",
    "focus",
    "watch",
    "cv_remainder",
    "excluded_hidden",
)
ARXIV_ID_RE = re.compile(
    r"(?<![\w.])((?:\d{4}\.\d{4,5})|(?:[a-z-]+(?:\.[A-Z]{2})?/\d{7}))"
    r"(?:v(\d+))?(?!\d)",
    re.IGNORECASE,
)
THEME_RE = re.compile(r"((?!))")

DEFAULT_CONFIG_TEMPLATE = "Complete daily-digest-config.json before initialization."


def default_config_for_root(root: Path) -> str:
    return public_config.render_config_md(configure_public_runtime(root))


class DigestValidationError(ValueError):
    """Raised when a digest or runtime input violates the contract."""


class OfficialArxivFetchError(DigestValidationError):
    """Raised when the official arXiv API fallback cannot return a valid shard."""

    def __init__(
        self,
        kind: str,
        detail: str,
        *,
        http_status: int | None = None,
        exception_type: str | None = None,
        attempts: list[dict[str, Any]] | None = None,
        request_chain: list[dict[str, Any]] | None = None,
    ) -> None:
        if kind not in ARXIV_FAILURE_KINDS:
            raise DigestValidationError(f"unsupported arXiv failure kind: {kind}")
        normalized_detail = str(detail).strip() or "arXiv request failed without detail"
        super().__init__(normalized_detail)
        self.kind = kind
        self.detail = normalized_detail
        self.http_status = http_status
        self.exception_type = exception_type or self.__class__.__name__
        self.attempts = list(attempts or [])
        self.request_chain = list(request_chain or [])

    def __str__(self) -> str:
        # MCP transports exception text, not custom exception attributes. Keep
        # every route and retry visible there without changing retry classification.
        if self.request_chain:
            return json.dumps(self.as_record(), ensure_ascii=False)
        return self.detail

    def as_record(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "http_status": self.http_status,
            "exception_type": self.exception_type,
            "detail": self.detail,
            "attempts": copy.deepcopy(self.attempts),
            **({"request_chain": copy.deepcopy(self.request_chain)}
               if self.request_chain else {}),
        }


def arxiv_network_preflight(
    proxies: dict[str, str] | None = None,
    *,
    target_host: str = "arxiv.org",
    proxy_connector: Any = socket.create_connection,
    proxy_connect_timeout_seconds: float = 2.0,
) -> dict[str, Any]:
    """Verify that the sandbox HTTPS proxy policy has a reachable local listener."""

    configured = getproxies() if proxies is None else dict(proxies)
    if proxies is None and proxy_bypass(target_host):
        return {
            "ok": True,
            "kind": None,
            "retryable": False,
            "proxy_endpoint": None,
            "detail": f"HTTPS access to {target_host} bypasses the configured proxy.",
        }

    raw_proxy = configured.get("https") or configured.get("all")
    if not raw_proxy:
        return {
            "ok": True,
            "kind": None,
            "retryable": False,
            "proxy_endpoint": None,
            "detail": f"No HTTPS proxy denial sentinel is configured for {target_host}.",
        }

    parsed = urlparse(raw_proxy if "://" in raw_proxy else f"http://{raw_proxy}")
    try:
        port = parsed.port
    except ValueError:
        port = None
    host = (parsed.hostname or "").lower()
    endpoint = f"{host}:{port}" if host and port is not None else host or "invalid"
    denied = host in {"127.0.0.1", "localhost", "::1"} and port == 9
    if denied:
        return {
            "ok": False,
            "kind": "sandbox_network_denied",
            "retryable": False,
            "proxy_endpoint": endpoint,
            "detail": (
                "Scheduled Task network access is unavailable: HTTPS is routed "
                f"through the sandbox denial proxy {endpoint}. Enable network "
                "access for this Scheduled Task; retrying the arXiv request cannot help."
            ),
        }
    if host in {"127.0.0.1", "localhost", "::1"} and port is not None:
        try:
            connection = proxy_connector(
                (host, port),
                timeout=proxy_connect_timeout_seconds,
            )
        except OSError as exc:
            return {
                "ok": False,
                "kind": "sandbox_network_denied",
                "retryable": False,
                "proxy_endpoint": endpoint,
                "detail": (
                    "Scheduled Task HTTPS proxy policy is configured, but its local "
                    f"proxy listener {endpoint} is unreachable ({type(exc).__name__}: {exc}). "
                    "Enable `[features.network_proxy]` with `enabled = true` in the "
                    "effective Codex config, restart Codex, and retry. Repeating the "
                    "arXiv request cannot repair a missing or blocked proxy listener."
                ),
            }
        else:
            close = getattr(connection, "close", None)
            if callable(close):
                close()
    return {
        "ok": True,
        "kind": None,
        "retryable": False,
        "proxy_endpoint": endpoint,
        "detail": f"HTTPS uses a non-denial proxy endpoint ({endpoint}).",
    }


def require_arxiv_network_access(*, opener: Any = urlopen) -> None:
    """Fail before acquiring a lease when the default HTTP stack is sandbox-blocked."""

    if opener is not urlopen:
        return
    result = arxiv_network_preflight()
    if result["ok"]:
        return
    raise OfficialArxivFetchError(
        "sandbox_network_denied",
        result["detail"],
        exception_type="SandboxNetworkDenied",
    )


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _require_aware_utc(value: datetime, label: str) -> datetime:
    if value.tzinfo is None:
        raise DigestValidationError(f"{label} must be timezone-aware")
    return value.astimezone(timezone.utc)


def arxiv_mcp_not_before(
    previous_started_at: datetime | None,
    rate_limited_at: datetime | None = None,
) -> datetime | None:
    """Return the earliest UTC start time allowed by the global arXiv MCP gate."""

    candidates: list[datetime] = []
    if previous_started_at is not None:
        previous = _require_aware_utc(previous_started_at, "previous_started_at")
        candidates.append(
            previous
            + timedelta(
                seconds=ARXIV_MCP_RATE_LIMIT_POLICY["min_interval_seconds"],
            )
        )
    if rate_limited_at is not None:
        limited = _require_aware_utc(rate_limited_at, "rate_limited_at")
        candidates.append(
            limited
            + timedelta(
                seconds=ARXIV_MCP_RATE_LIMIT_POLICY["rate_limit_cooldown_seconds"],
            )
        )
    return max(candidates) if candidates else None


def classify_arxiv_failure(
    error_detail: str | None = None,
    *,
    http_status: int | None = None,
    rate_limited: bool = False,
    response_integrity: bool = False,
) -> str:
    """Classify an arXiv failure without treating an empty MCP error as permanent."""

    if response_integrity:
        return "response_integrity"
    if rate_limited or http_status == 429:
        return "rate_limited"
    if http_status in {408, 425, 500, 502, 503, 504}:
        return "transient_transport"
    detail = str(error_detail or "").strip()
    normalized = detail.lower()
    if (
        "sandbox_network_denied" in normalized
        or "sandbox denial proxy" in normalized
        or "winerror 10013" in normalized
    ):
        return "sandbox_network_denied"
    if not detail or re.fullmatch(r"error:\s*", detail, flags=re.IGNORECASE):
        return "transient_transport"
    transient_markers = (
        "timeout",
        "timed out",
        "connection reset",
        "connection refused",
        "connection aborted",
        "connecterror",
        "proxy",
        "temporary failure",
        "temporarily unavailable",
        "server disconnected",
        "remote protocol",
        "unexpected eof",
        "urlopen error",
        "network",
        "name resolution",
        "dns",
    )
    if any(marker in normalized for marker in transient_markers):
        return "transient_transport"
    return "permanent_request"


def arxiv_mcp_failure_action(
    call_kind: str,
    retries_used: int,
    *,
    rate_limited: bool = False,
    error_detail: str | None = None,
    http_status: int | None = None,
    failure_kind: str | None = None,
) -> dict[str, Any]:
    """Return the required executor action after an arXiv MCP call failure."""

    if call_kind not in ARXIV_MCP_CALL_KINDS:
        raise DigestValidationError(f"unsupported arXiv MCP call kind: {call_kind}")
    if not isinstance(retries_used, int) or retries_used < 0:
        raise DigestValidationError("retries_used must be a non-negative integer")
    kind = failure_kind or classify_arxiv_failure(
        error_detail,
        http_status=http_status,
        rate_limited=rate_limited,
    )
    if kind not in ARXIV_FAILURE_KINDS:
        raise DigestValidationError(f"unsupported arXiv failure kind: {kind}")

    if (
        kind == "rate_limited"
        and retries_used
        < ARXIV_MCP_RATE_LIMIT_POLICY["max_429_retries_per_call"]
    ):
        return {
            "action": "retry_same_call",
            "failure_kind": kind,
            "freeze_queue": True,
            "delay_seconds": ARXIV_MCP_RATE_LIMIT_POLICY[
                "rate_limit_cooldown_seconds"
            ],
            "advance_version_cursor": False,
        }

    if (
        kind == "transient_transport"
        and retries_used
        < ARXIV_MCP_RATE_LIMIT_POLICY["max_transient_retries_per_call"]
    ):
        delays = ARXIV_MCP_RATE_LIMIT_POLICY["transient_retry_delays_seconds"]
        return {
            "action": "retry_same_call",
            "failure_kind": kind,
            "freeze_queue": False,
            "delay_seconds": delays[retries_used],
            "advance_version_cursor": False,
        }

    if call_kind in ARXIV_MCP_REQUIRED_RETRIEVAL_KINDS:
        action = (
            "fallback_to_official_api"
            if kind in {"rate_limited", "transient_transport"}
            else "stop_coverage_incomplete"
        )
    elif call_kind == "version_check":
        action = "record_failure_hold_cursor"
    else:
        action = "fallback_to_abstract"
    return {
        "action": action,
        "failure_kind": kind,
        "freeze_queue": False,
        "delay_seconds": 0,
        "advance_version_cursor": False,
    }


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise DigestValidationError(f"missing JSON file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise DigestValidationError(f"invalid JSON file {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise DigestValidationError(f"JSON root must be an object: {path}")
    return value


def atomic_write_text(path: Path, text: str) -> None:
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
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    atomic_write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def announcement_batch_output_path(
    digest_root: Path,
    run_id: str,
    category: str,
) -> Path:
    """Return the fixed per-run announcement output path for the MCP service."""

    root = Path(digest_root)
    if not root.is_absolute():
        raise DigestValidationError("digest root must be an absolute path")
    normalized_run_id = str(run_id).strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,127}", normalized_run_id):
        raise DigestValidationError(
            "digest run ID must contain only letters, digits, dot, underscore, plus, "
            "or hyphen and begin with a letter or digit"
        )
    normalized_category = normalize_categories([category])[0]
    runs_root = (root.resolve() / "runs").resolve()
    output_path = (
        runs_root
        / normalized_run_id
        / f"{normalized_category}-announcement.json"
    ).resolve()
    if not output_path.is_relative_to(runs_root):
        raise DigestValidationError("announcement output escaped the digest runs root")
    return output_path


def _gate_state_default() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "active_lease": None,
        "previous_started_at": None,
        "rate_limited_at": None,
    }


def _parse_gate_timestamp(value: Any, label: str) -> datetime | None:
    if value in (None, ""):
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise DigestValidationError(f"invalid {label}: {value}") from exc
    return _require_aware_utc(parsed, label)


def _gate_timestamp(value: datetime) -> str:
    return (
        _require_aware_utc(value, "gate timestamp")
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _read_gate_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return _gate_state_default()
    state = read_json(path)
    if state.get("schema_version") != 1:
        raise DigestValidationError(f"unsupported arXiv MCP gate state: {path}")
    active_lease = state.get("active_lease")
    if active_lease is not None:
        if not isinstance(active_lease, dict):
            raise DigestValidationError("arXiv MCP gate active_lease must be an object")
        for field in ("token", "owner", "acquired_at", "expires_at"):
            if not active_lease.get(field):
                raise DigestValidationError(
                    f"arXiv MCP gate active_lease is missing {field}"
                )
    _parse_gate_timestamp(state.get("previous_started_at"), "previous_started_at")
    _parse_gate_timestamp(state.get("rate_limited_at"), "rate_limited_at")
    return state


@contextmanager
def _exclusive_gate_state_lock(
    path: Path,
    timeout_seconds: float = 10.0,
) -> Iterator[None]:
    """Hold a crash-safe cross-process lock while reading or replacing gate state."""

    if timeout_seconds < 0:
        raise DigestValidationError("gate lock timeout must be non-negative")
    path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout_seconds
    while True:
        handle = path.open("a+b", buffering=0)
        try:
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                # Two first-time callers can both observe an empty lock file. On
                # Windows, one may lock the first byte before the other writes the
                # sentinel, so retry the initialization instead of leaking a raw
                # PermissionError outside the bounded lock acquisition contract.
                handle.write(b"\0")
            break
        except PermissionError as exc:
            handle.close()
            if time.monotonic() >= deadline:
                raise DigestValidationError(
                    f"timed out initializing arXiv MCP gate state lock: {path}"
                ) from exc
            time.sleep(0.05)
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
                    raise DigestValidationError(
                        f"timed out acquiring arXiv MCP gate state lock: {path}"
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


def try_acquire_arxiv_mcp_gate(
    root: Path,
    owner: str,
    *,
    now: datetime | None = None,
    lease_seconds: int | None = None,
) -> dict[str, Any]:
    """Atomically acquire the single project-wide arXiv MCP call lease."""
    configure_public_runtime(root)

    normalized_owner = owner.strip()
    if not normalized_owner:
        raise DigestValidationError("arXiv MCP gate owner must be non-empty")
    lease_duration = (
        ARXIV_MCP_RATE_LIMIT_POLICY["lease_timeout_seconds"]
        if lease_seconds is None
        else lease_seconds
    )
    if not isinstance(lease_duration, int) or lease_duration <= 0:
        raise DigestValidationError("arXiv MCP gate lease_seconds must be positive")
    current = _require_aware_utc(now or datetime.now(timezone.utc), "now")
    root.mkdir(parents=True, exist_ok=True)
    state_path = root / ARXIV_MCP_GATE_STATE
    lock_path = root / ARXIV_MCP_GATE_LOCK

    with _exclusive_gate_state_lock(lock_path):
        state = _read_gate_state(state_path)
        active_lease = state.get("active_lease")
        if active_lease is not None:
            expires_at = _parse_gate_timestamp(
                active_lease["expires_at"],
                "active_lease.expires_at",
            )
            assert expires_at is not None
            if expires_at > current:
                return {
                    "acquired": False,
                    "reason": "active_lease",
                    "retry_after_seconds": (expires_at - current).total_seconds(),
                    "active_owner": active_lease["owner"],
                }
            state["active_lease"] = None

        not_before = arxiv_mcp_not_before(
            _parse_gate_timestamp(
                state.get("previous_started_at"),
                "previous_started_at",
            ),
            _parse_gate_timestamp(
                state.get("rate_limited_at"),
                "rate_limited_at",
            ),
        )
        if not_before is not None and not_before > current:
            return {
                "acquired": False,
                "reason": "rate_limit_delay",
                "retry_after_seconds": (not_before - current).total_seconds(),
                "not_before": _gate_timestamp(not_before),
            }

        token = uuid.uuid4().hex
        expires_at = current + timedelta(seconds=lease_duration)
        state.update(
            {
                "active_lease": {
                    "token": token,
                    "owner": normalized_owner,
                    "acquired_at": _gate_timestamp(current),
                    "expires_at": _gate_timestamp(expires_at),
                },
                "previous_started_at": _gate_timestamp(current),
                "updated_at": _gate_timestamp(current),
            }
        )
        atomic_write_json(state_path, state)
        return {
            "acquired": True,
            "token": token,
            "owner": normalized_owner,
            "started_at": _gate_timestamp(current),
            "expires_at": _gate_timestamp(expires_at),
        }


def acquire_arxiv_mcp_gate(
    root: Path,
    owner: str,
    *,
    wait_timeout_seconds: float = 360.0,
    lease_seconds: int | None = None,
) -> dict[str, Any]:
    """Wait for the mutex and rate-limit window, then return a call lease."""
    configure_public_runtime(root)

    if wait_timeout_seconds < 0:
        raise DigestValidationError("gate wait timeout must be non-negative")
    deadline = time.monotonic() + wait_timeout_seconds
    while True:
        result = try_acquire_arxiv_mcp_gate(
            root,
            owner,
            lease_seconds=lease_seconds,
        )
        if result["acquired"]:
            return result
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise DigestValidationError(
                "timed out waiting for the project-wide arXiv MCP gate"
            )
        delay = max(0.05, float(result["retry_after_seconds"]))
        time.sleep(min(delay, remaining, 1.0))


def release_arxiv_mcp_gate(
    root: Path,
    token: str,
    *,
    rate_limited: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Release one lease and optionally start the global HTTP 429 cooldown."""
    configure_public_runtime(root)

    normalized_token = token.strip()
    if not normalized_token:
        raise DigestValidationError("arXiv MCP gate token must be non-empty")
    current = _require_aware_utc(now or datetime.now(timezone.utc), "now")
    state_path = root / ARXIV_MCP_GATE_STATE
    lock_path = root / ARXIV_MCP_GATE_LOCK
    with _exclusive_gate_state_lock(lock_path):
        state = _read_gate_state(state_path)
        active_lease = state.get("active_lease")
        if active_lease is None:
            raise DigestValidationError("arXiv MCP gate has no active lease")
        if active_lease.get("token") != normalized_token:
            raise DigestValidationError("arXiv MCP gate token does not own the lease")
        state["active_lease"] = None
        state["released_at"] = _gate_timestamp(current)
        state["updated_at"] = _gate_timestamp(current)
        if rate_limited:
            state["rate_limited_at"] = _gate_timestamp(current)
        atomic_write_json(state_path, state)
        return {
            "released": True,
            "rate_limited": rate_limited,
            "not_before": (
                _gate_timestamp(
                    current
                    + timedelta(
                        seconds=ARXIV_MCP_RATE_LIMIT_POLICY[
                            "rate_limit_cooldown_seconds"
                        ]
                    )
                )
                if rate_limited
                else None
            ),
        }


def acquire_arxiv_request_gate(
    root: Path,
    owner: str,
    *,
    priority_root: Path | None = None,
    priority_gate: ArxivPriorityGate | None = None,
    digest_session_token: str | None = None,
) -> dict[str, Any]:
    """Acquire either the compatibility gate or the machine-wide digest lane."""
    configure_public_runtime(root)

    if priority_root is None:
        lease = acquire_arxiv_mcp_gate(root, owner)
        return {"backend": "legacy", **lease}
    normalized_token = str(digest_session_token or "").strip()
    if not normalized_token:
        raise DigestValidationError(
            "machine-wide arXiv access requires --digest-session-token"
        )
    gate = priority_gate or ArxivPriorityGate(priority_root)
    lease = gate.acquire_call(
        "digest",
        owner,
        digest_token=normalized_token,
    )
    return {"backend": "priority", **lease}


def release_arxiv_request_gate(
    root: Path,
    lease: dict[str, Any],
    *,
    priority_root: Path | None = None,
    priority_gate: ArxivPriorityGate | None = None,
    rate_limited: bool = False,
) -> dict[str, Any]:
    """Release a lease acquired by :func:`acquire_arxiv_request_gate`."""
    configure_public_runtime(root)

    if lease.get("backend") == "priority":
        if priority_root is None:
            raise DigestValidationError("priority_root is required for priority lease")
        gate = priority_gate or ArxivPriorityGate(priority_root)
        return gate.release_call(
            str(lease["token"]),
            rate_limited=rate_limited,
        )
    return release_arxiv_mcp_gate(
        root,
        str(lease["token"]),
        rate_limited=rate_limited,
    )


def initialize_runtime(root: Path) -> None:
    configure_public_runtime(root)
    root.mkdir(parents=True, exist_ok=True)
    config_path = root / "config.md"
    sent_path = root / "sent-papers.json"
    last_path = root / "last-successful-run.json"
    if not config_path.exists():
        atomic_write_text(config_path, default_config_for_root(root))
    if not sent_path.exists():
        atomic_write_json(sent_path, {"schema_version": SCHEMA_VERSION, "papers": {}})
    if not last_path.exists():
        atomic_write_json(
            last_path,
            {
                "schema_version": SCHEMA_VERSION,
                "last_successful_run": None,
                "announcement_cursors": {},
                "version_check_cursor": 0,
            },
        )


def normalize_categories(values: Any) -> list[str]:
    if not isinstance(values, list):
        raise DigestValidationError("categories must be an array")
    lookup = {category.lower(): category for category in TRACKED_CATEGORIES}
    normalized: list[str] = []
    for raw in values:
        category = lookup.get(str(raw).strip().lower())
        if category is None:
            raise DigestValidationError(f"unsupported tracked category: {raw}")
        if category not in normalized:
            normalized.append(category)
    return normalized


ANNOUNCEMENT_MONTHS = {
    month: index
    for index, month in enumerate(
        (
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        ),
        1,
    )
}
ANNOUNCEMENT_TYPES = ("new", "cross_list", "replacement")


def parse_announcement_date_heading(value: str) -> str:
    text = " ".join(str(value).split())
    match = re.fullmatch(
        r"Showing new listings for [A-Za-z]+,\s+(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})",
        text,
    )
    if not match:
        raise DigestValidationError(f"invalid arXiv announcement heading: {text!r}")
    month = ANNOUNCEMENT_MONTHS.get(match.group(2))
    if month is None:
        raise DigestValidationError(
            f"unsupported month in arXiv announcement heading: {text!r}"
        )
    try:
        parsed = datetime(int(match.group(3)), month, int(match.group(1))).date()
    except ValueError as exc:
        raise DigestValidationError(
            f"invalid date in arXiv announcement heading: {text!r}"
        ) from exc
    return parsed.isoformat()


def parse_catchup_date_heading(value: str) -> str:
    """Parse the compact date used by the official historical catchup page."""

    text = " ".join(str(value).split())
    match = re.fullmatch(
        r"[A-Za-z]{3},\s+(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})",
        text,
    )
    if not match:
        raise DigestValidationError(f"invalid arXiv catchup date: {text!r}")
    try:
        parsed = datetime.strptime(
            f"{match.group(1)} {match.group(2)} {match.group(3)}",
            "%d %b %Y",
        ).date()
    except ValueError as exc:
        raise DigestValidationError(
            f"invalid arXiv catchup date: {text!r}"
        ) from exc
    return parsed.isoformat()


def announcement_listing_url(
    category: str,
    announcement_date: str | None = None,
) -> str:
    normalized = normalize_categories([category])[0]
    if announcement_date is not None:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", announcement_date):
            raise DigestValidationError(
                "historical announcement date must use YYYY-MM-DD"
            )
        try:
            datetime.fromisoformat(announcement_date)
        except ValueError as exc:
            raise DigestValidationError(
                "historical announcement date is invalid"
            ) from exc
        return ARXIV_CATCHUP_URL_TEMPLATE.format(
            category=normalized,
            announcement_date=announcement_date,
        )
    return ARXIV_ANNOUNCEMENT_URL_TEMPLATE.format(category=normalized)


def expected_announcement_date(observed_at: datetime | None = None) -> str:
    """Return the newest listing date expected from arXiv's 20:00 US Eastern schedule."""

    value = observed_at or datetime.now(timezone.utc)
    if value.tzinfo is None:
        raise DigestValidationError("announcement observation time must be timezone-aware")
    try:
        eastern = value.astimezone(ZoneInfo(ARXIV_ANNOUNCEMENT_TIMEZONE))
    except ZoneInfoNotFoundError as exc:
        raise DigestValidationError(
            f"timezone data unavailable for {ARXIV_ANNOUNCEMENT_TIMEZONE}"
        ) from exc

    current = eastern.date()
    weekday = current.weekday()
    after_release = eastern.hour >= ARXIV_ANNOUNCEMENT_HOUR
    if weekday <= 3:
        expected = current + timedelta(days=1) if after_release else current
    elif weekday == 4:
        expected = current
    elif weekday == 5:
        expected = current - timedelta(days=1)
    elif after_release:
        expected = current + timedelta(days=1)
    else:
        expected = current - timedelta(days=2)
    return expected.isoformat()


def runtime_environment_preflight() -> dict[str, Any]:
    """Validate and fingerprint one Python runtime for the complete digest run."""

    executable = str(Path(sys.executable).resolve())
    module_versions: dict[str, str | None] = {}
    missing: list[str] = []
    for module_name in DAILY_DIGEST_REQUIRED_PYTHON_MODULES:
        try:
            module = __import__(module_name)
        except Exception:  # pragma: no cover - exact import failures are environment-specific
            module_versions[module_name] = None
            missing.append(module_name)
        else:
            version = getattr(module, "__version__", None)
            module_versions[module_name] = str(version) if version else "available"

    timezone_ready = False
    timezone_source: str | None = None
    try:
        announcement_timezone = ZoneInfo(ARXIV_ANNOUNCEMENT_TIMEZONE)
        winter_offset = datetime(2026, 1, 15, tzinfo=timezone.utc).astimezone(
            announcement_timezone
        ).utcoffset()
        summer_offset = datetime(2026, 7, 15, tzinfo=timezone.utc).astimezone(
            announcement_timezone
        ).utcoffset()
        if winter_offset is None or summer_offset is None:
            raise ValueError("timezone UTC offsets are unavailable")
        timezone_ready = True
        timezone_source = (
            "tzdata_package"
            if importlib.util.find_spec("tzdata") is not None
            else "system_zoneinfo"
        )
    except (OSError, ValueError, ZoneInfoNotFoundError):
        missing.append(f"timezone:{ARXIV_ANNOUNCEMENT_TIMEZONE}")

    identity = {
        "python_executable": executable,
        "python_version": sys.version.split()[0],
        "required_python_modules": module_versions,
        "announcement_timezone": ARXIV_ANNOUNCEMENT_TIMEZONE,
        "timezone_source": timezone_source,
    }
    fingerprint = hashlib.sha256(
        json.dumps(identity, ensure_ascii=True, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return {
        "schema_version": 1,
        "ready": not missing,
        **identity,
        "runtime_fingerprint": fingerprint,
        "timezone_ready": timezone_ready,
        "timezone_failure_code": None
        if timezone_ready
        else "timezone_data_unavailable",
        "missing": missing,
    }


DEFERRED_ANNOUNCEMENTS_FILENAME = "deferred-announcements-v1.json"


def deferred_announcement_dates(root: Path) -> tuple[str, ...]:
    """Read explicit operator exceptions; malformed evidence fails closed."""
    configure_public_runtime(root)
    path = root.resolve() / DEFERRED_ANNOUNCEMENTS_FILENAME
    if not path.exists():
        return ()
    value = read_json(path)
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise DigestValidationError("invalid deferred announcement ledger schema")
    entries = value.get("entries")
    if not isinstance(entries, list):
        raise DigestValidationError("invalid deferred announcement ledger entries")
    days = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise DigestValidationError("invalid deferred announcement entry")
        day = entry.get("date")
        if not isinstance(day, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
            raise DigestValidationError("invalid deferred announcement date")
        announcement_archive_path(root, day, TRACKED_CATEGORIES[0])
        if (entry.get("status") != "missing_pending"
                or entry.get("categories") != list(TRACKED_CATEGORIES)
                or any(not isinstance(entry.get(k), str) or not entry[k].strip()
                       for k in ("authorized_by", "authorization", "reason", "created_at"))):
            raise DigestValidationError("invalid deferred announcement authorization")
        if day in days:
            raise DigestValidationError("duplicate deferred announcement date")
        days.append(day)
    return tuple(sorted(days))


def defer_announcement(root: Path, day: str, *, reason: str, authorization: str) -> dict[str, Any]:
    """Operator-only registration: no cursor, checkpoint or delivery mutation."""
    configure_public_runtime(root)
    root = root.resolve()
    announcement_archive_path(root, day, TRACKED_CATEGORIES[0])
    if not reason.strip() or not authorization.strip():
        raise DigestValidationError("explicit authorization and reason are required")
    with _exclusive_gate_state_lock(root / "announcement-phase.lock"):
        with _exclusive_gate_state_lock(root / "digest-transaction.lock"):
            pending_path = root / "pending-run.json"
            if pending_path.exists():
                pending = read_json(pending_path)
                if pending and pending.get("delivery_status") != "committed":
                    raise DigestValidationError("cannot defer while a delivery is unresolved")
            path = root / DEFERRED_ANNOUNCEMENTS_FILENAME
            existing = deferred_announcement_dates(root)
            if day in existing:
                return read_json(path)
            if any((root / "deliveries").glob(f"arxiv-daily-{day}-*.json")):
                raise DigestValidationError("cannot defer a date with delivery artifacts")
            cursors = _committed_announcement_cursors(root)
            if (len(set(cursors.values())) != 1 or None in cursors.values()
                    or day <= str(next(iter(cursors.values())))
                    or day > expected_announcement_date()):
                raise DigestValidationError("deferred date must be available and uncommitted")
            value = read_json(path) if path.exists() else {"schema_version": 1, "entries": []}
            value["entries"].append({
                "date": day, "status": "missing_pending",
                "categories": list(TRACKED_CATEGORIES), "authorized_by": "user",
                "authorization": authorization, "reason": reason, "created_at": utc_now(),
                "committed_cursors_at_registration": cursors,
            })
            atomic_write_json(path, value)
            deferred_announcement_dates(root)
            return value


def announcement_cursor_action(
    cursor_date: str | None,
    current_date: str,
    *,
    observed_at: datetime | None = None,
    enforce_current: bool = True,
    deferred_dates: tuple[str, ...] = (),
) -> str:
    """Validate one announcement date against its committed category cursor."""

    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", current_date):
        raise DigestValidationError("current announcement date must use YYYY-MM-DD")
    current = datetime.fromisoformat(current_date).date()
    if current.weekday() >= 5:
        raise DigestValidationError(
            f"announcement date {current_date} falls on a weekend"
        )
    if cursor_date is not None and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", cursor_date):
        raise DigestValidationError("announcement cursor date must use YYYY-MM-DD")
    expected_date = expected_announcement_date(observed_at)
    if enforce_current and expected_date > current_date:
        raise OfficialArxivFetchError(
            "stale_announcement",
            "stale arXiv announcement page: "
            f"expected listing date {expected_date} after the scheduled "
            f"{ARXIV_ANNOUNCEMENT_HOUR}:00 {ARXIV_ANNOUNCEMENT_TIMEZONE} "
            f"release, but received {current_date}",
        )
    if cursor_date is None:
        return "process_migration_batch"
    cursor = datetime.fromisoformat(cursor_date).date()
    if current < cursor:
        raise DigestValidationError(
            f"announcement page date {current_date} precedes cursor {cursor_date}"
        )
    if current == cursor:
        return "already_processed"
    business_dates = []
    candidate = cursor + timedelta(days=1)
    while candidate <= current:
        if candidate.weekday() < 5:
            business_dates.append(candidate)
        candidate += timedelta(days=1)
    if any(day.isoformat() not in deferred_dates for day in business_dates[:-1]):
        raise DigestValidationError(
            f"announcement coverage gap from {cursor_date} to {current_date}; "
            "the current /new page requires an exact historical catchup batch"
        )
    return "process_next_batch"


class _AnnouncementListingParser(HTMLParser):
    """Extract one complete `/new` announcement batch without trusting layout text."""

    def __init__(self, category: str) -> None:
        super().__init__(convert_charrefs=True)
        self.category = normalize_categories([category])[0]
        self.announcement_date: str | None = None
        self.section_counts = {name: 0 for name in ANNOUNCEMENT_TYPES}
        self.entries: list[dict[str, Any]] = []
        self._section: str | None = None
        self._h3_depth = 0
        self._h3_text: list[str] = []
        self._in_dt = False
        self._in_dd = False
        self._entry: dict[str, Any] | None = None
        self._field: str | None = None
        self._field_depth = 0
        self._field_text: list[str] = []
        self._void_tags = {
            "area",
            "base",
            "br",
            "col",
            "embed",
            "hr",
            "img",
            "input",
            "link",
            "meta",
            "param",
            "source",
            "track",
            "wbr",
        }

    @staticmethod
    def _attributes(attrs: list[tuple[str, str | None]]) -> dict[str, str]:
        return {key: value or "" for key, value in attrs}

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        tag = tag.lower()
        attributes = self._attributes(attrs)
        if self._h3_depth:
            self._h3_depth += 1
        elif tag == "h3":
            self._h3_depth = 1
            self._h3_text = []

        if tag == "dt":
            self._in_dt = True
            self._entry = {
                "announcement_type": self._section,
                "query_sources": [self.category],
            }
        elif tag == "dd":
            self._in_dd = True

        if self._in_dt and tag == "a" and self._entry is not None:
            href = attributes.get("href", "")
            match = ARXIV_ID_RE.search(href)
            if match:
                base_id = match.group(1)
                version = int(match.group(2)) if match.group(2) else None
                if "/abs/" in href:
                    self._entry["arxiv_id"] = base_id
                    self._entry["arxiv_url"] = f"https://arxiv.org/abs/{base_id}"
                if version is not None and (
                    self._entry.get("arxiv_id") in {None, base_id}
                ):
                    self._entry["version"] = max(
                        version,
                        int(self._entry.get("version") or 0),
                    )

        if self._field is not None:
            if tag not in self._void_tags:
                self._field_depth += 1
            return
        classes = set(attributes.get("class", "").split())
        field: str | None = None
        if self._in_dd and tag == "div" and "list-title" in classes:
            field = "title"
        elif self._in_dd and tag == "div" and "list-authors" in classes:
            field = "authors"
        elif self._in_dd and tag == "div" and "list-subjects" in classes:
            field = "categories"
        elif self._in_dd and tag == "p" and "mathjax" in classes:
            field = "abstract"
        if field is not None:
            self._field = field
            self._field_depth = 1
            self._field_text = []

    def handle_data(self, data: str) -> None:
        if self._h3_depth:
            self._h3_text.append(data)
        if self._field is not None:
            self._field_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self._field is not None:
            self._field_depth -= 1
            if self._field_depth == 0:
                self._finish_field()

        if self._h3_depth:
            self._h3_depth -= 1
            if self._h3_depth == 0:
                self._finish_h3()

        if tag == "dt":
            self._in_dt = False
        elif tag == "dd":
            self._in_dd = False
            self._finish_entry()

    def _finish_h3(self) -> None:
        text = " ".join("".join(self._h3_text).split())
        self._h3_text = []
        if text.startswith("Showing new listings for "):
            self.announcement_date = parse_announcement_date_heading(text)
            self._section = None
            return
        section: str | None = None
        if text.startswith("New submissions"):
            section = "new"
        elif text.startswith("Cross"):
            section = "cross_list"
        elif text.startswith("Replacement"):
            section = "replacement"
        if section is None:
            return
        count_match = re.search(
            r"showing\s+(\d+)\s+of\s+(\d+)\s+entr(?:y|ies)",
            text,
            re.IGNORECASE,
        )
        if not count_match:
            raise DigestValidationError(
                f"announcement section count is missing: {text!r}"
            )
        shown = int(count_match.group(1))
        total = int(count_match.group(2))
        if shown != total:
            raise DigestValidationError(
                f"announcement section is truncated: {text!r}"
            )
        self._section = section
        self.section_counts[section] = total

    def _finish_field(self) -> None:
        assert self._field is not None
        field = self._field
        text = " ".join("".join(self._field_text).split())
        self._field = None
        self._field_text = []
        if self._entry is None:
            return
        if field == "title":
            self._entry["title"] = re.sub(r"^Title:\s*", "", text)
        elif field == "authors":
            self._entry["authors"] = [
                author.strip()
                for author in re.split(r",\s*", text)
                if author.strip()
            ]
        elif field == "categories":
            self._entry["categories"] = [
                match.group(1)
                for match in re.finditer(
                    r"\(([a-z][a-z-]*(?:\.[A-Za-z0-9-]+)?)\)",
                    text,
                )
            ]
        elif field == "abstract":
            self._entry["abstract"] = f"[EXTERNAL CONTENT] {text}"

    def _finish_entry(self) -> None:
        entry = self._entry
        self._entry = None
        if entry is None:
            return
        if entry.get("announcement_type") not in ANNOUNCEMENT_TYPES:
            raise DigestValidationError(
                "announcement entry appeared outside a recognized section"
            )
        base_id = entry.get("arxiv_id")
        if not isinstance(base_id, str):
            raise DigestValidationError("announcement entry is missing an arXiv ID")
        if entry.get("announcement_type") == "new" and entry.get("version") is None:
            entry["version"] = 1
        version = entry.get("version")
        version_suffix = f"v{version}" if isinstance(version, int) else ""
        entry["id"] = base_id
        entry["pdf_url"] = f"https://arxiv.org/pdf/{base_id}{version_suffix}"
        entry["url"] = entry["pdf_url"]
        entry["resource_uri"] = f"arxiv://{base_id}"
        entry["announcement_date"] = self.announcement_date
        entry["announcement_types"] = [entry["announcement_type"]]
        entry["submitted_or_updated"] = self.announcement_date
        entry["source"] = "arxiv_announcement"
        required = ("title", "authors", "categories", "abstract")
        missing = [field for field in required if not entry.get(field)]
        if missing:
            raise DigestValidationError(
                f"announcement entry {base_id} is missing: {', '.join(missing)}"
            )
        self.entries.append(entry)


def parse_announcement_listing(
    html_payload: bytes | str,
    category: str,
    *,
    listing_url: str | None = None,
) -> dict[str, Any]:
    """Normalize and integrity-check one official arXiv announcement page."""

    normalized = normalize_categories([category])[0]
    if isinstance(html_payload, bytes):
        try:
            document = html_payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise DigestValidationError(
                "arXiv announcement page is not valid UTF-8"
            ) from exc
    else:
        document = str(html_payload)
    total_match = re.search(
        r"Total of\s+(\d+)\s+entr(?:y|ies)",
        document,
        re.IGNORECASE,
    )
    if not total_match:
        raise DigestValidationError("arXiv announcement page is missing its total count")
    catchup_date_match = re.search(
        r"Total of\s+\d+\s+entr(?:y|ies)\s+for\s+"
        r"([A-Za-z]{3},\s+\d{1,2}\s+[A-Za-z]{3}\s+\d{4})",
        document,
        re.IGNORECASE,
    )
    parser = _AnnouncementListingParser(normalized)
    if catchup_date_match:
        parser.announcement_date = parse_catchup_date_heading(
            catchup_date_match.group(1)
        )
    try:
        parser.feed(document)
        parser.close()
    except DigestValidationError:
        raise
    except Exception as exc:
        raise DigestValidationError(
            f"could not parse arXiv announcement page: {type(exc).__name__}: {exc}"
        ) from exc
    if parser.announcement_date is None:
        raise DigestValidationError("arXiv announcement page is missing its batch date")
    if listing_url:
        catchup_url_match = re.fullmatch(
            r"https://(?:export\.)?arxiv\.org/catchup/([^/?#]+)/"
            r"(\d{4}-\d{2}-\d{2})\?abs=True&page=1",
            listing_url,
        )
        if catchup_url_match:
            url_category = normalize_categories([catchup_url_match.group(1)])[0]
            if url_category != normalized:
                raise DigestValidationError(
                    "arXiv catchup URL category does not match the requested category"
                )
            if catchup_url_match.group(2) != parser.announcement_date:
                raise DigestValidationError(
                    "arXiv catchup page date does not match its requested date"
                )
    total = int(total_match.group(1))
    section_total = sum(parser.section_counts.values())
    if section_total != total:
        raise DigestValidationError(
            f"announcement section counts total {section_total}, expected {total}"
        )
    if len(parser.entries) != total:
        raise DigestValidationError(
            f"announcement parser returned {len(parser.entries)} entries, expected {total}"
        )
    actual_counts = {
        name: sum(
            1
            for entry in parser.entries
            if entry.get("announcement_type") == name
        )
        for name in ANNOUNCEMENT_TYPES
    }
    if actual_counts != parser.section_counts:
        raise DigestValidationError(
            "announcement entry types do not match the published section counts"
        )
    identifiers = [str(entry["arxiv_id"]) for entry in parser.entries]
    if len(set(identifiers)) != len(identifiers):
        raise DigestValidationError(
            "announcement page contains a duplicate arXiv ID within one category"
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "category": normalized,
        "announcement_date": parser.announcement_date,
        "listing_url": listing_url or announcement_listing_url(normalized),
        "source": "arxiv_announcement",
        "counts": {
            "new_submissions": parser.section_counts["new"],
            "cross_lists": parser.section_counts["cross_list"],
            "replacements": parser.section_counts["replacement"],
            "total": total,
        },
        "papers": parser.entries,
        "missing_version_count": sum(
            1
            for paper in parser.entries
            if not isinstance(paper.get("version"), int)
        ),
        "complete": True,
        "inventory_validated": True,
    }


def parse_utc_minute(value: str) -> datetime:
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise DigestValidationError(f"invalid UTC timestamp: {value}") from exc
    if parsed.tzinfo is None:
        raise DigestValidationError(f"UTC timestamp requires a timezone: {value}")
    return parsed.astimezone(timezone.utc).replace(second=0, microsecond=0)


def iso_utc_minute(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(second=0, microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def arxiv_minute(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y%m%d%H%M")


def arxiv_date(value: datetime) -> str:
    return value.astimezone(timezone.utc).date().isoformat()


def make_shard(category: str, start: datetime, end: datetime) -> dict[str, Any]:
    normalized = normalize_categories([category])[0]
    start_minute = start.astimezone(timezone.utc).replace(second=0, microsecond=0)
    end_minute = end.astimezone(timezone.utc).replace(second=0, microsecond=0)
    if end_minute < start_minute:
        raise DigestValidationError("coverage shard end precedes start")
    query = (
        f"submittedDate:[{arxiv_minute(start_minute)} TO {arxiv_minute(end_minute)}] "
        f"AND cat:{normalized}"
    )
    date_from = arxiv_date(start_minute)
    date_to = arxiv_date(end_minute)
    return {
        "category": normalized,
        "from": iso_utc_minute(start_minute),
        "to": iso_utc_minute(end_minute),
        "query": query,
        "date_from": date_from,
        "date_to": date_to,
        "search_args": {
            "query": query,
            "categories": [normalized],
            "date_from": date_from,
            "date_to": date_to,
            "sort_by": "date",
            "max_results": 50,
        },
    }


def initial_coverage_shards(
    categories: list[str],
    start: str,
    end: str,
) -> list[dict[str, Any]]:
    normalized = normalize_categories(categories)
    start_minute = parse_utc_minute(start)
    end_minute = parse_utc_minute(end)
    if end_minute < start_minute:
        raise DigestValidationError("retrieval window end precedes start")
    shards: list[dict[str, Any]] = []
    for category in normalized:
        cursor = start_minute
        while cursor <= end_minute:
            day_end = cursor.replace(hour=23, minute=59)
            shard_end = min(day_end, end_minute)
            shards.append(make_shard(category, cursor, shard_end))
            cursor = shard_end + timedelta(minutes=1)
    return shards


def split_coverage_shard(shard: dict[str, Any]) -> list[dict[str, Any]]:
    start = parse_utc_minute(str(shard.get("from", "")))
    end = parse_utc_minute(str(shard.get("to", "")))
    if start >= end:
        raise DigestValidationError("a one-minute shard cannot be split")
    span_minutes = int((end - start).total_seconds() // 60) + 1
    left_minutes = span_minutes // 2
    left_end = start + timedelta(minutes=left_minutes - 1)
    right_start = left_end + timedelta(minutes=1)
    category = str(shard.get("category", ""))
    return [
        make_shard(category, start, left_end),
        make_shard(category, right_start, end),
    ]


def search_response_papers(response: dict[str, Any]) -> list[dict[str, Any]]:
    payload: Any = response
    content = response.get("content")
    if isinstance(content, list):
        text_blocks = [
            block.get("text")
            for block in content
            if isinstance(block, dict)
            and block.get("type") == "text"
            and isinstance(block.get("text"), str)
        ]
        if len(text_blocks) != 1:
            raise DigestValidationError(
                "search response content must contain exactly one JSON text block"
            )
        try:
            payload = json.loads(text_blocks[0])
        except json.JSONDecodeError as exc:
            raise DigestValidationError("search response text block is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise DigestValidationError("search response payload must be an object")
    papers = payload.get("papers")
    if not isinstance(papers, list):
        raise DigestValidationError("search response must contain a papers array")
    if len(papers) > 50:
        raise DigestValidationError("search response papers array exceeds the MCP limit of 50")
    if any(not isinstance(paper, dict) for paper in papers):
        raise DigestValidationError("search response papers must all be objects")
    return papers


def parse_published_timestamp(value: Any) -> datetime:
    if value is None:
        raise DigestValidationError("paper is missing published")
    text = str(value).strip().replace("Z", "+00:00")
    if not text:
        raise DigestValidationError("paper is missing published")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise DigestValidationError(f"invalid published timestamp: {value}") from exc
    if parsed.tzinfo is None:
        raise DigestValidationError(f"published timestamp requires a timezone: {value}")
    return parsed.astimezone(timezone.utc)


def validate_shard_search_args(shard: dict[str, Any]) -> None:
    start = parse_utc_minute(str(shard.get("from", "")))
    end = parse_utc_minute(str(shard.get("to", "")))
    expected = make_shard(str(shard.get("category", "")), start, end)
    for field in ("query", "date_from", "date_to", "search_args"):
        if shard.get(field) != expected[field]:
            raise DigestValidationError(
                f"coverage shard {field} does not match its category and UTC bounds"
            )


def resolve_coverage_shard(
    shard: dict[str, Any],
    response: dict[str, Any],
) -> dict[str, Any]:
    validate_shard_search_args(shard)
    papers = search_response_papers(response)
    resolved = copy.deepcopy(shard)
    retrieval = response.get("_retrieval")
    source = response.get("source")
    if source is None and isinstance(retrieval, dict):
        source = retrieval.get("source")
    source = source or "arxiv_mcp"
    if source not in ARXIV_RETRIEVAL_SOURCES:
        raise DigestValidationError(f"unsupported arXiv retrieval source: {source}")
    resolved["source"] = source
    returned_count = len(papers)
    resolved["returned"] = returned_count
    start = parse_utc_minute(str(shard.get("from", "")))
    end_exclusive = parse_utc_minute(str(shard.get("to", ""))) + timedelta(minutes=1)
    validation_errors: list[str] = []
    for index, paper in enumerate(papers):
        try:
            published = parse_published_timestamp(paper.get("published"))
        except DigestValidationError as exc:
            validation_errors.append(f"papers[{index}]: {exc}")
            continue
        if not start <= published < end_exclusive:
            paper_id = paper.get("id", paper.get("arxiv_id", "unknown"))
            validation_errors.append(
                f"papers[{index}] {paper_id} published {published.isoformat()} "
                f"outside [{iso_utc_minute(start)}, {iso_utc_minute(end_exclusive)})"
            )
    if validation_errors:
        resolved["complete"] = False
        resolved["requires_split"] = False
        resolved["overflow"] = False
        resolved["bounds_validated"] = False
        resolved["filter_mismatch"] = True
        resolved["validation_errors"] = validation_errors
        return resolved
    resolved["bounds_validated"] = True
    resolved["filter_mismatch"] = False
    if returned_count < 50:
        resolved["complete"] = True
        resolved["requires_split"] = False
        resolved["overflow"] = False
        return resolved
    end = parse_utc_minute(str(shard.get("to", "")))
    resolved["complete"] = False
    resolved["requires_split"] = start < end
    resolved["overflow"] = start >= end
    return resolved


OFFICIAL_ARXIV_NAMESPACES = {
    "atom": "http://www.w3.org/2005/Atom",
    "opensearch": "http://a9.com/-/spec/opensearch/1.1/",
}


def official_arxiv_request_url(shard: dict[str, Any]) -> str:
    """Build one standards-encoded official API request for a validated shard."""

    validate_shard_search_args(shard)
    parameters = {
        "search_query": shard["query"],
        "start": 0,
        "max_results": 50,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }
    return f"{OFFICIAL_ARXIV_API_URL}?{urlencode(parameters)}"


def official_arxiv_ids_request_url(identifiers: list[str]) -> str:
    if not isinstance(identifiers, list) or not 1 <= len(identifiers) <= 50:
        raise DigestValidationError(
            "official arXiv ID metadata requests require 1 to 50 IDs"
        )
    normalized = [normalize_arxiv_id(identifier)[0] for identifier in identifiers]
    if len(set(normalized)) != len(normalized):
        raise DigestValidationError(
            "official arXiv ID metadata requests cannot contain duplicate IDs"
        )
    parameters = {
        "id_list": ",".join(normalized),
        "start": 0,
        "max_results": len(normalized),
    }
    return f"{OFFICIAL_ARXIV_API_URL}?{urlencode(parameters)}"


def _atom_text(entry: ET.Element, path: str) -> str:
    element = entry.find(path, OFFICIAL_ARXIV_NAMESPACES)
    return element.text.strip() if element is not None and element.text else ""


def parse_official_arxiv_atom(xml_payload: bytes | str) -> dict[str, Any]:
    """Normalize an official arXiv Atom feed to the MCP search response shape."""

    try:
        root = ET.fromstring(xml_payload)
    except ET.ParseError as exc:
        raise OfficialArxivFetchError(
            "response_integrity",
            f"official arXiv API returned invalid Atom XML: {exc}",
            exception_type=type(exc).__name__,
        ) from exc

    total_text = _atom_text(root, "opensearch:totalResults")
    try:
        total_results = int(total_text) if total_text else 0
    except ValueError as exc:
        raise OfficialArxivFetchError(
            "response_integrity",
            f"official arXiv API returned invalid totalResults: {total_text!r}",
            exception_type=type(exc).__name__,
        ) from exc

    papers: list[dict[str, Any]] = []
    for index, entry in enumerate(
        root.findall("atom:entry", OFFICIAL_ARXIV_NAMESPACES)
    ):
        identifier_url = _atom_text(entry, "atom:id")
        if "/abs/" not in identifier_url:
            summary = _atom_text(entry, "atom:summary")
            raise OfficialArxivFetchError(
                "response_integrity",
                summary
                or f"official arXiv API entry {index} does not contain an article ID",
            )
        versioned_id = identifier_url.rsplit("/abs/", 1)[1]
        base_id = re.sub(r"v\d+$", "", versioned_id)
        if not ARXIV_ID_RE.fullmatch(base_id):
            raise OfficialArxivFetchError(
                "response_integrity",
                f"official arXiv API entry {index} has invalid ID: {versioned_id}",
            )

        authors = [
            _atom_text(author, "atom:name")
            for author in entry.findall("atom:author", OFFICIAL_ARXIV_NAMESPACES)
        ]
        categories = [
            str(category.get("term"))
            for category in entry.findall(
                "atom:category",
                OFFICIAL_ARXIV_NAMESPACES,
            )
            if category.get("term")
        ]
        pdf_url = ""
        abstract_url = identifier_url
        for link in entry.findall("atom:link", OFFICIAL_ARXIV_NAMESPACES):
            href = str(link.get("href") or "")
            if link.get("title") == "pdf":
                pdf_url = href
            if link.get("rel") == "alternate" and href:
                abstract_url = href
        if not pdf_url:
            pdf_url = f"https://arxiv.org/pdf/{versioned_id}"

        papers.append(
            {
                "id": base_id,
                "title": _atom_text(entry, "atom:title").replace("\n", " "),
                "authors": [author for author in authors if author],
                "abstract": "[EXTERNAL CONTENT] "
                + _atom_text(entry, "atom:summary").replace("\n", " "),
                "categories": categories,
                "published": _atom_text(entry, "atom:published"),
                "updated": _atom_text(entry, "atom:updated"),
                "url": pdf_url,
                "arxiv_url": abstract_url,
                "resource_uri": f"arxiv://{base_id}",
            }
        )

    if len(papers) > 50:
        raise OfficialArxivFetchError(
            "response_integrity",
            "official arXiv API returned more than the requested 50 entries",
        )
    return {
        "total_results": total_results,
        "papers": papers,
        "source": "official_arxiv_api",
    }


def _official_arxiv_error_detail(exc: BaseException, body: str = "") -> str:
    detail = str(exc).strip()
    body_detail = body.strip()
    if body_detail:
        detail = f"{detail}: {body_detail}" if detail else body_detail
    return detail or f"{type(exc).__name__} without error detail"


def _central_arxiv_get(
    url: str,
    *,
    headers: dict[str, str],
    timeout_seconds: int,
    opener: Any,
    use_cache: bool,
) -> Any:
    """Route one legacy fetch attempt through the repository-wide client."""

    injected_opener = opener is not urlopen
    client = _CENTRAL_ARXIV.ArxivClient(
        min_interval_seconds=0 if injected_opener else 3,
        cache_ttl_seconds=0 if injected_opener else 6 * 60 * 60,
        opener=opener,
    )
    try:
        return client.request(
            url,
            headers=headers,
            timeout_seconds=timeout_seconds,
            use_cache=use_cache and not injected_opener,
            # Injected openers are deterministic unit-test attempts. Production
            # calls keep the central client's global 429/503 retry loop so its
            # backoff remains inside the cross-process lock.
            max_retries=0 if injected_opener else None,
        )
    except _CENTRAL_ARXIV.ArxivHTTPError as exc:
        body = exc.body.decode("utf-8", errors="replace")
        detail = _official_arxiv_error_detail(exc, body)
        raise OfficialArxivFetchError(
            classify_arxiv_failure(detail, http_status=exc.status),
            detail,
            http_status=exc.status,
            exception_type=type(exc).__name__,
        ) from exc
    except (
        _CENTRAL_ARXIV.ArxivUnavailable,
        _CENTRAL_ARXIV.ArxivLockTimeout,
    ) as exc:
        detail = _official_arxiv_error_detail(exc)
        raise OfficialArxivFetchError(
            classify_arxiv_failure(detail),
            detail,
            exception_type=type(exc).__name__,
        ) from exc


def fetch_official_arxiv_once(
    shard: dict[str, Any],
    *,
    timeout_seconds: int = OFFICIAL_ARXIV_API_TIMEOUT_SECONDS,
    opener: Any = urlopen,
) -> dict[str, Any]:
    """Fetch one shard from the official API without retrying."""

    if not isinstance(timeout_seconds, int) or timeout_seconds <= 0:
        raise DigestValidationError("official arXiv timeout must be a positive integer")
    response = _central_arxiv_get(
        official_arxiv_request_url(shard),
        headers={
            "User-Agent": OFFICIAL_ARXIV_API_USER_AGENT,
            "Accept": "application/atom+xml",
        },
        timeout_seconds=timeout_seconds,
        opener=opener,
        use_cache=True,
    )
    return parse_official_arxiv_atom(response.body)


def fetch_official_arxiv_ids_once(
    identifiers: list[str],
    *,
    timeout_seconds: int = OFFICIAL_ARXIV_API_TIMEOUT_SECONDS,
    opener: Any = urlopen,
) -> dict[str, Any]:
    """Fetch the latest Atom metadata for a bounded list of announcement IDs."""

    if not isinstance(timeout_seconds, int) or timeout_seconds <= 0:
        raise DigestValidationError("official arXiv timeout must be a positive integer")
    response = _central_arxiv_get(
        official_arxiv_ids_request_url(identifiers),
        headers={
            "User-Agent": OFFICIAL_ARXIV_API_USER_AGENT,
            "Accept": "application/atom+xml",
        },
        timeout_seconds=timeout_seconds,
        opener=opener,
        use_cache=True,
    )
    return parse_official_arxiv_atom(response.body)


def fetch_official_arxiv_shard(
    root: Path,
    shard: dict[str, Any],
    *,
    priority_root: Path | None = None,
    digest_session_token: str | None = None,
    timeout_seconds: int = OFFICIAL_ARXIV_API_TIMEOUT_SECONDS,
    opener: Any = urlopen,
    sleep: Any = time.sleep,
) -> dict[str, Any]:
    """Fetch a shard with the shared lease and bounded official-API retries."""
    configure_public_runtime(root)

    validate_shard_search_args(shard)
    require_arxiv_network_access(opener=opener)
    transient_retries = 0
    rate_limit_retries = 0
    attempts: list[dict[str, Any]] = []
    owner = (
        f"official_api:{shard['category']}:{shard['from']}:{shard['to']}"
    )
    while True:
        lease = acquire_arxiv_request_gate(
            root,
            owner,
            priority_root=priority_root,
            digest_session_token=digest_session_token,
        )
        failure: OfficialArxivFetchError | None = None
        response: dict[str, Any] | None = None
        try:
            response = fetch_official_arxiv_once(
                shard,
                timeout_seconds=timeout_seconds,
                opener=opener,
            )
        except OfficialArxivFetchError as exc:
            failure = exc
        finally:
            release_arxiv_request_gate(
                root,
                lease,
                priority_root=priority_root,
                rate_limited=bool(
                    failure is not None and failure.kind == "rate_limited"
                ),
            )

        if response is not None:
            attempts.append(
                {
                    "attempt": len(attempts) + 1,
                    "outcome": "success",
                    "source": "official_arxiv_api",
                }
            )
            response["_retrieval"] = {
                "source": "official_arxiv_api",
                "attempts": attempts,
            }
            return response

        assert failure is not None
        attempts.append(
            {
                "attempt": len(attempts) + 1,
                "outcome": "failure",
                "source": "official_arxiv_api",
                "kind": failure.kind,
                "http_status": failure.http_status,
                "exception_type": failure.exception_type,
                "detail": failure.detail,
            }
        )
        delay = 0
        if (
            failure.kind == "rate_limited"
            and rate_limit_retries
            < ARXIV_MCP_RATE_LIMIT_POLICY["max_429_retries_per_call"]
        ):
            rate_limit_retries += 1
            delay = ARXIV_MCP_RATE_LIMIT_POLICY["rate_limit_cooldown_seconds"]
        elif (
            failure.kind == "transient_transport"
            and transient_retries
            < ARXIV_MCP_RATE_LIMIT_POLICY["max_transient_retries_per_call"]
        ):
            delays = ARXIV_MCP_RATE_LIMIT_POLICY["transient_retry_delays_seconds"]
            delay = delays[transient_retries]
            transient_retries += 1
        else:
            failure.attempts = attempts
            raise failure
        sleep(delay)


def fetch_official_arxiv_ids(
    root: Path,
    identifiers: list[str],
    *,
    priority_root: Path | None = None,
    priority_gate: ArxivPriorityGate | None = None,
    digest_session_token: str | None = None,
    timeout_seconds: int = OFFICIAL_ARXIV_API_TIMEOUT_SECONDS,
    opener: Any = urlopen,
    sleep: Any = time.sleep,
) -> dict[str, Any]:
    """Fetch latest metadata for up to 50 IDs with the shared bounded retry policy."""
    configure_public_runtime(root)

    normalized = [normalize_arxiv_id(identifier)[0] for identifier in identifiers]
    official_arxiv_ids_request_url(normalized)
    require_arxiv_network_access(opener=opener)
    transient_retries = 0
    rate_limit_retries = 0
    attempts: list[dict[str, Any]] = []
    owner = f"official_ids:{normalized[0]}:{len(normalized)}"
    while True:
        lease = acquire_arxiv_request_gate(
            root,
            owner,
            priority_root=priority_root,
            priority_gate=priority_gate,
            digest_session_token=digest_session_token,
        )
        failure: OfficialArxivFetchError | None = None
        response: dict[str, Any] | None = None
        try:
            response = fetch_official_arxiv_ids_once(
                normalized,
                timeout_seconds=timeout_seconds,
                opener=opener,
            )
        except OfficialArxivFetchError as exc:
            failure = exc
        finally:
            release_arxiv_request_gate(
                root,
                lease,
                priority_root=priority_root,
                priority_gate=priority_gate,
                rate_limited=bool(
                    failure is not None and failure.kind == "rate_limited"
                ),
            )
        if response is not None:
            attempts.append(
                {
                    "attempt": len(attempts) + 1,
                    "outcome": "success",
                    "source": "official_arxiv_api",
                }
            )
            response["_retrieval"] = {
                "source": "official_arxiv_api",
                "attempts": attempts,
            }
            return response
        assert failure is not None
        attempts.append(
            {
                "attempt": len(attempts) + 1,
                "outcome": "failure",
                "source": "official_arxiv_api",
                "kind": failure.kind,
                "http_status": failure.http_status,
                "exception_type": failure.exception_type,
                "detail": failure.detail,
            }
        )
        delay = 0
        if (
            failure.kind == "rate_limited"
            and rate_limit_retries
            < ARXIV_MCP_RATE_LIMIT_POLICY["max_429_retries_per_call"]
        ):
            rate_limit_retries += 1
            delay = ARXIV_MCP_RATE_LIMIT_POLICY["rate_limit_cooldown_seconds"]
        elif (
            failure.kind == "transient_transport"
            and transient_retries
            < ARXIV_MCP_RATE_LIMIT_POLICY["max_transient_retries_per_call"]
        ):
            delays = ARXIV_MCP_RATE_LIMIT_POLICY["transient_retry_delays_seconds"]
            delay = delays[transient_retries]
            transient_retries += 1
        else:
            failure.attempts = attempts
            raise failure
        sleep(delay)


def fetch_announcement_listing_once(
    category: str,
    *,
    target_date: str | None = None,
    timeout_seconds: int = OFFICIAL_ARXIV_API_TIMEOUT_SECONDS,
    opener: Any = urlopen,
    observed_at: datetime | None = None,
) -> dict[str, Any]:
    """Fetch a complete current or historical batch using bounded official routes."""

    normalized = normalize_categories([category])[0]
    if not isinstance(timeout_seconds, int) or timeout_seconds <= 0:
        raise DigestValidationError("arXiv announcement timeout must be a positive integer")
    primary_url = announcement_listing_url(normalized, target_date)
    current_url = announcement_listing_url(normalized)
    current_target = target_date == expected_announcement_date(observed_at)
    urls = [primary_url]
    if target_date is not None:
        if current_target:
            urls.extend([current_url, current_url.split("?", 1)[0]])
        # The official export host serves the same exact-date catchup route,
        # including full abstracts, when the main host rejects a query with 406.
        urls.append(primary_url.replace("https://arxiv.org/", f"{_CENTRAL_ARXIV.ARXIV_EXPORT_BASE_URL}/", 1))
    headers = {
        "User-Agent": OFFICIAL_ARXIV_API_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml",
        "Cache-Control": "no-cache, no-store, max-age=0",
        "Pragma": "no-cache",
    }
    rejected_urls: list[str] = []
    request_chain: list[dict[str, Any]] = []
    for index, url in enumerate(urls):
        started = time.monotonic()
        request_record: dict[str, Any] = {
            "url": url, "category": normalized, "target_date": target_date,
            "timeout_seconds": timeout_seconds,
        }
        try:
            response = _central_arxiv_get(
                url, headers=headers, timeout_seconds=timeout_seconds,
                opener=opener, use_cache=False,
            )
        except OfficialArxivFetchError as exc:
            request_record.update(
                outcome="failure", kind=exc.kind, http_status=exc.http_status,
                exception_type=exc.exception_type, detail=exc.detail,
                elapsed_seconds=round(time.monotonic() - started, 3),
            )
            request_chain.append(request_record)
            exc.request_chain = copy.deepcopy(request_chain)
            if exc.http_status != 406 or index == len(urls) - 1:
                raise
            rejected_urls.append(url)
            continue
        request_record.update(
            http_status=response.status,
            elapsed_seconds=round(time.monotonic() - started, 3),
        )
        try:
            batch = parse_announcement_listing(response.body, normalized, listing_url=url)
            if target_date is not None and batch["announcement_date"] != target_date:
                if (
                    url.startswith("https://arxiv.org/list/")
                    and current_target and batch["announcement_date"] < target_date
                ):
                    raise OfficialArxivFetchError(
                        "stale_announcement",
                        f"stale arXiv current fallback: expected {target_date}, "
                        f"received {batch['announcement_date']}",
                    )
                raise DigestValidationError(
                    f"arXiv announcement page date {batch['announcement_date']} "
                    f"does not match requested date {target_date}"
                )
        except OfficialArxivFetchError as exc:
            request_record.update(outcome="failure", kind=exc.kind, detail=exc.detail)
            request_chain.append(request_record)
            exc.request_chain = copy.deepcopy(request_chain)
            raise
        except DigestValidationError as exc:
            request_record.update(
                outcome="failure", kind="response_integrity", detail=str(exc),
                exception_type=type(exc).__name__,
            )
            request_chain.append(request_record)
            raise OfficialArxivFetchError(
                "response_integrity", str(exc), exception_type=type(exc).__name__,
                request_chain=request_chain,
            ) from exc
        request_record["outcome"] = "success"
        request_chain.append(request_record)
        batch["_retrieval"] = {
            "source": "arxiv_announcement",
            "request_chain": request_chain,
            "listing_mode": "catchup" if "/catchup/" in url else "current",
            "response": {
                "status": response.status,
                "fetched_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "headers": {
                    key: value for key, value in response.headers.items()
                    if key in {"date", "age", "etag", "last-modified", "cache-control", "via", "x-cache"}
                },
            },
        }
        if rejected_urls:
            fallback = {
                "from_url": primary_url, "http_status": 406,
                "rejected_urls": rejected_urls,
            }
            if current_url in rejected_urls:
                fallback["rejected_current_url"] = current_url
            batch["_retrieval"]["fallback"] = fallback
        return batch
    raise AssertionError("announcement request candidates must not be empty")


def parse_arxiv_abstract_version(
    html_payload: bytes | str,
    identifier: str,
) -> int:
    """Extract the latest explicit version from an official arXiv abstract page."""

    base_id = normalize_arxiv_id(identifier)[0]
    if isinstance(html_payload, bytes):
        try:
            document = html_payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise DigestValidationError(
                "arXiv abstract page is not valid UTF-8"
            ) from exc
    else:
        document = str(html_payload)
    versions = [
        int(match.group(2))
        for match in ARXIV_ID_RE.finditer(document)
        if match.group(1).lower() == base_id.lower() and match.group(2)
    ]
    if not versions:
        raise DigestValidationError(
            f"arXiv abstract page omitted an explicit version for {base_id}"
        )
    return max(versions)


def fetch_arxiv_abstract_version_once(
    identifier: str,
    *,
    timeout_seconds: int = OFFICIAL_ARXIV_API_TIMEOUT_SECONDS,
    opener: Any = urlopen,
) -> int:
    base_id = normalize_arxiv_id(identifier)[0]
    if not isinstance(timeout_seconds, int) or timeout_seconds <= 0:
        raise DigestValidationError(
            "arXiv abstract timeout must be a positive integer"
        )
    url = ARXIV_ABSTRACT_URL_TEMPLATE.format(identifier=base_id)
    response = _central_arxiv_get(
        url,
        headers={
            "User-Agent": OFFICIAL_ARXIV_API_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
        },
        timeout_seconds=timeout_seconds,
        opener=opener,
        use_cache=True,
    )
    payload = response.body
    try:
        return parse_arxiv_abstract_version(payload, base_id)
    except DigestValidationError as exc:
        raise OfficialArxivFetchError(
            "response_integrity",
            str(exc),
            exception_type=type(exc).__name__,
        ) from exc


def fetch_arxiv_abstract_version(
    root: Path,
    identifier: str,
    *,
    priority_root: Path | None = None,
    priority_gate: ArxivPriorityGate | None = None,
    digest_session_token: str | None = None,
    timeout_seconds: int = OFFICIAL_ARXIV_API_TIMEOUT_SECONDS,
    opener: Any = urlopen,
    sleep: Any = time.sleep,
) -> int:
    """Resolve one version through the same lease and bounded retry contract."""
    configure_public_runtime(root)

    base_id = normalize_arxiv_id(identifier)[0]
    require_arxiv_network_access(opener=opener)
    transient_retries = 0
    rate_limit_retries = 0
    attempts: list[dict[str, Any]] = []
    while True:
        lease = acquire_arxiv_request_gate(
            root,
            f"abstract_version:{base_id}",
            priority_root=priority_root,
            priority_gate=priority_gate,
            digest_session_token=digest_session_token,
        )
        failure: OfficialArxivFetchError | None = None
        version: int | None = None
        try:
            version = fetch_arxiv_abstract_version_once(
                base_id,
                timeout_seconds=timeout_seconds,
                opener=opener,
            )
        except OfficialArxivFetchError as exc:
            failure = exc
        finally:
            release_arxiv_request_gate(
                root,
                lease,
                priority_root=priority_root,
                priority_gate=priority_gate,
                rate_limited=bool(
                    failure is not None and failure.kind == "rate_limited"
                ),
            )
        if version is not None:
            return version
        assert failure is not None
        attempts.append(
            {
                "attempt": len(attempts) + 1,
                "outcome": "failure",
                "source": "arxiv_abstract_page",
                "kind": failure.kind,
                "http_status": failure.http_status,
                "exception_type": failure.exception_type,
                "detail": failure.detail,
            }
        )
        delay = 0
        if (
            failure.kind == "rate_limited"
            and rate_limit_retries
            < ARXIV_MCP_RATE_LIMIT_POLICY["max_429_retries_per_call"]
        ):
            rate_limit_retries += 1
            delay = ARXIV_MCP_RATE_LIMIT_POLICY["rate_limit_cooldown_seconds"]
        elif (
            failure.kind == "transient_transport"
            and transient_retries
            < ARXIV_MCP_RATE_LIMIT_POLICY["max_transient_retries_per_call"]
        ):
            delays = ARXIV_MCP_RATE_LIMIT_POLICY["transient_retry_delays_seconds"]
            delay = delays[transient_retries]
            transient_retries += 1
        else:
            failure.attempts = attempts
            raise failure
        sleep(delay)


def fetch_announcement_batch(
    root: Path,
    category: str,
    *,
    cursor_date: str | None = None,
    priority_root: Path | None = None,
    priority_gate: ArxivPriorityGate | None = None,
    digest_session_token: str | None = None,
    timeout_seconds: int = OFFICIAL_ARXIV_API_TIMEOUT_SECONDS,
    opener: Any = urlopen,
    sleep: Any = time.sleep,
    observed_at: datetime | None = None,
    target_date: str | None = None,
) -> dict[str, Any]:
    """Fetch a complete current or exact historical inventory under one lease."""
    configure_public_runtime(root)

    normalized = normalize_categories([category])[0]
    if target_date is not None:
        # URL construction performs strict syntax and calendar validation.
        announcement_listing_url(normalized, target_date)
    require_arxiv_network_access(opener=opener)
    transient_retries = 0
    rate_limit_retries = 0
    stale_retries = 0
    attempts: list[dict[str, Any]] = []
    owner = f"announcement:{normalized}"
    while True:
        lease = acquire_arxiv_request_gate(
            root,
            owner,
            priority_root=priority_root,
            priority_gate=priority_gate,
            digest_session_token=digest_session_token,
        )
        failure: OfficialArxivFetchError | None = None
        failure_context: dict[str, Any] = {}
        batch: dict[str, Any] | None = None
        try:
            batch = fetch_announcement_listing_once(
                normalized,
                target_date=target_date,
                timeout_seconds=timeout_seconds,
                opener=opener,
                observed_at=observed_at,
            )
        except OfficialArxivFetchError as exc:
            failure = exc
        finally:
            release_arxiv_request_gate(
                root,
                lease,
                priority_root=priority_root,
                priority_gate=priority_gate,
                rate_limited=bool(
                    failure is not None and failure.kind == "rate_limited"
                ),
            )

        if batch is not None:
            retrieval = dict(batch.get("_retrieval") or {})
            response = copy.deepcopy(retrieval.get("response"))
            try:
                if (
                    target_date is not None
                    and batch.get("announcement_date") != target_date
                ):
                    raise DigestValidationError(
                        "historical announcement response date does not match "
                        f"requested target {target_date}"
                    )
                cursor_action = announcement_cursor_action(
                    cursor_date,
                    str(batch.get("announcement_date", "")),
                    observed_at=observed_at,
                    enforce_current=target_date is None,
                    deferred_dates=deferred_announcement_dates(root),
                )
            except OfficialArxivFetchError as exc:
                failure = exc
                failure_context = {
                    "announcement_date": batch.get("announcement_date"),
                    "expected_announcement_date": expected_announcement_date(
                        observed_at
                    ),
                    "response": response,
                }
                batch = None
            else:
                attempts.append(
                    {
                        "attempt": len(attempts) + 1,
                        "outcome": "success",
                        "source": "arxiv_announcement",
                        "announcement_date": batch.get("announcement_date"),
                    }
                )
                retrieval["source"] = "arxiv_announcement"
                retrieval["attempts"] = attempts
                batch["_retrieval"] = retrieval
                batch["cursor_action"] = cursor_action
                return batch

        if failure is None:
            raise DigestValidationError(
                "announcement fetch ended without a batch or classified failure"
            )
        attempts.append(
            {
                "attempt": len(attempts) + 1,
                "outcome": "failure",
                "source": "arxiv_announcement",
                "kind": failure.kind,
                "http_status": failure.http_status,
                "exception_type": failure.exception_type,
                "detail": failure.detail,
                **failure_context,
                "request_chain": copy.deepcopy(failure.request_chain),
            }
        )
        delay = 0
        if (
            failure.kind == "rate_limited"
            and rate_limit_retries
            < ARXIV_MCP_RATE_LIMIT_POLICY["max_429_retries_per_call"]
        ):
            rate_limit_retries += 1
            delay = ARXIV_MCP_RATE_LIMIT_POLICY["rate_limit_cooldown_seconds"]
        elif (
            failure.kind == "stale_announcement"
            and stale_retries < ARXIV_STALE_REVALIDATION_RETRIES
        ):
            stale_retries += 1
            delay = ARXIV_STALE_REVALIDATION_DELAY_SECONDS
        elif (
            failure.kind == "transient_transport"
            and transient_retries
            < ARXIV_MCP_RATE_LIMIT_POLICY["max_transient_retries_per_call"]
        ):
            delays = ARXIV_MCP_RATE_LIMIT_POLICY["transient_retry_delays_seconds"]
            delay = delays[transient_retries]
            transient_retries += 1
        else:
            failure.attempts = attempts
            raise failure
        sleep(delay)


def hydrate_announcement_versions(
    root: Path,
    batch: dict[str, Any],
    *,
    priority_root: Path | None = None,
    priority_gate: ArxivPriorityGate | None = None,
    digest_session_token: str | None = None,
    timeout_seconds: int = OFFICIAL_ARXIV_API_TIMEOUT_SECONDS,
    opener: Any = urlopen,
    sleep: Any = time.sleep,
) -> dict[str, Any]:
    """Fill versions omitted by `/new` using bounded official ID metadata calls."""
    configure_public_runtime(root)

    value = copy.deepcopy(batch)
    papers = value.get("papers")
    if not isinstance(papers, list):
        raise DigestValidationError("announcement batch papers must be an array")
    missing = [
        str(paper.get("arxiv_id"))
        for paper in papers
        if isinstance(paper, dict) and not isinstance(paper.get("version"), int)
    ]
    metadata_by_id: dict[str, dict[str, Any]] = {}
    metadata_attempts: list[dict[str, Any]] = []
    abstract_fallback_count = 0
    for offset in range(0, len(missing), 50):
        identifiers = missing[offset : offset + 50]
        try:
            response = fetch_official_arxiv_ids(
                root,
                identifiers,
                priority_root=priority_root,
                priority_gate=priority_gate,
                digest_session_token=digest_session_token,
                timeout_seconds=timeout_seconds,
                opener=opener,
                sleep=sleep,
            )
        except OfficialArxivFetchError as exc:
            metadata_attempts.append(
                {
                    "outcome": "fallback",
                    "source": "official_arxiv_api",
                    **exc.as_record(),
                }
            )
            for identifier in identifiers:
                version = fetch_arxiv_abstract_version(
                    root,
                    identifier,
                    priority_root=priority_root,
                    priority_gate=priority_gate,
                    digest_session_token=digest_session_token,
                    timeout_seconds=timeout_seconds,
                    opener=opener,
                    sleep=sleep,
                )
                metadata_by_id[identifier] = {
                    "id": identifier,
                    "url": f"https://arxiv.org/pdf/{identifier}v{version}",
                    "updated": None,
                    "source": "arxiv_abstract_page",
                }
                abstract_fallback_count += 1
            continue
        retrieval = response.get("_retrieval")
        if isinstance(retrieval, dict):
            attempts = retrieval.get("attempts")
            if isinstance(attempts, list):
                metadata_attempts.extend(copy.deepcopy(attempts))
        for paper in response.get("papers", []):
            if not isinstance(paper, dict):
                continue
            base_id, version = normalize_arxiv_id(
                str(paper.get("id", "")),
                str(paper.get("url", "")),
            )
            if version is None:
                raise OfficialArxivFetchError(
                    "response_integrity",
                    f"official metadata omitted the latest version for {base_id}",
                )
            metadata_by_id[base_id] = paper
    unresolved = [identifier for identifier in missing if identifier not in metadata_by_id]
    if unresolved:
        raise OfficialArxivFetchError(
            "response_integrity",
            "official metadata did not return announcement IDs: "
            + ", ".join(unresolved),
        )
    for paper in papers:
        if not isinstance(paper, dict) or isinstance(paper.get("version"), int):
            continue
        base_id = str(paper["arxiv_id"])
        metadata = metadata_by_id[base_id]
        _, version = normalize_arxiv_id(
            str(metadata.get("id", "")),
            str(metadata.get("url", "")),
        )
        assert version is not None
        paper["version"] = version
        paper["pdf_url"] = f"https://arxiv.org/pdf/{base_id}v{version}"
        paper["url"] = paper["pdf_url"]
        paper["metadata_source"] = metadata.get(
            "source",
            "official_arxiv_api",
        )
        if metadata.get("updated"):
            paper["updated"] = metadata["updated"]
    value["metadata_hydrated_count"] = len(missing)
    metadata_sources = ["arxiv_announcement"]
    if missing and abstract_fallback_count < len(missing):
        metadata_sources.append("official_arxiv_api")
    if abstract_fallback_count:
        metadata_sources.append("arxiv_abstract_page")
    value["metadata_sources"] = metadata_sources
    value["abstract_version_fallback_count"] = abstract_fallback_count
    if metadata_attempts:
        value["_metadata_retrieval"] = {
            "source": "official_arxiv_api",
            "attempts": metadata_attempts,
        }
    return value


def announcement_batch_coverage(batch: dict[str, Any]) -> dict[str, Any]:
    """Build one category coverage record from a validated announcement batch."""

    category = normalize_categories([batch.get("category")])[0]
    if batch.get("complete") is not True or batch.get("inventory_validated") is not True:
        raise DigestValidationError(
            f"announcement batch for {category} is not completely validated"
        )
    papers = batch.get("papers")
    counts = batch.get("counts")
    if not isinstance(papers, list) or not isinstance(counts, dict):
        raise DigestValidationError(
            f"announcement batch for {category} is missing papers or counts"
        )
    total = counts.get("total")
    if total != len(papers):
        raise DigestValidationError(
            f"announcement batch for {category} has inconsistent paper count"
        )
    unique_count = len({str(paper.get("arxiv_id")) for paper in papers})
    batch_record = {
        "announcement_date": batch.get("announcement_date"),
        "listing_url": batch.get("listing_url"),
        "source": "arxiv_announcement",
        "counts": copy.deepcopy(counts),
        "returned": len(papers),
        "complete": True,
        "inventory_validated": True,
    }
    return {
        "category": category,
        "complete": True,
        "raw_count": len(papers),
        "unique_count": unique_count,
        "batches": [batch_record],
    }


def failure_report_path(root: Path, report_date: str) -> Path:
    """Return the normalized project-local failure report path."""
    configure_public_runtime(root)

    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", report_date):
        raise DigestValidationError("failure report date must use YYYY-MM-DD")
    return root.resolve() / f"{report_date}-failure.md"


def write_failure_report(root: Path, report_date: str, content: str) -> dict[str, Path]:
    """Write a dated failure report and its latest-failure alias safely."""
    configure_public_runtime(root)

    if not str(content).strip():
        raise DigestValidationError("failure report content must be non-empty")
    root.mkdir(parents=True, exist_ok=True)
    dated = failure_report_path(root, report_date)
    latest = root.resolve() / "latest-failure.md"
    atomic_write_text(dated, content)
    atomic_write_text(latest, content)
    if not dated.exists() or not latest.exists():
        raise DigestValidationError("failure report paths were not created")
    return {"dated": dated, "latest": latest}


def paper_text(paper: dict[str, Any]) -> str:
    return " ".join(
        str(paper.get(field, ""))
        for field in ("title", "abstract", "core_conclusion", "research_problem")
    ).lower()


def exclusion_reason(paper: dict[str, Any]) -> str | None:
    return public_config.configured_exclusion(_require_public_configuration(), paper_text(paper))


def assign_topic_group(paper: dict[str, Any]) -> str:
    return public_config.configured_topic_group(_require_public_configuration(), paper_text(paper))


def paper_sort_key(paper: dict[str, Any]) -> tuple[Any, ...]:
    submitted = str(paper.get("submitted_or_updated", "")).replace("Z", "+00:00")
    try:
        submitted_rank = -datetime.fromisoformat(submitted).timestamp()
    except ValueError:
        submitted_rank = 0.0
    return (
        -int(paper.get("relevance_score", 0)),
        submitted_rank,
        str(paper.get("arxiv_id", "")),
    )


def focus_sort_key(paper: dict[str, Any]) -> tuple[Any, ...]:
    group = str(paper.get("topic_group", "other_relevant"))
    rank = TOPIC_GROUPS.index(group) if group in TOPIC_GROUPS else len(TOPIC_GROUPS)
    return (rank, *paper_sort_key(paper))


def canonicalize_digest(digest: dict[str, Any]) -> dict[str, Any]:
    value = copy.deepcopy(digest)
    value["focus_papers"] = sorted(value.get("focus_papers", []), key=focus_sort_key)
    value["watch_papers"] = sorted(value.get("watch_papers", []), key=paper_sort_key)
    for remainder_name in ("cs_cv_report", "cv_daily_remainder"):
        remainder = value.get(remainder_name, {})
        if isinstance(remainder, dict):
            for field in ("detailed", "compact", "papers"):
                if isinstance(remainder.get(field), list):
                    remainder[field] = sorted(remainder[field], key=paper_sort_key)
    value["reading_order"] = [
        paper["title"] for paper in value["focus_papers"] + value["watch_papers"]
    ]
    coverage = value.get("retrieval_coverage")
    if isinstance(coverage, list):
        for entry in coverage:
            if not isinstance(entry, dict):
                continue
            batches = entry.get("batches")
            if isinstance(batches, list):
                for batch in batches:
                    if isinstance(batch, dict):
                        batch.setdefault("source", "arxiv_announcement")
            shards = entry.get("shards")
            if not isinstance(shards, list):
                continue
            for shard in shards:
                if isinstance(shard, dict):
                    shard.setdefault("source", "arxiv_mcp")
    return value


TRANSACTION_METADATA_FIELDS = (
    "schema_version",
    "run_id",
    "transaction_id",
    "delivery_status",
    "rendered_at",
    "report_files",
    "gmail_message_id",
    "commit_started_at",
    "committed_at",
)


def digest_transaction_id(digest: dict[str, Any]) -> str:
    """Return a stable identity for one validated digest transaction."""

    value = canonicalize_digest(digest)
    for field in TRANSACTION_METADATA_FIELDS:
        value.pop(field, None)
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def cv_delivery_coverage_errors(digest: dict[str, Any]) -> list[str]:
    'Require every announced selected report category paper in selected cards or the PDF remainder.'

    errors: list[str] = []
    selected = list(digest.get("focus_papers", [])) + list(
        digest.get("watch_papers", [])
    )
    def announcement_sources(paper: dict[str, Any]) -> set[str]:
        sources = paper.get("query_sources")
        if isinstance(sources, list):
            return {str(source) for source in sources}
        return set()

    selected_cv_ids = {
        str(paper.get("arxiv_id"))
        for paper in selected
        if isinstance(paper, dict) and REPORT_CATEGORY in announcement_sources(paper)
    }
    remainder = digest.get("cs_cv_report") if digest.get("schema_version") == SCHEMA_VERSION else digest.get("cv_daily_remainder")
    remainder_papers: list[Any] = []
    if isinstance(remainder, dict):
        for field in ("detailed", "compact", "papers"):
            papers = remainder.get(field)
            if isinstance(papers, list):
                remainder_papers.extend(papers)
    remainder_ids = {
        str(paper.get("arxiv_id"))
        for paper in remainder_papers
        if isinstance(paper, dict) and paper.get("arxiv_id")
    }
    remainder_outside_cv_inventory = {
        str(paper.get("arxiv_id"))
        for paper in remainder_papers
        if isinstance(paper, dict)
        and paper.get("arxiv_id")
        and REPORT_CATEGORY not in announcement_sources(paper)
    }
    if remainder_outside_cv_inventory:
        errors.append(
            _report_category_text('cv_daily_remainder contains papers outside the cs.CV announcement inventory: ')
            + ", ".join(sorted(remainder_outside_cv_inventory)[:10])
        )
    overlap = selected_cv_ids & remainder_ids
    if overlap:
        errors.append(
            _report_category_text('selected cs.CV papers and cv_daily_remainder overlap: ')
            + ", ".join(sorted(overlap)[:10])
        )

    expected_unique: int | None = None
    coverage = digest.get("retrieval_coverage")
    if isinstance(coverage, list):
        for entry in coverage:
            if isinstance(entry, dict) and entry.get("category") == REPORT_CATEGORY:
                batches = entry.get("batches")
                has_validated_announcement = isinstance(batches, list) and any(
                    isinstance(batch, dict)
                    and batch.get("source") == "arxiv_announcement"
                    and batch.get("inventory_validated") is True
                    for batch in batches
                )
                value = entry.get("unique_count")
                if has_validated_announcement and isinstance(value, int) and value >= 0:
                    expected_unique = value
                break
    if expected_unique is not None:
        missing_source_ids = {
            str(paper.get("arxiv_id"))
            for paper in [*selected, *remainder_papers]
            if isinstance(paper, dict)
            and paper.get("arxiv_id")
            and not isinstance(paper.get("query_sources"), list)
        }
        if missing_source_ids:
            errors.append(
                "announcement-batch delivery papers must retain query_sources: "
                + ", ".join(sorted(missing_source_ids)[:10])
            )
        exclusion_stats = digest.get("exclusion_stats")
        cs_cv_hidden = (
            exclusion_stats.get("cs_cv_total_hidden")
            if isinstance(exclusion_stats, dict)
            else None
        )
        if not isinstance(cs_cv_hidden, int) or cs_cv_hidden < 0:
            errors.append(
                "digest.exclusion_stats.cs_cv_total_hidden must be a non-negative "
                "integer for announcement-batch coverage"
            )
            cs_cv_hidden = 0
        expected_delivered = expected_unique - cs_cv_hidden
        if digest.get("schema_version") == SCHEMA_VERSION:
            # Original screening gives each inventory paper one exclusive
            # classification; hidden and already_known cannot double-count it.
            expected_delivered -= digest["report_already_known_count"]
        if expected_delivered < 0:
            errors.append(_report_category_text('cs.CV hidden and already-known counts cannot exceed announced inventory'))
            expected_delivered = 0
        delivered_unique = len(selected_cv_ids | remainder_ids)
        if delivered_unique != expected_delivered:
            errors.append(
                (_report_category_text('selected cs.CV plus cv_daily_remainder must cover every non-hidden announced cs.CV paper (') + f'{delivered_unique}' + ' delivered, ' + f'{expected_unique}' + ' announced, ' + f'{cs_cv_hidden}' + ' hidden)')
            )
    return errors


def normalize_arxiv_id(identifier: str, pdf_url: str = "") -> tuple[str, int | None]:
    identifier_match = ARXIV_ID_RE.search(str(identifier))
    url_match = ARXIV_ID_RE.search(str(pdf_url))
    match = identifier_match or url_match
    if not match:
        raise DigestValidationError(f"cannot parse arXiv ID from {identifier!r} / {pdf_url!r}")
    base_id = match.group(1)
    versions = [
        int(candidate.group(2))
        for candidate in (identifier_match, url_match)
        if candidate and candidate.group(2)
    ]
    return base_id, max(versions) if versions else None


def merge_unique(left: Any, right: Any) -> list[Any]:
    result: list[Any] = []
    for value in list(left or []) + list(right or []):
        if value not in result:
            result.append(value)
    return result


def version_rank(version: int | None) -> int:
    return version if isinstance(version, int) else -1


def deduplicate_candidates(
    candidates: list[dict[str, Any]],
    sent_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    sent_papers = (sent_state or {}).get("papers", {})
    if not isinstance(sent_papers, dict):
        raise DigestValidationError("sent state papers must be an object")
    by_id: dict[str, dict[str, Any]] = {}
    rejected: list[dict[str, Any]] = []

    for raw in candidates:
        if not isinstance(raw, dict):
            raise DigestValidationError("each candidate must be an object")
        paper = copy.deepcopy(raw)
        base_id, parsed_version = normalize_arxiv_id(
            str(paper.get("arxiv_id") or paper.get("id") or ""),
            str(paper.get("pdf_url") or paper.get("url") or ""),
        )
        explicit_version = paper.get("version")
        if explicit_version is not None and not isinstance(explicit_version, int):
            raise DigestValidationError(f"version must be integer or null for {base_id}")
        version = explicit_version if explicit_version is not None else parsed_version
        paper["arxiv_id"] = base_id
        paper["version"] = version
        paper["categories"] = merge_unique([], paper.get("categories", []))
        paper["query_sources"] = merge_unique([], paper.get("query_sources", []))
        paper["announcement_types"] = merge_unique(
            paper.get("announcement_types", []),
            [paper["announcement_type"]] if paper.get("announcement_type") else [],
        )

        prior = by_id.get(base_id)
        if prior is None:
            by_id[base_id] = paper
            continue
        merged_categories = merge_unique(prior.get("categories"), paper.get("categories"))
        merged_sources = merge_unique(prior.get("query_sources"), paper.get("query_sources"))
        merged_announcement_types = merge_unique(
            prior.get("announcement_types"),
            paper.get("announcement_types"),
        )
        if version_rank(version) > version_rank(prior.get("version")):
            by_id[base_id] = paper
        by_id[base_id]["categories"] = merged_categories
        by_id[base_id]["query_sources"] = merged_sources
        by_id[base_id]["announcement_types"] = merged_announcement_types

    eligible: list[dict[str, Any]] = []
    for base_id, paper in by_id.items():
        sent = sent_papers.get(base_id)
        if sent is None:
            paper["delivery_status"] = "new"
            eligible.append(paper)
            continue
        if not isinstance(sent, dict):
            raise DigestValidationError(f"sent state entry must be an object: {base_id}")
        current_version = paper.get("version")
        sent_version = sent.get("latest_sent_version")
        announcement_date = paper.get("announcement_date")
        sent_announcement_date = sent.get("latest_sent_announcement_date")
        if (
            isinstance(current_version, int)
            and isinstance(sent_version, int)
            and current_version > sent_version
        ):
            paper["delivery_status"] = "updated"
            eligible.append(paper)
        elif (
            "replacement" in paper.get("announcement_types", [])
            and isinstance(announcement_date, str)
            and (
                not isinstance(sent_announcement_date, str)
                or announcement_date > sent_announcement_date
            )
        ):
            paper["delivery_status"] = "updated"
            eligible.append(paper)
        else:
            rejected.append(
                {
                    "arxiv_id": base_id,
                    "version": current_version,
                    "reason": "already_sent_same_or_newer_version",
                }
            )

    eligible.sort(
        key=lambda item: (
            str(item.get("published") or item.get("submitted_or_updated") or ""),
            str(item.get("arxiv_id") or ""),
            version_rank(item.get("version")),
        ),
        reverse=True,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "input_count": len(candidates),
        "unique_count": len(by_id),
        "eligible": eligible,
        "excluded": rejected,
    }


SCREENING_PAGE_FIELDS = (
    "arxiv_id",
    "version",
    "title",
    "authors",
    "categories",
    "query_sources",
    "announcement_date",
    "announcement_types",
    "submitted_or_updated",
    "arxiv_url",
    "pdf_url",
    "delivery_status",
    "screening_scope",
    "abstract",
)
SCREENING_PRIORITY_CLASSES = (
    "focus_candidate",
    "watch_candidate",
    "browse",
    "exclude",
)
SEMANTIC_EXCLUSION_REASONS = (
    "configured_primary_exclusion",
    "configured_secondary_exclusion",
)
SELECTED_ENRICHMENT_FIELDS = (
    "recommendation",
    "core_conclusion",
    "research_problem",
    "method_overview",
    "contributions",
    "research_relation",
    "transferable_ideas",
    "limitations",
    "worth_reading",
    "follow_up",
    "evidence_level",
)
DETAILED_REMAINDER_ENRICHMENT_FIELDS = (
    "research_problem",
    "method_overview",
    "contributions",
)
SCREENING_DECISION_FIELDS = (
    "arxiv_id",
    "priority_class",
    "relevance_score",
    "topic_group",
    "core_conclusion",
    "evidence_level",
    "semantic_exclusion_reason",
)
EVIDENCE_LEVELS = ("abstract", "full_text")


def _json_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _json_sha256(value: dict[str, Any]) -> str:
    return hashlib.sha256(_json_bytes(value)).hexdigest()


def _validate_screening_checkpoint(
    batch: dict[str, Any],
    category: str,
    expected_cursor: str | None,
    *, root: Path | None = None,
) -> dict[str, Any]:
    """Validate one durable MCP announcement checkpoint for offline screening."""

    if batch.get("category") != category:
        raise DigestValidationError(
            f"announcement checkpoint category mismatch for {category}"
        )
    if batch.get("source") != "arxiv_announcement":
        raise DigestValidationError(
            f"announcement checkpoint source mismatch for {category}"
        )
    if batch.get("requested_cursor_date") != expected_cursor:
        raise DigestValidationError(
            f"announcement checkpoint cursor mismatch for {category}: expected "
            f"{expected_cursor!r}, received {batch.get('requested_cursor_date')!r}"
        )
    announcement_date = batch.get("announcement_date")
    if not isinstance(announcement_date, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}", announcement_date
    ):
        raise DigestValidationError(
            f"announcement checkpoint date is invalid for {category}"
        )
    listing_url = batch.get("listing_url")
    valid_listing_urls = {
        announcement_listing_url(category),
        announcement_listing_url(category).split("?", 1)[0],
        announcement_listing_url(category, announcement_date),
        announcement_listing_url(category, announcement_date).replace(
            "https://arxiv.org/", f"{_CENTRAL_ARXIV.ARXIV_EXPORT_BASE_URL}/", 1,
        ),
    }
    if listing_url not in valid_listing_urls:
        raise DigestValidationError(
            f"announcement checkpoint listing URL mismatch for {category}"
        )
    if expected_cursor is None:
        expected_action = "process_migration_batch"
    elif announcement_date == expected_cursor:
        expected_action = "already_processed"
    elif announcement_date > expected_cursor:
        expected_action = "process_next_batch"
        cursor_day = datetime.fromisoformat(expected_cursor).date()
        announcement_day = datetime.fromisoformat(announcement_date).date()
        deferred = deferred_announcement_dates(root) if root is not None else ()
        business_days = 0
        candidate_day = cursor_day + timedelta(days=1)
        while candidate_day <= announcement_day:
            if (candidate_day.weekday() < 5
                    and (candidate_day == announcement_day
                         or candidate_day.isoformat() not in deferred)):
                business_days += 1
            candidate_day += timedelta(days=1)
        if business_days > 1:
            raise DigestValidationError(
                f"announcement checkpoint has an unrecoverable cursor gap for {category}"
            )
    else:
        raise DigestValidationError(
            f"announcement checkpoint date {announcement_date} precedes cursor "
            f"{expected_cursor} for {category}"
        )
    if batch.get("cursor_action") != expected_action:
        raise DigestValidationError(
            f"announcement checkpoint cursor action mismatch for {category}: "
            f"expected {expected_action}"
        )

    coverage = announcement_batch_coverage(batch)
    if batch.get("coverage") != coverage:
        raise DigestValidationError(
            f"announcement checkpoint coverage mismatch for {category}"
        )
    papers = batch.get("papers")
    assert isinstance(papers, list)
    counts = batch.get("counts")
    assert isinstance(counts, dict)
    section_counts = [
        counts.get("new_submissions"),
        counts.get("cross_lists"),
        counts.get("replacements"),
    ]
    if any(not isinstance(value, int) or value < 0 for value in section_counts):
        raise DigestValidationError(
            f"announcement checkpoint section counts are invalid for {category}"
        )
    if counts.get("total") != sum(section_counts):
        raise DigestValidationError(
            f"announcement checkpoint section counts do not sum for {category}"
        )
    seen_ids: set[str] = set()
    for index, paper in enumerate(papers):
        label = f"{category} announcement paper[{index}]"
        if not isinstance(paper, dict):
            raise DigestValidationError(f"{label} must be an object")
        errors = validate_announcement_identity(paper, label)
        if errors:
            raise DigestValidationError("; ".join(errors))
        try:
            base_id, parsed_version = normalize_arxiv_id(
                str(paper.get("arxiv_id") or paper.get("id") or ""),
                str(paper.get("pdf_url") or paper.get("url") or ""),
            )
        except DigestValidationError as exc:
            raise DigestValidationError(f"{label}: {exc}") from exc
        if base_id in seen_ids:
            raise DigestValidationError(
                f"announcement checkpoint contains duplicate ID {base_id} for {category}"
            )
        seen_ids.add(base_id)
        if paper.get("version") is not None and paper.get("version") != parsed_version:
            raise DigestValidationError(
                f"{label}.version must match the PDF URL version"
            )
        if paper.get("announcement_date") != announcement_date:
            raise DigestValidationError(
                f"{label}.announcement_date does not match its checkpoint"
            )
        sources = paper.get("query_sources")
        if not isinstance(sources, list) or category not in sources:
            raise DigestValidationError(
                f"{label}.query_sources must contain {category}"
            )
        for field in ("title", "abstract", "arxiv_url", "pdf_url"):
            if not isinstance(paper.get(field), str) or not paper[field].strip():
                raise DigestValidationError(f"{label}.{field} must be non-empty")
        for field in ("authors", "categories"):
            if not isinstance(paper.get(field), list) or not paper[field]:
                raise DigestValidationError(f"{label}.{field} must be a non-empty array")
    if len(seen_ids) != coverage["unique_count"]:
        raise DigestValidationError(
            f"announcement checkpoint unique count mismatch for {category}"
        )
    return coverage


def _run_date_key(run_id: str) -> str | None:
    """Return a YYYYMMDD key for a date-like stable run identifier."""

    normalized = str(run_id).strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", normalized):
        candidate = normalized.replace("-", "")
    else:
        matches = list(
            re.finditer(
                r"(?<!\d)(?:(20\d{2})-(\d{2})-(\d{2})|(20\d{6}))(?!\d)",
                normalized,
            )
        )
        if not matches:
            candidate = ""
        else:
            match = matches[-1]
            candidate = match.group(4) or "".join(match.groups()[:3])
    if not candidate:
        return None
    try:
        datetime.strptime(candidate, "%Y%m%d")
    except ValueError:
        return None
    return candidate


def _retarget_run_id(run_id: str, target_date: str) -> str:
    """Bind a date-like run identifier to one announcement date."""

    normalized = str(run_id).strip()
    target_key = target_date.replace("-", "")
    if _run_date_key(target_date) != target_key:
        raise DigestValidationError("target announcement date must use YYYY-MM-DD")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", normalized):
        return target_date
    matches = list(
        re.finditer(
            r"(?<!\d)(?:(20\d{2})-(\d{2})-(\d{2})|(20\d{6}))(?!\d)",
            normalized,
        )
    )
    if not matches:
        raise DigestValidationError(
            "a backlog run ID must contain a replaceable YYYYMMDD or YYYY-MM-DD date"
        )
    match = matches[-1]
    replacement = target_date if "-" in match.group(0) else target_key
    return normalized[: match.start()] + replacement + normalized[match.end() :]


def _announcement_backlog_plan(
    cursors: dict[str, str | None],
    requested_run_id: str,
    *,
    observed_at: datetime | None = None,
    deferred_dates: tuple[str, ...] = (),
) -> dict[str, Any] | None:
    """Plan missing weekday announcement dates from the committed cursor."""

    requested_key = _run_date_key(requested_run_id)
    if requested_key is None:
        return None
    values = {cursors[category] for category in TRACKED_CATEGORIES}
    if values == {None}:
        return None
    if None in values or len(values) != 1:
        # The phase validator owns reporting a corrupt mixed-cursor state. It must
        # not be disguised as a normal backlog plan.
        return None
    committed_text = str(next(iter(values)))
    committed = datetime.fromisoformat(committed_text).date()
    if committed.weekday() >= 5:
        raise DigestValidationError(
            f"committed announcement cursor {committed_text} falls on a weekend"
        )
    requested = datetime.strptime(requested_key, "%Y%m%d").date()
    if committed >= requested:
        return {
            "requested_announcement_date": requested.isoformat(),
            "official_available_through_date": committed.isoformat(),
            "planned_through_announcement_date": requested.isoformat(),
            "latest_committed_announcement_date": committed.isoformat(),
            "pending_announcement_dates": [],
            "calendar_basis": "weekday_only",
            "selection_policy": "oldest_uncommitted_first",
            "availability_basis": "committed_cursor_proof",
        }
    officially_available = datetime.fromisoformat(
        expected_announcement_date(observed_at)
    ).date()
    through = min(requested, officially_available)
    pending: list[str] = []
    candidate = committed + timedelta(days=1)
    while candidate <= through:
        if candidate.weekday() < 5 and candidate.isoformat() not in deferred_dates:
            pending.append(candidate.isoformat())
        candidate += timedelta(days=1)
    return {
        "requested_announcement_date": requested.isoformat(),
        "official_available_through_date": officially_available.isoformat(),
        "planned_through_announcement_date": through.isoformat(),
        "latest_committed_announcement_date": committed.isoformat(),
        "pending_announcement_dates": pending,
        "calendar_basis": "weekday_only",
        "selection_policy": "oldest_uncommitted_first",
        "availability_basis": "live_arxiv_schedule",
    }


def _committed_cursor_consistency_error(
    cursors: dict[str, str | None],
) -> str | None:
    values = {cursors[category] for category in TRACKED_CATEGORIES}
    return "divergent_committed_cursors" if len(values) > 1 else None


ANNOUNCEMENT_TARGET_SCHEMA_VERSION = 1
ANNOUNCEMENT_TARGET_FILENAME = "announcement-target-v1.json"
BACKLOG_DRAIN_CONTRACT_VERSION = 1


def announcement_target_manifest_path(root: Path, run_id: str) -> Path:
    """Return the immutable announcement-target marker for one stable run."""
    configure_public_runtime(root)

    return announcement_batch_output_path(
        root.resolve(), run_id, TRACKED_CATEGORIES[0]
    ).parent / ANNOUNCEMENT_TARGET_FILENAME


def _validate_announcement_target_manifest(
    value: dict[str, Any],
    run_id: str,
    cursors: dict[str, str | None],
    *, root: Path | None = None,
) -> str:
    if value.get("schema_version") != ANNOUNCEMENT_TARGET_SCHEMA_VERSION:
        raise DigestValidationError("unsupported announcement target manifest schema")
    if value.get("run_id") != run_id:
        raise DigestValidationError("announcement target manifest run_id mismatch")
    target_date = value.get("target_announcement_date")
    if not isinstance(target_date, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}", target_date
    ):
        raise DigestValidationError(
            "announcement target manifest date must use YYYY-MM-DD"
        )
    if datetime.fromisoformat(target_date).date().weekday() >= 5:
        raise DigestValidationError(
            "announcement target manifest date falls on a weekend"
        )
    requested_cursors = value.get("requested_cursors")
    expected_cursors = {
        category: cursors[category] for category in TRACKED_CATEGORIES
    }
    if requested_cursors != expected_cursors:
        raise DigestValidationError(
            "announcement target manifest cursor snapshot mismatch"
        )
    if not isinstance(value.get("created_at"), str) or not value["created_at"].strip():
        raise DigestValidationError("announcement target manifest created_at is missing")
    actions = {
        announcement_cursor_action(
            cursors[category], target_date, enforce_current=False,
            deferred_dates=deferred_announcement_dates(root) if root is not None else ()
        )
        for category in TRACKED_CATEGORIES
    }
    if actions not in ({"process_next_batch"}, {"process_migration_batch"}):
        raise DigestValidationError(
            "announcement target manifest is not the immediate uncommitted batch"
        )
    return target_date


def store_announcement_target_manifest(
    root: Path,
    run_id: str,
    target_date: str,
    cursors: dict[str, str | None],
) -> tuple[dict[str, Any], Path, bool]:
    """Create one immutable phase target before the first network request."""
    configure_public_runtime(root)

    path = announcement_target_manifest_path(root.resolve(), run_id)
    if path.is_file():
        existing = read_json(path)
        existing_target = _validate_announcement_target_manifest(
            existing, run_id, cursors, root=root,
        )
        if existing_target != target_date:
            raise DigestValidationError(
                "announcement target manifest cannot be retargeted"
            )
        return existing, path, True
    value = {
        "schema_version": ANNOUNCEMENT_TARGET_SCHEMA_VERSION,
        "run_id": run_id,
        "target_announcement_date": target_date,
        "requested_cursors": {
            category: cursors[category] for category in TRACKED_CATEGORIES
        },
        "calendar_basis": "weekday_only",
        "created_at": utc_now(),
    }
    _validate_announcement_target_manifest(value, run_id, cursors, root=root)
    atomic_write_json(path, value)
    stored = read_json(path)
    _validate_announcement_target_manifest(stored, run_id, cursors, root=root)
    return stored, path, False


RUN_PROGRESS_ARTIFACTS = (
    "review-manifest-v3.json",
    "cv-summary-manifest-v4.json",
    "digest-v4.json",
)


def store_announcement_checkpoint(
    root: Path,
    run_id: str,
    category: str,
    batch: dict[str, Any],
    expected_cursor: str | None,
) -> tuple[dict[str, Any], Path, bool]:
    """Atomically create or safely repair one immutable phase checkpoint."""
    configure_public_runtime(root)

    root = root.resolve()
    _validate_screening_checkpoint(batch, category, expected_cursor, root=root)
    output_path = announcement_batch_output_path(root, run_id, category)
    if output_path.is_file():
        try:
            existing = read_json(output_path)
            _validate_screening_checkpoint(existing, category, expected_cursor, root=root)
        except (DigestValidationError, OSError, ValueError):
            run_dir = output_path.parent
            downstream = [
                filename
                for filename in RUN_PROGRESS_ARTIFACTS
                if (run_dir / filename).is_file()
            ]
            if downstream:
                raise DigestValidationError(
                    f"cannot repair {category} announcement checkpoint after "
                    f"downstream progress exists: {', '.join(downstream)}"
                )
        else:
            # Retrieval timestamps and response headers are volatile. Once a
            # checkpoint validates, retain its exact bytes as the run evidence.
            return existing, output_path, True

    atomic_write_json(output_path, batch)
    stored = read_json(output_path)
    _validate_screening_checkpoint(stored, category, expected_cursor, root=root)
    return stored, output_path, False


def _run_progress_profile(
    root: Path,
    run_id: str,
    cursors: dict[str, str | None],
) -> dict[str, Any]:
    """Measure only validated or phase-owned progress, never arbitrary files."""

    run_dir = root.resolve() / "runs" / run_id
    valid_count = 0
    checkpoint_dates: set[str] = set()
    progress_times: list[float] = []
    for category in TRACKED_CATEGORIES:
        path = announcement_batch_output_path(root.resolve(), run_id, category)
        if not path.is_file():
            continue
        try:
            batch = read_json(path)
            _validate_screening_checkpoint(batch, category, cursors[category], root=root)
        except (DigestValidationError, OSError, ValueError):
            continue
        valid_count += 1
        checkpoint_dates.add(str(batch["announcement_date"]))
        progress_times.append(path.stat().st_mtime)

    target_manifest_valid = False
    manifest_target: str | None = None
    target_path = announcement_target_manifest_path(root.resolve(), run_id)
    if target_path.is_file():
        try:
            manifest_target = _validate_announcement_target_manifest(
                read_json(target_path), run_id, cursors, root=root,
            )
        except (DigestValidationError, OSError, ValueError):
            pass
        else:
            target_manifest_valid = True
            progress_times.append(target_path.stat().st_mtime)

    phase_rank = 0
    for rank, filename in enumerate(RUN_PROGRESS_ARTIFACTS, start=1):
        path = run_dir / filename
        if path.is_file():
            phase_rank = rank
            progress_times.append(path.stat().st_mtime)
    checkpoint_target = (
        next(iter(checkpoint_dates)) if len(checkpoint_dates) == 1 else None
    )
    target_announcement_date = manifest_target or checkpoint_target
    if (
        manifest_target is not None
        and checkpoint_target is not None
        and manifest_target != checkpoint_target
    ):
        target_announcement_date = None
    return {
        "run_id": run_id,
        "valid_checkpoint_count": valid_count,
        "target_manifest_valid": target_manifest_valid,
        "target_announcement_date": target_announcement_date,
        "target_announcement_date_source": (
            "phase_manifest"
            if manifest_target is not None
            else "validated_checkpoint"
            if checkpoint_target is not None
            else None
        ),
        "phase_rank": phase_rank,
        "has_progress": target_manifest_valid or valid_count > 0 or phase_rank > 0,
        "score": (phase_rank, valid_count, int(target_manifest_valid)),
        "last_progress_mtime": max(progress_times) if progress_times else None,
    }


def _select_progressed_run(
    profiles: list[dict[str, Any]],
    *,
    ambiguity_label: str,
) -> str | None:
    progressed = [profile for profile in profiles if profile["has_progress"]]
    if not progressed:
        return None
    best_score = max(profile["score"] for profile in progressed)
    best = [profile for profile in progressed if profile["score"] == best_score]
    if len(best) != 1:
        names = ", ".join(sorted(str(profile["run_id"]) for profile in best))
        raise DigestValidationError(f"{ambiguity_label}: {names}")
    return str(best[0]["run_id"])


def _last_committed_run_date_key(root: Path) -> str | None:
    path = root.resolve() / "last-successful-run.json"
    if not path.is_file():
        return None
    state = read_json(path)
    keys: list[str] = []
    retrieval_window = state.get("retrieval_window")
    for value in (
        state.get("run_id"),
        state.get("report_date"),
        retrieval_window.get("to") if isinstance(retrieval_window, dict) else None,
    ):
        key = _run_date_key(str(value or ""))
        if key is not None:
            keys.append(key)
    cursors = state.get("announcement_cursors")
    if isinstance(cursors, dict):
        for value in cursors.values():
            key = _run_date_key(str(value or ""))
            if key is not None:
                keys.append(key)
    return max(keys) if keys else None


def resolve_stable_run_id(root: Path, requested_run_id: str) -> str:
    """Resolve aliases and select the oldest uncommitted announcement date."""
    configure_public_runtime(root)

    normalized = str(requested_run_id).strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,127}", normalized):
        raise DigestValidationError("stable run ID is invalid")
    date_key = _run_date_key(normalized)
    if date_key is None:
        return normalized

    root = root.resolve()
    runs_root = root / "runs"
    cursors = _committed_announcement_cursors(root.resolve())
    backlog = _announcement_backlog_plan(cursors, normalized, deferred_dates=deferred_announcement_dates(root))
    all_candidates = (
        sorted(
            (path for path in runs_root.iterdir() if path.is_dir()),
            key=lambda path: path.name,
        )
        if runs_root.is_dir()
        else []
    )

    if backlog is not None and backlog["pending_announcement_dates"]:
        target_date = str(backlog["pending_announcement_dates"][0])
        target_key = target_date.replace("-", "")
        target_run_id = _retarget_run_id(normalized, target_date)
        profiles = [
            _run_progress_profile(root, path.name, cursors)
            for path in all_candidates
        ]
        target_profiles = [
            profile
            for profile in profiles
            if (
                (
                    profile.get("target_announcement_date_source")
                    == "phase_manifest"
                    and profile.get("target_announcement_date") == target_date
                )
                or (
                    _run_date_key(str(profile["run_id"])) == target_key
                    and profile.get("target_announcement_date")
                    in (None, target_date)
                )
            )
        ]
        recovered = _select_progressed_run(
            target_profiles,
            ambiguity_label=(
                "multiple oldest uncommitted Daily Digest runs have equal durable "
                "progress"
            ),
        )
        if recovered is not None:
            return recovered

        target_candidates = [
            path for path in all_candidates if _run_date_key(path.name) == target_key
        ]
        generated = runs_root / target_run_id
        if generated.is_dir():
            return target_run_id
        if len(target_candidates) == 1:
            return target_candidates[0].name
        if len(target_candidates) > 1:
            names = ", ".join(path.name for path in target_candidates)
            raise DigestValidationError(
                "multiple oldest-date Daily Digest run directories are ambiguous: "
                f"{names}"
            )
        return target_run_id

    candidates = [
        path for path in all_candidates if _run_date_key(path.name) == date_key
    ]
    exact = runs_root / normalized
    same_day = _select_progressed_run(
        [
            _run_progress_profile(root.resolve(), path.name, cursors)
            for path in candidates
        ],
        ambiguity_label=(
            "multiple same-day Daily Digest runs have equal durable progress"
        ),
    )
    if same_day is not None:
        return same_day

    committed_key = _last_committed_run_date_key(root.resolve())
    older_profiles: list[tuple[str, dict[str, Any]]] = []
    for path in all_candidates:
        candidate_key = _run_date_key(path.name)
        if candidate_key in {d.replace("-", "") for d in deferred_announcement_dates(root)}:
            continue
        if candidate_key is None or candidate_key >= date_key:
            continue
        if committed_key is not None and candidate_key <= committed_key:
            continue
        profile = _run_progress_profile(root.resolve(), path.name, cursors)
        if profile["has_progress"]:
            older_profiles.append((candidate_key, profile))
    if older_profiles:
        oldest_key = min(candidate_key for candidate_key, _profile in older_profiles)
        recovered = _select_progressed_run(
            [
                profile
                for candidate_key, profile in older_profiles
                if candidate_key == oldest_key
            ],
            ambiguity_label=(
                "multiple oldest uncommitted Daily Digest runs have equal durable progress"
            ),
        )
        if recovered is not None:
            return recovered

    if exact.is_dir():
        return normalized
    if len(candidates) == 1:
        return candidates[0].name
    if len(candidates) > 1:
        names = ", ".join(path.name for path in candidates)
        raise DigestValidationError(
            f"multiple same-day Daily Digest run directories are ambiguous: {names}"
        )
    return normalized


def _committed_announcement_cursors(root: Path) -> dict[str, str | None]:
    last_path = root.resolve() / "last-successful-run.json"
    last_state = read_json(last_path) if last_path.is_file() else {}
    raw_cursors = last_state.get("announcement_cursors", {})
    if not isinstance(raw_cursors, dict):
        raise DigestValidationError(
            "last-successful-run.json announcement_cursors must be an object"
        )
    cursors: dict[str, str | None] = {}
    for category in TRACKED_CATEGORIES:
        value = raw_cursors.get(category)
        if value is None:
            cursors[category] = None
        elif isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            cursors[category] = value
        else:
            raise DigestValidationError(
                f"announcement cursor for {category} must be YYYY-MM-DD or null"
            )
    return cursors


def announcement_phase_status(root: Path, requested_run_id: str) -> dict[str, Any]:
    """Return compact validated checkpoint progress for one stable run."""
    configure_public_runtime(root)

    root = root.resolve()
    run_id = resolve_stable_run_id(root, requested_run_id)
    cursors = _committed_announcement_cursors(root)
    valid_categories: list[str] = []
    missing_categories: list[str] = []
    invalid_categories: dict[str, str] = {}
    announcement_dates: set[str] = set()
    cursor_actions: set[str] = set()
    progress_times: list[float] = []
    for category in TRACKED_CATEGORIES:
        path = announcement_batch_output_path(root, run_id, category)
        if not path.is_file():
            missing_categories.append(category)
            continue
        progress_times.append(path.stat().st_mtime)
        try:
            batch = read_json(path)
            _validate_screening_checkpoint(batch, category, cursors[category], root=root)
        except (DigestValidationError, OSError, ValueError) as exc:
            invalid_categories[category] = str(exc)[:300]
            continue
        valid_categories.append(category)
        announcement_dates.add(str(batch["announcement_date"]))
        cursor_actions.add(str(batch["cursor_action"]))

    run_dir = announcement_batch_output_path(root, run_id, TRACKED_CATEGORIES[0]).parent
    target_path = announcement_target_manifest_path(root, run_id)
    manifest_target: str | None = None
    target_manifest_error: str | None = None
    if target_path.is_file():
        progress_times.append(target_path.stat().st_mtime)
        try:
            manifest_target = _validate_announcement_target_manifest(
                read_json(target_path), run_id, cursors, root=root,
            )
        except (DigestValidationError, OSError, ValueError) as exc:
            target_manifest_error = str(exc)[:300]
    for filename in RUN_PROGRESS_ARTIFACTS:
        path = run_dir / filename
        if path.is_file():
            progress_times.append(path.stat().st_mtime)

    phase_error = _committed_cursor_consistency_error(cursors)
    if phase_error is None and target_manifest_error is not None:
        phase_error = "invalid_announcement_target_manifest"
    elif phase_error is None and len(announcement_dates) > 1:
        phase_error = "inconsistent_announcement_dates"
    elif (
        phase_error is None
        and "already_processed" in cursor_actions
        and len(cursor_actions) > 1
    ):
        phase_error = "mixed_cursor_actions"
    checkpoint_target = (
        next(iter(announcement_dates)) if len(announcement_dates) == 1 else None
    )
    if (
        phase_error is None
        and manifest_target is not None
        and checkpoint_target is not None
        and manifest_target != checkpoint_target
    ):
        phase_error = "announcement_target_mismatch"

    complete = (
        len(valid_categories) == len(TRACKED_CATEGORIES)
        and not missing_categories
        and not invalid_categories
        and len(announcement_dates) == 1
        and phase_error is None
    )
    target_announcement_date: str | None = None
    target_source: str | None = None
    if manifest_target is not None:
        target_announcement_date = manifest_target
        target_source = "phase_manifest"
    elif checkpoint_target is not None:
        target_announcement_date = checkpoint_target
        target_source = "validated_checkpoint"
    elif not announcement_dates:
        run_date_key = _run_date_key(run_id)
        if run_date_key is not None:
            candidate = datetime.strptime(run_date_key, "%Y%m%d").date().isoformat()
            try:
                candidate_actions = {
                    announcement_cursor_action(
                        cursors[category],
                        candidate,
                        enforce_current=False,
                        deferred_dates=deferred_announcement_dates(root),
                    )
                    for category in TRACKED_CATEGORIES
                }
            except (DigestValidationError, OfficialArxivFetchError):
                candidate_actions = set()
            if candidate_actions in (
                {"process_next_batch"},
                {"process_migration_batch"},
            ):
                target_announcement_date = candidate
                target_source = "validated_run_id"
    result: dict[str, Any] = {
        "run_id": run_id,
        "requested_run_id": str(requested_run_id).strip(),
        "announcement_complete": complete,
        "valid_categories": valid_categories,
        "missing_categories": missing_categories,
        "invalid_categories": invalid_categories,
        "needed_categories": [
            category
            for category in TRACKED_CATEGORIES
            if category in missing_categories or category in invalid_categories
        ],
        "announcement_dates": sorted(announcement_dates),
        "target_announcement_date": target_announcement_date,
        "target_announcement_date_source": target_source,
        "cursor_actions": sorted(cursor_actions),
        "phase_blocked": phase_error is not None,
        "phase_error": phase_error,
        "target_manifest_error": target_manifest_error,
        "has_progress": bool(progress_times),
        "next_action": (
            "prepare_review"
            if complete
            else "repair_announcement_phase"
            if phase_error is not None
            else "fetch_announcement_phase"
        ),
    }
    if progress_times:
        result["last_progress_at"] = (
            datetime.fromtimestamp(max(progress_times), timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        )
    return result


def run_resume_status(root: Path, requested_run_id: str) -> dict[str, Any]:
    """Return the next deterministic action without exposing bounded model pages."""
    configure_public_runtime(root)

    status = announcement_phase_status(root, requested_run_id)
    if not status["announcement_complete"]:
        status["phase"] = (
            "announcement_blocked"
            if status.get("phase_blocked")
            else "announcement_retrieval"
        )
        return status
    run_id = str(status["run_id"])
    run_dir = announcement_batch_output_path(root.resolve(), run_id, TRACKED_CATEGORIES[0]).parent
    if (run_dir / "digest-v4.json").is_file():
        status.update({"phase": "digest_ready", "next_action": "render"})
        return status
    if (run_dir / "review-manifest-v3.json").is_file():
        compact = review_status(root.resolve(), run_id)
        status.update(
            {
                "phase": compact.get("phase", "review"),
                "next_action": compact.get("next_action", "review-status"),
            }
        )
        return status
    status.update({"phase": "announcement_complete", "next_action": "prepare_review"})
    return status


def announcement_archive_path(root: Path, day: str, category: str) -> Path:
    # Validate before incorporating either value into a filesystem path.
    configure_public_runtime(root)
    announcement_listing_url(category, day)
    if datetime.fromisoformat(day).weekday() >= 5:
        raise DigestValidationError("announcement archive date falls on a weekend")
    return root.resolve() / "announcement-archive" / day / f"{category}.json"


def _archive_batch(batch: dict[str, Any], day: str, category: str) -> dict[str, Any]:
    if batch.get("announcement_date") != day:
        raise DigestValidationError("announcement archive date mismatch")
    value = copy.deepcopy(batch)
    # Archive identity is independent of committed delivery state. No cursor is
    # advanced or invented: these fields only validate the standalone inventory.
    value["requested_cursor_date"] = None
    value["cursor_action"] = "process_migration_batch"
    value["coverage"] = announcement_batch_coverage(value)
    _validate_screening_checkpoint(value, category, None)
    for kind, key in (("new", "new_submissions"), ("cross_list", "cross_lists"),
                      ("replacement", "replacements")):
        if sum(p.get("announcement_type") == kind for p in value["papers"]) != value["counts"][key]:
            raise DigestValidationError("announcement archive section inventory mismatch")
    return value


def load_announcement_archive(
    root: Path, day: str, category: str, cursor: str | None = None,
) -> dict[str, Any] | None:
    configure_public_runtime(root)
    path = announcement_archive_path(root, day, category)
    if not path.is_file():
        return None
    record = read_json(path)
    batch = record.get("batch")
    if (record.get("schema_version") != 1 or record.get("date") != day
            or record.get("category") != category or not isinstance(batch, dict)
            or record.get("sha256") != _json_sha256(batch)):
        raise DigestValidationError(f"invalid announcement archive identity/hash: {path}")
    batch = _archive_batch(batch, day, category)
    batch["requested_cursor_date"] = cursor
    batch["cursor_action"] = announcement_cursor_action(cursor, day, enforce_current=False, deferred_dates=deferred_announcement_dates(root))
    _validate_screening_checkpoint(batch, category, cursor, root=root)
    batch.setdefault("_retrieval", {})["archive_sha256"] = record["sha256"]
    return batch


def store_announcement_archive(root: Path, batch: dict[str, Any]) -> Path:
    configure_public_runtime(root)
    day, category = str(batch.get("announcement_date", "")), str(batch.get("category", ""))
    path = announcement_archive_path(root, day, category)
    value = _archive_batch(batch, day, category)
    if path.exists():
        load_announcement_archive(root, day, category)
        return path  # A validated snapshot is immutable, including its exact bytes.
    atomic_write_json(path, {
        "schema_version": 1, "date": day, "category": category,
        "saved_at": utc_now(), "sha256": _json_sha256(value), "batch": value,
    })
    load_announcement_archive(root, day, category)
    return path


def capture_current_announcements(
    root: Path, *, observed_at: datetime | None = None,
    priority_root: Path | None = None, gate: ArxivPriorityGate | None = None,
    fetcher: Any = None,
) -> dict[str, Any]:
    """Preserve the latest available inventories despite older delivery backlog."""
    configure_public_runtime(root)
    root = root.resolve()
    day = expected_announcement_date(observed_at)
    coordination_root = (priority_root or root / "priority-gate").resolve()
    session_gate = gate or ArxivPriorityGate(coordination_root)
    fetch_batch = fetcher or fetch_announcement_batch
    result: dict[str, Any] = {
        "date": day, "capture_complete": False, "valid_categories": [],
        "fetched_categories": [], "errors": {}, "delivery_state_changed": False,
    }
    with _exclusive_gate_state_lock(root / "announcement-phase.lock", timeout_seconds=300):
        missing = []
        for category in TRACKED_CATEGORIES:
            try:
                cached = load_announcement_archive(root, day, category)
                if cached is None:
                    missing.append(category)
                else:
                    result["valid_categories"].append(category)
            except (DigestValidationError, OSError, ValueError) as exc:
                result["errors"][category] = {"detail": str(exc)}
        if missing:
            session = session_gate.begin_digest_session("archive-" + day, wait_timeout_seconds=300)
            token = str(session.get("session_token", ""))
            try:
                if not token or session.get("run_id") != "archive-" + day:
                    raise DigestValidationError("archive session identity mismatch")
                for category in missing:
                    try:
                        batch = fetch_batch(
                            root, category, cursor_date=None, target_date=day,
                            observed_at=observed_at, priority_root=coordination_root,
                            priority_gate=session_gate, digest_session_token=token,
                        )
                        _archive_batch(batch, day, category)
                        store_announcement_archive(root, batch)
                        result["valid_categories"].append(category)
                        result["fetched_categories"].append(category)
                    except (OfficialArxivFetchError, DigestValidationError, OSError, ValueError) as exc:
                        result["errors"][category] = (
                            exc.as_record() if isinstance(exc, OfficialArxivFetchError)
                            else {"detail": str(exc)}
                        )
            finally:
                if token:
                    session_gate.end_digest_session(token)
        result["capture_complete"] = len(result["valid_categories"]) == len(TRACKED_CATEGORIES)
        result["checked_at"] = utc_now()
        atomic_write_json(root / "announcement-archive" / day / "capture-status.json", result)
    return result


def fetch_announcement_phase(
    root: Path,
    requested_run_id: str,
    *,
    priority_root: Path | None = None,
    gate: ArxivPriorityGate | None = None,
    fetcher: Any = None,
    session_wait_timeout_seconds: float = 300.0,
) -> dict[str, Any]:
    """Fetch every missing announcement checkpoint inside one owned digest session."""
    configure_public_runtime(root)

    root = root.resolve()
    initialize_runtime(root)
    pending_path = root / "pending-run.json"
    if pending_path.is_file():
        pending = read_json(pending_path)
        if pending.get("delivery_status") in (None, "pending", "committing"):
            raise DigestValidationError(
                "an uncommitted delivery must be recovered before fetching another "
                "announcement phase"
            )
    backlog_fields = _backlog_status_fields(root, requested_run_id)
    if backlog_fields and not backlog_fields["pending_announcement_dates"]:
        return {
            "run_id": str(requested_run_id).strip(),
            "action": "no_announcement_due",
            "phase": "idle",
            "next_action": None,
            "announcement_complete": False,
            "reused": True,
            "fetched_categories": [],
            **backlog_fields,
        }
    coordination_root = (priority_root or Path(_require_public_configuration()["coordination_root"])).resolve()
    session_gate = gate or ArxivPriorityGate(coordination_root)
    fetch_batch = fetcher or fetch_announcement_batch
    with _exclusive_gate_state_lock(
        root / "announcement-phase.lock",
        timeout_seconds=session_wait_timeout_seconds,
    ):
        status = announcement_phase_status(root, requested_run_id)
        run_id = str(status["run_id"])
        if status.get("phase_blocked"):
            raise DigestValidationError(
                "announcement phase is blocked: "
                f"{status.get('phase_error') or 'unknown_phase_inconsistency'}"
            )
        if status["announcement_complete"]:
            result = run_resume_status(root, run_id)
            result.update({"reused": True, "fetched_categories": []})
            if str(requested_run_id).strip() != run_id:
                result["requested_run_id"] = str(requested_run_id).strip()
            return result

        cursors = _committed_announcement_cursors(root)
        target_date = status.get("target_announcement_date")
        if target_date is not None:
            target_date = str(target_date)
            store_announcement_target_manifest(
                root, run_id, target_date, cursors
            )
        fetched_categories: list[str] = []
        restored_categories: list[str] = []
        session: dict[str, Any] = {}
        session_token = ""
        session_started = False
        phase_error: BaseException | None = None
        try:
            session = session_gate.begin_digest_session(
                run_id,
                wait_timeout_seconds=session_wait_timeout_seconds,
            )
            session_started = True
            session_token = str(session.get("session_token", "")).strip()
            if not session_token:
                raise DigestValidationError(
                    "priority gate began a digest session without a session token"
                )
            if str(session.get("run_id", "")).strip() != run_id:
                raise DigestValidationError(
                    "priority gate returned a digest session for the wrong run"
                )
            for category in status["needed_categories"]:
                batch = (load_announcement_archive(root, target_date, category, cursors[category])
                         if target_date is not None else None)
                from_archive = batch is not None
                if batch is None:
                    batch = fetch_batch(
                        root,
                        category,
                        cursor_date=cursors[category],
                        target_date=target_date,
                        priority_root=coordination_root,
                        priority_gate=session_gate,
                        digest_session_token=session_token,
                    )
                batch_date = str(batch.get("announcement_date", "")).strip()
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", batch_date):
                    raise DigestValidationError(
                        f"announcement batch date is invalid for {category}"
                    )
                if target_date is None:
                    target_date = batch_date
                    store_announcement_target_manifest(
                        root, run_id, target_date, cursors
                    )
                elif batch_date != target_date:
                    raise DigestValidationError(
                        f"announcement phase target is {target_date}, but {category} "
                        f"returned {batch_date}"
                    )
                cursor_action = str(batch.get("cursor_action", "")).strip()
                if not cursor_action:
                    raise DigestValidationError(
                        f"announcement batch is missing cursor_action for {category}"
                    )
                complete_batch = dict(batch)
                complete_batch["requested_cursor_date"] = cursors[category]
                complete_batch["cursor_action"] = cursor_action
                complete_batch["coverage"] = announcement_batch_coverage(batch)
                complete_batch["version_hydration"] = {
                    "requested": False,
                    "complete": True,
                }
                _stored_batch, _output_path, checkpoint_reused = (
                    store_announcement_checkpoint(
                        root,
                        run_id,
                        category,
                        complete_batch,
                        cursors[category],
                    )
                )
                if not checkpoint_reused:
                    (restored_categories if from_archive else fetched_categories).append(category)
        except BaseException as exc:
            phase_error = exc
            raise
        finally:
            if session_started:
                try:
                    session_gate.end_digest_session(session_token)
                except Exception as release_error:
                    if phase_error is None:
                        raise
                    phase_error.add_note(
                        "digest session cleanup also failed: "
                        f"{type(release_error).__name__}: {release_error}"
                    )

        result = run_resume_status(root, run_id)
        result.update(
            {
                "reused": False,
                "session_resumed": bool(session.get("resumed")),
                "fetched_categories": fetched_categories,
                "restored_categories": restored_categories,
            }
        )
        if not result["announcement_complete"]:
            detail = result.get("phase_error") or "incomplete coverage"
            raise DigestValidationError(
                f"announcement phase ended without complete coverage: {detail}"
            )
        return result


REVIEW_PAGE_FIELDS = (
    "arxiv_id",
    "title",
    "abstract",
    "categories",
    "query_sources",
    "announcement_date",
    "announcement_types",
    "submitted_or_updated",
    "local_topic_group",
    "prefilter_score",
    "prefilter_reasons",
)
REVIEW_DECISION_FIELDS = (
    "arxiv_id",
    "relevance_score",
    "topic_group",
    "core_conclusion",
    "research_problem",
    "method_overview",
    "contributions",
    "research_relation",
    "transferable_ideas",
    "limitations",
    "worth_reading",
    "follow_up",
    "semantic_exclusion_reason",
)

V3_REVIEW_PROSE_LIMITS = {
    "core_conclusion": 110,
    "research_problem": 90,
    "method_overview": 110,
    "contributions": 90,
    "research_relation": 110,
    "transferable_ideas": 90,
    "limitations": 90,
    "worth_reading": 60,
    "follow_up": 80,
}
LEGACY_REVIEW_PROSE_FALLBACKS = {
    "core_conclusion": "旧版复核未提供可靠的中文核心结论，需结合摘要核对。",
    "research_problem": "旧版复核未提供中文研究问题，需结合摘要或原文核对。",
    "method_overview": "旧版复核未提供中文方法概述，需结合摘要或原文核对。",
    "contributions": "旧版复核未提供中文贡献说明，需结合摘要或原文核对。",
    "research_relation": "旧版复核未提供中文关联说明，需由当前研究目标重新核对。",
    "transferable_ideas": "旧版复核未确认可迁移内容，需精读后判断。",
    "limitations": "旧版复核未提供中文局限说明，需核对实验与数据设置。",
    "worth_reading": "旧版复核信息不足，建议按相关分决定是否精读。",
    "follow_up": "建议后续核对论文原文、代码与数据协议。",
}


def _normalized_paper_text(paper: dict[str, Any], field: str) -> str:
    return " ".join(str(paper.get(field, "")).lower().split())


def _matched_terms(text: str, terms: tuple[str, ...]) -> list[str]:
    return [term for term in terms if term in text]


def load_topic_tiers(root: Path) -> dict[str, tuple[str, ...]]:
    config = configure_public_runtime(root)
    return {name: tuple(config["topic_tiers"][name]) for name in "ABC"}


def local_prefilter(
    paper: dict[str, Any],
    topic_tiers: dict[str, tuple[str, ...]] | None = None,
) -> dict[str, Any]:
    """Return a deterministic, non-semantic ranking record for one abstract."""

    _require_public_configuration()
    tiers = topic_tiers if topic_tiers is not None else DEFAULT_TOPIC_TIERS
    title = _normalized_paper_text(paper, "title")
    abstract = _normalized_paper_text(paper, "abstract")
    direct_title = _matched_terms(title, tiers["A"])
    direct_abstract = _matched_terms(abstract, tiers["A"])
    method_title = _matched_terms(title, tiers["B"])
    method_abstract = _matched_terms(abstract, tiers["B"])
    transfer_title = _matched_terms(title, tiers["C"])
    transfer_abstract = _matched_terms(abstract, tiers["C"])
    architecture = _matched_terms(f"{title} {abstract}", ARCHITECTURE_TERMS)
    vision_context = _matched_terms(f"{title} {abstract}", VISION_CONTEXT_TERMS)
    architecture_visual = bool(architecture and vision_context)
    reasons: list[str] = []
    for label, values in (
        ("direct_title", direct_title),
        ("direct_abstract", direct_abstract),
        ("method_title", method_title),
        ("method_abstract", method_abstract),
        ("transfer_title", transfer_title),
        ("transfer_abstract", transfer_abstract),
    ):
        reasons.extend(f"{label}:{value}" for value in values)
    if architecture_visual:
        reasons.append("architecture_visual:" + ",".join(architecture))
    score = min(
        100,
        100 * bool(direct_title)
        or 85 * bool(direct_abstract)
        or 70 * bool(method_title)
        or 60 * bool(method_abstract)
        or 50 * bool(transfer_title)
        or 40 * bool(transfer_abstract)
        or 35 * architecture_visual,
    )
    metrics = {
        "direct_title": len(direct_title),
        "direct_abstract": len(direct_abstract),
        "method_title": len(method_title),
        "method_abstract": len(method_abstract),
        "transfer_title": len(transfer_title),
        "transfer_abstract": len(transfer_abstract),
        "architecture_visual": int(architecture_visual),
    }
    return {
        "prefilter_score": int(score),
        "prefilter_reasons": reasons,
        "prefilter_metrics": metrics,
        "local_topic_group": assign_topic_group(paper),
        "has_relevance_signal": bool(reasons),
    }


def _review_rank_key(item: dict[str, Any]) -> tuple[Any, ...]:
    metrics = item["prefilter_metrics"]
    category_order = CATEGORY_ORDER
    sources = item.get("paper", {}).get("query_sources", [])
    category_rank = min(
        (category_order.index(source) for source in sources if source in category_order),
        default=len(category_order),
    )
    submitted = str(item.get("paper", {}).get("submitted_or_updated", ""))
    try:
        submitted_rank = -datetime.fromisoformat(
            submitted.replace("Z", "+00:00")
        ).timestamp()
    except ValueError:
        submitted_rank = 0.0
    return (
        -metrics["direct_title"],
        -metrics["direct_abstract"],
        -metrics["method_title"],
        -metrics["method_abstract"],
        -metrics["transfer_title"],
        -metrics["transfer_abstract"],
        -metrics["architecture_visual"],
        category_rank,
        submitted_rank,
        str(item.get("paper", {}).get("arxiv_id", "")),
    )


def _bounded_review_page(
    run_id: str,
    number: int,
    items: list[dict[str, Any]],
    page_max_bytes: int,
) -> dict[str, Any]:
    for abstract_limit in (REVIEW_ABSTRACT_MAX_CHARS, 900, 600, 400):
        papers = []
        for item in items:
            paper = item["paper"]
            abstract = " ".join(str(paper.get("abstract", "")).split())
            clipped = abstract[:abstract_limit]
            if len(abstract) > abstract_limit:
                clipped = clipped.rstrip() + "…"
            papers.append(
                {
                    "arxiv_id": paper.get("arxiv_id"),
                    "title": paper.get("title"),
                    "abstract": clipped,
                    "abstract_truncated": len(abstract) > abstract_limit,
                    "categories": paper.get("categories", []),
                    "query_sources": paper.get("query_sources", []),
                    "announcement_date": paper.get("announcement_date"),
                    "announcement_types": paper.get("announcement_types", []),
                    "submitted_or_updated": paper.get("submitted_or_updated"),
                    "local_topic_group": item["local_topic_group"],
                    "prefilter_score": item["prefilter_score"],
                    "prefilter_reasons": item["prefilter_reasons"],
                }
            )
        page = {
            "schema_version": REVIEW_SCHEMA_VERSION,
            "run_id": run_id,
            "page": number,
            "page_size": len(papers),
            "evidence_level": "abstract",
            "papers": papers,
        }
        if len(_json_bytes(page)) <= page_max_bytes:
            return page
    raise DigestValidationError(
        f"review page {number} exceeds {page_max_bytes} bytes after bounded clipping"
    )


def prepare_review(
    root: Path,
    run_id: str,
    *,
    candidate_limit: int = DEFAULT_REVIEW_CANDIDATE_LIMIT,
    page_size: int = DEFAULT_REVIEW_PAGE_SIZE,
    page_max_bytes: int = DEFAULT_REVIEW_PAGE_MAX_BYTES,
) -> dict[str, Any]:
    'Validate selected checkpoints and expose at most two compact model review pages.'
    configure_public_runtime(root)

    if not 1 <= candidate_limit <= DEFAULT_REVIEW_CANDIDATE_LIMIT:
        raise DigestValidationError("review candidate limit must be from 1 to 30")
    if not 1 <= page_size <= DEFAULT_REVIEW_PAGE_SIZE:
        raise DigestValidationError("review page size must be from 1 to 15")
    if candidate_limit > page_size * MAX_REVIEW_PAGES:
        raise DigestValidationError("review candidate limit must fit in at most two pages")
    if not 8_000 <= page_max_bytes <= DEFAULT_REVIEW_PAGE_MAX_BYTES:
        raise DigestValidationError("review page maximum bytes must be from 8000 to 30000")
    root = root.resolve()
    initialize_runtime(root)
    with _exclusive_gate_state_lock(root / "digest-transaction.lock"):
        pending_path = root / "pending-run.json"
        if pending_path.exists():
            pending = read_json(pending_path)
            if pending.get("delivery_status") in {None, "pending", "committing"}:
                raise DigestValidationError(
                    "an uncommitted digest transaction must be resumed before review"
                )
        last_state = read_json(root / "last-successful-run.json")
        sent_state = read_json(root / "sent-papers.json")
        cursors = last_state.get("announcement_cursors", {})
        if not isinstance(cursors, dict):
            raise DigestValidationError("announcement cursors must be an object")
        if cursors and set(cursors) != set(TRACKED_CATEGORIES):
            raise DigestValidationError(_report_category_text('all seven announcement cursors are required'))
        run_dir = announcement_batch_output_path(root, run_id, TRACKED_CATEGORIES[0]).parent
        all_papers: list[dict[str, Any]] = []
        coverages: list[dict[str, Any]] = []
        checkpoints: list[dict[str, Any]] = []
        announcement_dates: set[str] = set()
        already_processed: list[str] = []
        retrieved_count = 0
        for category in TRACKED_CATEGORIES:
            path = announcement_batch_output_path(root, run_id, category)
            batch = read_json(path)
            expected_cursor = cursors.get(category)
            coverage = _validate_screening_checkpoint(batch, category, expected_cursor, root=root)
            announcement_dates.add(str(batch["announcement_date"]))
            coverages.append(coverage)
            retrieved_count += len(batch["papers"])
            if batch.get("cursor_action") == "already_processed":
                already_processed.append(category)
            else:
                all_papers.extend(copy.deepcopy(batch["papers"]))
            checkpoints.append(
                {
                    "category": category,
                    "path": str(path),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "requested_cursor_date": expected_cursor,
                    "announcement_date": batch["announcement_date"],
                    "count": len(batch["papers"]),
                }
            )
        if len(announcement_dates) != 1:
            raise DigestValidationError(_report_category_text('the seven checkpoints must share one announcement date'))
        if already_processed and len(already_processed) != len(TRACKED_CATEGORIES):
            raise DigestValidationError("checkpoints mix processed and new category states")

        current_inventory = deduplicate_candidates(all_papers)
        deduplicated = deduplicate_candidates(all_papers, sent_state)
        eligible_ids = {str(item["arxiv_id"]) for item in deduplicated["eligible"]}
        already_known_ids = {
            str(item["arxiv_id"]) for item in deduplicated["excluded"]
        }
        topic_tiers = load_topic_tiers(root)
        hidden_counts = {
            "configured_primary_exclusion": 0,
            "configured_secondary_exclusion": 0,
        }
        inventory: list[dict[str, Any]] = []
        ranked: list[dict[str, Any]] = []
        for paper in current_inventory["eligible"]:
            record = {
                "paper": copy.deepcopy(paper),
                **local_prefilter(paper, topic_tiers),
            }
            reason = exclusion_reason(paper)
            arxiv_id = str(paper["arxiv_id"])
            if reason is not None:
                hidden_counts[reason] += 1
                record["local_classification"] = "hidden"
                record["exclusion_reason"] = reason
            elif arxiv_id in already_known_ids or arxiv_id not in eligible_ids:
                record["local_classification"] = "already_known"
            elif record["has_relevance_signal"]:
                record["local_classification"] = "review_candidate"
                ranked.append(record)
            else:
                record["local_classification"] = "local_background"
            inventory.append(record)
        ranked.sort(key=_review_rank_key)
        selected = ranked[:candidate_limit]
        selected_ids = {str(item["paper"]["arxiv_id"]) for item in selected}
        for record in inventory:
            if record["local_classification"] == "review_candidate":
                record["local_classification"] = (
                    "model_review" if str(record["paper"]["arxiv_id"]) in selected_ids
                    else "budget_deferred"
                )
        candidate_count = sum(
            item["local_classification"]
            in {"model_review", "budget_deferred", "local_background"}
            for item in inventory
        )

        groups = [selected[offset : offset + page_size] for offset in range(0, len(selected), page_size)]
        if len(groups) > MAX_REVIEW_PAGES:
            raise DigestValidationError("review preparation exceeded the two-page budget")
        page_values: list[tuple[Path, dict[str, Any]]] = []
        pages: list[dict[str, Any]] = []
        for number, items in enumerate(groups, start=1):
            page = _bounded_review_page(run_id, number, items, page_max_bytes)
            path = run_dir / f"review-page-{number:03d}.json"
            payload = _json_bytes(page)
            page_values.append((path, page))
            pages.append(
                {
                    "page": number,
                    "path": str(path),
                    "count": len(items),
                    "bytes": len(payload),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                }
            )
        ledger = {
            "schema_version": REVIEW_SCHEMA_VERSION,
            "coverage_policy": DAILY_COVERAGE_POLICY,
            "report_category": REPORT_CATEGORY,
            "public_profile_sha256": _require_public_configuration()["_config_sha256"],
            "run_id": run_id,
            "announcement_date": next(iter(announcement_dates)),
            "retrieved_count": retrieved_count,
            "unique_count": current_inventory["unique_count"],
            "eligible_count": len(deduplicated["eligible"]),
            "candidate_count": candidate_count,
            "reviewed_count": len(selected),
            "budget_deferred_count": max(0, len(ranked) - len(selected)),
            "local_background_count": sum(
                item["local_classification"] == "local_background" for item in inventory
            ),
            "already_known_count": len(already_known_ids),
            "no_new_announcement": len(already_processed) == len(TRACKED_CATEGORIES),
            "exclusion_stats": {
                **hidden_counts,
                "cs_cv_total_hidden": sum(
                    item.get("exclusion_reason") is not None
                    and REPORT_CATEGORY in item["paper"].get("query_sources", [])
                    for item in inventory
                ),
                "total_hidden": sum(hidden_counts.values()),
            },
            "retrieval_coverage": coverages,
            "topic_tiers": {name: list(values) for name, values in topic_tiers.items()},
            "inventory": inventory,
        }
        ledger_path = run_dir / "review-inventory-v3.json"
        manifest = {
            "schema_version": REVIEW_SCHEMA_VERSION,
            "coverage_policy": DAILY_COVERAGE_POLICY,
            "report_category": REPORT_CATEGORY,
            "public_profile_sha256": _require_public_configuration()["_config_sha256"],
            "run_id": run_id,
            "announcement_date": ledger["announcement_date"],
            "candidate_limit": candidate_limit,
            "page_size": page_size,
            "page_max_bytes": page_max_bytes,
            "page_count": len(pages),
            "model_candidate_count": len(selected),
            "inventory_count": candidate_count,
            "report_record_count": len(inventory),
            "no_new_announcement": ledger["no_new_announcement"],
            "ledger_path": str(ledger_path),
            "ledger_sha256": _json_sha256(ledger),
            "checkpoints": checkpoints,
            "pages": pages,
        }
        manifest_path = run_dir / "review-manifest-v3.json"
        if manifest_path.exists() and read_json(manifest_path) == manifest:
            pages_valid = all(
                Path(record["path"]).is_file()
                and Path(record["path"]).stat().st_size == record["bytes"]
                and hashlib.sha256(Path(record["path"]).read_bytes()).hexdigest()
                == record["sha256"]
                for record in pages
            )
            if (
                ledger_path.is_file()
                and hashlib.sha256(ledger_path.read_bytes()).hexdigest()
                == manifest["ledger_sha256"]
                and pages_valid
            ):
                return {
                    "run_id": run_id,
                    "inventory": candidate_count,
                    "report_records": len(inventory),
                    "model_candidates": len(selected),
                    "pages": len(pages),
                    "model_visible_bytes": sum(item["bytes"] for item in pages),
                    "no_new_announcement": ledger["no_new_announcement"],
                    "manifest": str(manifest_path),
                    "reused": True,
                }
        if list(run_dir.glob("review-decision-*.json")):
            raise DigestValidationError(
                "review_source_changed: existing v3 decisions are bound to another source"
            )
        atomic_write_json(ledger_path, ledger)
        for path, page in page_values:
            atomic_write_json(path, page)
        atomic_write_json(manifest_path, manifest)
        return {
            "run_id": run_id,
            "inventory": candidate_count,
            "report_records": len(inventory),
            "model_candidates": len(selected),
            "pages": len(pages),
            "model_visible_bytes": sum(item["bytes"] for item in pages),
            "no_new_announcement": ledger["no_new_announcement"],
            "manifest": str(manifest_path),
            "reused": False,
        }


def _load_review_state(
    root: Path,
    run_id: str,
) -> tuple[Path, dict[str, Any], dict[str, Any], list[tuple[dict[str, Any], dict[str, Any]]]]:
    run_dir = announcement_batch_output_path(root.resolve(), run_id, TRACKED_CATEGORIES[0]).parent
    manifest = read_json(run_dir / "review-manifest-v3.json")
    _validate_public_artifact_profile(manifest)
    if manifest.get("schema_version") not in {REVIEW_SCHEMA_VERSION, SCHEMA_VERSION} or manifest.get("run_id") != run_id:
        raise DigestValidationError("v3 review manifest identity mismatch")
    ledger_path = Path(str(manifest.get("ledger_path") or ""))
    if not ledger_path.is_file() or hashlib.sha256(ledger_path.read_bytes()).hexdigest() != manifest.get("ledger_sha256"):
        raise DigestValidationError("v3 review inventory hash mismatch")
    ledger = read_json(ledger_path)
    _validate_public_artifact_profile(ledger)
    records = manifest.get("pages")
    if not isinstance(records, list) or len(records) > MAX_REVIEW_PAGES:
        raise DigestValidationError("v3 review manifest page budget is invalid")
    pages: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for expected, record in enumerate(records, start=1):
        path = Path(str(record.get("path") or ""))
        if record.get("page") != expected or not path.is_file():
            raise DigestValidationError(f"missing v3 review page {expected}")
        if hashlib.sha256(path.read_bytes()).hexdigest() != record.get("sha256"):
            raise DigestValidationError(f"v3 review page {expected} hash mismatch")
        page = read_json(path)
        if page.get("run_id") != run_id or page.get("page") != expected:
            raise DigestValidationError(f"v3 review page {expected} identity mismatch")
        if len(_json_bytes(page)) > int(manifest["page_max_bytes"]):
            raise DigestValidationError(f"v3 review page {expected} exceeds its byte budget")
        pages.append((record, page))
    return run_dir, manifest, ledger, pages


def _review_decision_contract(run_id: str, record: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "input_template": {
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id,
            "page": record["page"],
            "source_page_sha256": record["sha256"],
            "decisions": [],
        },
        "expected_decision_count": record["count"],
        "preserve_source_order": True,
        "decision_fields": list(REVIEW_DECISION_FIELDS),
        "topic_groups": list(TOPIC_GROUPS),
        "semantic_exclusion_reasons": list(SEMANTIC_EXCLUSION_REASONS),
        "evidence_level": "abstract",
        "prose_limits": copy.deepcopy(V3_REVIEW_PROSE_LIMITS),
    }


def _validate_review_decision(
    run_id: str,
    record: dict[str, Any],
    page: dict[str, Any],
    value: dict[str, Any],
) -> dict[str, Any]:
    if value.get("schema_version") not in {REVIEW_SCHEMA_VERSION, SCHEMA_VERSION}:
        raise DigestValidationError("review decision schema version mismatch")
    if value.get("run_id") != run_id or value.get("page") != record["page"]:
        raise DigestValidationError("review decision run/page mismatch")
    if value.get("source_page_sha256") != record["sha256"]:
        raise DigestValidationError("review decision source hash mismatch")
    decisions = value.get("decisions")
    papers = page.get("papers")
    if not isinstance(decisions, list) or not isinstance(papers, list) or len(decisions) != len(papers):
        raise DigestValidationError("review decision count mismatch")
    if [str(item.get("arxiv_id")) for item in decisions if isinstance(item, dict)] != [
        str(item.get("arxiv_id")) for item in papers
    ]:
        raise DigestValidationError("review decision IDs/order mismatch")
    normalized: list[dict[str, Any]] = []
    limits = V3_REVIEW_PROSE_LIMITS
    legacy_compatible = value.get("schema_version") == REVIEW_SCHEMA_VERSION
    for decision in decisions:
        arxiv_id = str(decision.get("arxiv_id", ""))
        score = decision.get("relevance_score")
        if type(score) is not int or not 0 <= score <= 100:
            raise DigestValidationError(f"invalid relevance score for {arxiv_id}")
        if decision.get("topic_group") not in TOPIC_GROUPS:
            raise DigestValidationError(f"invalid topic group for {arxiv_id}")
        result = {"arxiv_id": arxiv_id, "relevance_score": score, "topic_group": decision["topic_group"]}
        for field, limit in limits.items():
            prose = str(decision.get(field, "")).strip()
            if validate_chinese_prose(prose, field):
                if legacy_compatible:
                    prose = LEGACY_REVIEW_PROSE_FALLBACKS[field]
                else:
                    raise DigestValidationError(f"{field} must contain Chinese prose for {arxiv_id}")
            if len(prose) > limit:
                raise DigestValidationError(f"{field} exceeds {limit} characters for {arxiv_id}")
            result[field] = prose
        exclusion = decision.get("semantic_exclusion_reason")
        if exclusion is not None and exclusion not in SEMANTIC_EXCLUSION_REASONS:
            raise DigestValidationError(f"invalid semantic exclusion for {arxiv_id}")
        result["semantic_exclusion_reason"] = exclusion
        normalized.append(result)
    return {
        "schema_version": int(value["schema_version"]),
        "run_id": run_id,
        "page": record["page"],
        "source_page_sha256": record["sha256"],
        "decisions": normalized,
    }


def record_review_page(
    root: Path,
    run_id: str,
    page_number: int,
    input_path: Path,
) -> dict[str, Any]:
    configure_public_runtime(root)
    root = root.resolve()
    with _exclusive_gate_state_lock(root / "digest-transaction.lock"):
        run_dir, _manifest, _ledger, pages = _load_review_state(root, run_id)
        if not 1 <= page_number <= len(pages):
            raise DigestValidationError("review page number is out of range")
        record, page = pages[page_number - 1]
        value = _validate_review_decision(run_id, record, page, read_json(input_path.resolve()))
        output = run_dir / f"review-decision-{page_number:03d}.json"
        if output.exists() and read_json(output) != value:
            raise DigestValidationError("review decision page already exists with different content")
        replayed = output.exists()
        if not replayed:
            atomic_write_json(output, value)
        return {
            "run_id": run_id,
            "page": page_number,
            "recorded": len(value["decisions"]),
            "path": str(output),
            "replayed": replayed,
        }


def _load_review_decisions(
    run_dir: Path,
    run_id: str,
    pages: list[tuple[dict[str, Any], dict[str, Any]]],
    *,
    require_complete: bool,
) -> tuple[list[dict[str, Any]], list[int]]:
    decisions: list[dict[str, Any]] = []
    missing: list[int] = []
    for record, page in pages:
        number = int(record["page"])
        path = run_dir / f"review-decision-{number:03d}.json"
        if not path.exists():
            missing.append(number)
            continue
        decisions.extend(
            _validate_review_decision(run_id, record, page, read_json(path))["decisions"]
        )
    if require_complete and missing:
        raise DigestValidationError(f"review is incomplete; missing page {missing[0]}")
    return decisions, missing


def review_status(root: Path, run_id: str) -> dict[str, Any]:
    configure_public_runtime(root)
    run_dir, manifest, _ledger, pages = _load_review_state(root.resolve(), run_id)
    if manifest.get("no_new_announcement") is True:
        return {"run_id": run_id, "phase": "no_new_announcement", "next_action": "no_work"}
    _decisions, missing = _load_review_decisions(
        run_dir, run_id, pages, require_complete=False
    )
    if missing:
        number = missing[0]
        record = manifest["pages"][number - 1]
        return {
            "run_id": run_id,
            "phase": "review",
            "completed_pages": len(pages) - len(missing),
            "total_pages": len(pages),
            "next_page": record["path"],
            "next_page_number": number,
            "next_page_sha256": record["sha256"],
            "decision_contract": _review_decision_contract(run_id, record),
            "next_action": "record_review_page",
        }
    return {
        "run_id": run_id,
        "phase": "review_complete",
        "completed_pages": len(pages),
        "total_pages": len(pages),
        "next_action": "finalize_digest",
    }


def _v3_selected_paper(paper: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    score = int(decision["relevance_score"])
    recommendation = "强烈建议立即阅读" if score >= 90 else ("建议精读" if score >= 75 else "建议浏览")
    value = copy.deepcopy(paper)
    value.update(
        {
            "relevance_score": score,
            "recommendation": recommendation,
            "core_conclusion": decision["core_conclusion"],
            "research_problem": decision["research_problem"],
            "method_overview": decision["method_overview"],
            "contributions": decision["contributions"],
            "research_relation": decision["research_relation"],
            "transferable_ideas": decision["transferable_ideas"],
            "limitations": decision["limitations"],
            "worth_reading": decision["worth_reading"],
            "follow_up": decision["follow_up"],
            "evidence_level": "abstract",
            "topic_group": decision["topic_group"],
        }
    )
    return {field: value.get(field) for field in V3_PAPER_FIELDS}


def _render_inventory_markdown(
    ledger: dict[str, Any],
    decision_by_id: dict[str, dict[str, Any]],
) -> str:
    lines = [
        f"# arXiv Daily 本地分类报告 — {ledger['announcement_date']}",
        "",
        f"- 完整检索：{ledger['retrieved_count']}",
        f"- 去重后：{ledger['unique_count']}",
        f"- 模型复核：{ledger['reviewed_count']}",
        f"- 预算延后：{ledger['budget_deferred_count']}",
        f"- 本地背景：{ledger['local_background_count']}",
        "",
        "| arXiv | 标题 | 本地分类 | 主题 | 预筛分 | 模型分 |",
        "|---|---|---|---|---:|---:|",
    ]
    for item in ledger["inventory"]:
        paper = item["paper"]
        arxiv_id = str(paper["arxiv_id"])
        decision = decision_by_id.get(arxiv_id)
        title = str(paper.get("title", "")).replace("|", "\\|").replace("\n", " ")
        lines.append(
            "| {id} | {title} | {classification} | {group} | {local} | {model} |".format(
                id=arxiv_id,
                title=title,
                classification=item["local_classification"],
                group=(decision or {}).get("topic_group", item["local_topic_group"]),
                local=item["prefilter_score"],
                model=(decision or {}).get("relevance_score", "—"),
            )
        )
    return "\n".join(lines) + "\n"


def _finalize_digest_v3_legacy(root: Path, run_id: str) -> dict[str, Any]:
    root = root.resolve()
    run_dir, manifest, ledger, pages = _load_review_state(root, run_id)
    decisions, _missing = _load_review_decisions(
        run_dir, run_id, pages, require_complete=True
    )
    source_by_id = {
        str(item["paper"]["arxiv_id"]): item["paper"] for item in ledger["inventory"]
    }
    eligible_decisions = [
        decision for decision in decisions if decision.get("semantic_exclusion_reason") is None
    ]
    eligible_decisions.sort(
        key=lambda decision: paper_sort_key(
            {**source_by_id[str(decision["arxiv_id"])], **decision}
        )
    )
    focus_decisions = [
        decision for decision in eligible_decisions if decision["relevance_score"] >= FOCUS_SCORE_MINIMUM
    ][:MAX_EMAIL_FOCUS]
    focus_ids = {str(decision["arxiv_id"]) for decision in focus_decisions}
    watch_decisions = [
        decision
        for decision in eligible_decisions
        if str(decision["arxiv_id"]) not in focus_ids
        and decision["relevance_score"] >= WATCH_SCORE_MINIMUM
    ][:MAX_EMAIL_WATCH]
    focus = [
        _v3_selected_paper(source_by_id[str(item["arxiv_id"])], item)
        for item in focus_decisions
    ]
    watch = [
        _v3_selected_paper(source_by_id[str(item["arxiv_id"])], item)
        for item in watch_decisions
    ]
    exclusion_stats = copy.deepcopy(ledger["exclusion_stats"])
    for decision in decisions:
        reason = decision.get("semantic_exclusion_reason")
        if reason is None:
            continue
        exclusion_stats[reason] += 1
        exclusion_stats["total_hidden"] += 1
        paper = source_by_id[str(decision["arxiv_id"])]
        if REPORT_CATEGORY in paper.get("query_sources", []):
            exclusion_stats["cs_cv_total_hidden"] += 1
    decision_by_id = {str(item["arxiv_id"]): item for item in decisions}
    result_ledger = copy.deepcopy(ledger)
    result_ledger["model_decisions"] = decisions
    result_json = run_dir / "inventory-result-v3.json"
    result_markdown = run_dir / "inventory-report-v3.md"
    atomic_write_json(result_json, result_ledger)
    atomic_write_text(result_markdown, _render_inventory_markdown(ledger, decision_by_id))
    group_counts: dict[str, int] = {}
    for paper in focus + watch:
        group = str(paper["topic_group"])
        group_counts[group] = group_counts.get(group, 0) + 1
    trends = [
        f"本次高相关论文主要集中在{TOPIC_LABELS[group]}，共 {count} 篇。"
        for group, count in sorted(
            group_counts.items(), key=lambda item: TOPIC_GROUPS.index(item[0])
        )
    ] or ["本次更新未发现达到浏览阈值的高相关论文。"]
    insights = []
    for paper in focus[:3]:
        relation = str(paper["research_relation"])
        if relation not in insights:
            insights.append(relation)
    if not insights:
        insights = ["本次更新暂无需要立即调整当前研究计划的内容。"]
    report_date = str(ledger["announcement_date"])
    digest = {
        "schema_version": SCHEMA_VERSION,
        "coverage_policy": DAILY_COVERAGE_POLICY,
        "report_category": REPORT_CATEGORY,
        "public_profile_sha256": _require_public_configuration()["_config_sha256"],
        "run_id": run_id,
        "date": report_date,
        "retrieval_window": {"basis": "announcement_batch", "from": report_date, "to": report_date},
        "stats": {
            "retrieved": int(ledger["retrieved_count"]),
            "unique": int(ledger["unique_count"]),
            "candidates": int(ledger["candidate_count"]),
            "model_reviewed": len(decisions),
            "budget_deferred": int(ledger["budget_deferred_count"]),
            "local_background": int(ledger["local_background_count"]),
            "focus": len(focus),
            "watch": len(watch),
            "excluded_hidden": int(exclusion_stats["total_hidden"]),
        },
        "inventory_summary": {
            "inventory_count": int(ledger["candidate_count"]),
            "report_record_count": len(ledger["inventory"]),
            "model_candidate_limit": int(manifest["candidate_limit"]),
            "model_visible_bytes": sum(record["bytes"] for record in manifest["pages"]),
            "review_page_count": len(manifest["pages"]),
        },
        "overview": (
            (_report_category_text('本次完整检索七个 arXiv 分类，共获得 ') + f"{ledger['retrieved_count']}" + ' 条公告记录，去重后 ' + f"{ledger['unique_count']}" + ' 篇；本地预筛后由模型复核 ' + f'{len(decisions)}' + ' 篇，推荐重点 ' + f'{len(focus)}' + ' 篇、关注 ' + f'{len(watch)}' + ' 篇。')
        ),
        "reading_order": [],
        "focus_papers": focus,
        "watch_papers": watch,
        "trends": trends,
        "actionable_insights": insights,
        "retrieval_coverage": copy.deepcopy(ledger["retrieval_coverage"]),
        "exclusion_stats": exclusion_stats,
        "arxiv_tools": ["mcp__arxiv_daily__fetch_announcement_phase"],
        "next_version_check_cursor": int(read_json(root / "last-successful-run.json").get("version_check_cursor", 0)),
        "local_reports": {
            "inventory_json": str(result_json),
            "inventory_markdown": str(result_markdown),
        },
    }
    digest = canonicalize_digest(digest)
    validate_digest(digest)
    output = run_dir / "digest-v3.json"
    atomic_write_json(output, digest)
    return {
        "run_id": run_id,
        "digest": str(output),
        "focus": len(focus),
        "watch": len(watch),
        "inventory": len(ledger["inventory"]),
        "local_report": str(result_markdown),
    }


def _select_review_results(
    ledger: dict[str, Any], decisions: list[dict[str, Any]]
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    source_by_id = {
        str(item["paper"]["arxiv_id"]): item["paper"] for item in ledger["inventory"]
    }
    eligible = [
        decision
        for decision in decisions
        if decision.get("semantic_exclusion_reason") is None
    ]
    eligible.sort(
        key=lambda decision: paper_sort_key(
            {**source_by_id[str(decision["arxiv_id"])], **decision}
        )
    )
    focus = [
        item for item in eligible if item["relevance_score"] >= FOCUS_SCORE_MINIMUM
    ][:MAX_EMAIL_FOCUS]
    focus_ids = {str(item["arxiv_id"]) for item in focus}
    watch = [
        item
        for item in eligible
        if str(item["arxiv_id"]) not in focus_ids
        and item["relevance_score"] >= WATCH_SCORE_MINIMUM
    ][:MAX_EMAIL_WATCH]
    return source_by_id, focus, watch


def _cs_cv_report_rank_key(item: dict[str, Any]) -> tuple[Any, ...]:
    model_score = item.get("model_score")
    effective = int(model_score) if type(model_score) is int else int(item["prefilter_score"])
    return (-effective, *_review_rank_key(item))


def _cs_cv_report_papers(
    ledger: dict[str, Any],
    decisions: list[dict[str, Any]],
    selected_ids: set[str],
) -> list[dict[str, Any]]:
    'Rank the remaining selected report category inventory once, without any translation.'

    decision_by_id = {str(item["arxiv_id"]): item for item in decisions}
    ranked: list[dict[str, Any]] = []
    for item in ledger["inventory"]:
        paper = item["paper"]
        arxiv_id = str(paper["arxiv_id"])
        if (
            REPORT_CATEGORY not in paper.get("query_sources", [])
            or arxiv_id in selected_ids
            or item.get("local_classification") in {"hidden", "already_known"}
        ):
            continue
        decision = decision_by_id.get(arxiv_id)
        if decision and decision.get("semantic_exclusion_reason") is not None:
            continue
        ranked.append(
            {
                "paper": paper,
                "arxiv_id": arxiv_id,
                "prefilter_score": int(item["prefilter_score"]),
                "prefilter_metrics": item["prefilter_metrics"],
                "model_score": decision.get("relevance_score") if decision else None,
            }
        )
    ranked.sort(key=_cs_cv_report_rank_key)
    papers = []
    for record in ranked:
        paper = copy.deepcopy(record["paper"])
        paper["relevance_score"] = int(
            record["model_score"] if type(record["model_score"]) is int else record["prefilter_score"]
        )
        papers.append({field: paper.get(field) for field in CS_CV_REPORT_FIELDS})
    return papers


def finalize_digest(root: Path, run_id: str) -> dict[str, Any]:
    configure_public_runtime(root)
    root = root.resolve()
    run_dir, review_manifest, ledger, review_pages = _load_review_state(root, run_id)
    decisions, _missing = _load_review_decisions(run_dir, run_id, review_pages, require_complete=True)
    source_by_id, focus_decisions, watch_decisions = _select_review_results(ledger, decisions)
    focus = [_v3_selected_paper(source_by_id[str(item["arxiv_id"])], item) for item in focus_decisions]
    watch = [_v3_selected_paper(source_by_id[str(item["arxiv_id"])], item) for item in watch_decisions]
    selected_ids = {str(item["arxiv_id"]) for item in focus_decisions + watch_decisions}
    cv_papers = _cs_cv_report_papers(ledger, decisions, selected_ids)
    exclusion_stats = copy.deepcopy(ledger["exclusion_stats"])
    for decision in decisions:
        reason = decision.get("semantic_exclusion_reason")
        if reason is not None:
            exclusion_stats[reason] += 1
            exclusion_stats["total_hidden"] += 1
            if REPORT_CATEGORY in source_by_id[str(decision["arxiv_id"])].get("query_sources", []):
                exclusion_stats["cs_cv_total_hidden"] += 1
    decision_by_id = {str(item["arxiv_id"]): item for item in decisions}
    result_ledger = copy.deepcopy(ledger)
    result_ledger["model_decisions"] = decisions
    result_ledger["cs_cv_report"] = cv_papers
    result_json = run_dir / "inventory-result-v4.json"
    result_markdown = run_dir / "inventory-report-v4.md"
    atomic_write_json(result_json, result_ledger)
    atomic_write_text(result_markdown, _render_inventory_markdown(ledger, decision_by_id))
    group_counts: dict[str, int] = {}
    for paper in focus + watch:
        group = str(paper["topic_group"])
        group_counts[group] = group_counts.get(group, 0) + 1
    trends = [f"本次高相关论文主要集中在{TOPIC_LABELS[group]}，共 {count} 篇。" for group, count in sorted(group_counts.items(), key=lambda item: TOPIC_GROUPS.index(item[0]))] or ["本次更新未发现达到浏览阈值的高相关论文。"]
    insights = list(dict.fromkeys(str(paper["research_relation"]) for paper in focus[:3])) or ["本次更新暂无需要立即调整当前研究计划的内容。"]
    report_date = str(ledger["announcement_date"])
    digest = {
        "schema_version": SCHEMA_VERSION,
        "coverage_policy": DAILY_COVERAGE_POLICY,
        "report_category": REPORT_CATEGORY,
        "report_already_known_count": len({
            str(item["paper"]["arxiv_id"]) for item in ledger["inventory"]
            if item.get("local_classification") == "already_known"
            and REPORT_CATEGORY in item["paper"].get("query_sources", [])
        }),
        "public_profile_sha256": _require_public_configuration()["_config_sha256"],
        "run_id": run_id,
        "date": report_date,
        "retrieval_window": {"basis": "announcement_batch", "from": report_date, "to": report_date},
        "stats": {
            "retrieved": int(ledger["retrieved_count"]), "unique": int(ledger["unique_count"]),
            "candidates": int(ledger["candidate_count"]), "model_reviewed": len(decisions),
            "budget_deferred": int(ledger["budget_deferred_count"]), "local_background": int(ledger["local_background_count"]),
            "focus": len(focus), "watch": len(watch), "cv_remainder": len(cv_papers),
            "excluded_hidden": int(exclusion_stats["total_hidden"]),
        },
        "inventory_summary": {
            "inventory_count": int(ledger["candidate_count"]), "report_record_count": len(ledger["inventory"]),
            "model_candidate_limit": int(review_manifest["candidate_limit"]),
            "model_visible_bytes": sum(record["bytes"] for record in review_manifest["pages"]),
            "review_page_count": len(review_manifest["pages"]),
        },
        "overview": (_report_category_text('本次完整检索七个 arXiv 分类，共获得 ') + f"{ledger['retrieved_count']}" + ' 条公告记录，去重后 ' + f"{ledger['unique_count']}" + ' 篇；模型复核 ' + f'{len(decisions)}' + ' 篇，推荐重点 ' + f'{len(focus)}' + ' 篇、关注 ' + f'{len(watch)}' + _report_category_text(' 篇；其余 cs.CV ') + f'{len(cv_papers)}' + ' 篇仅记入本地清单。'),
        "reading_order": [paper["title"] for paper in focus[:3]],
        "focus_papers": focus, "watch_papers": watch,
        "trends": trends, "actionable_insights": insights,
        "retrieval_coverage": copy.deepcopy(ledger["retrieval_coverage"]),
        "exclusion_stats": exclusion_stats,
        "cs_cv_report": {"total": len(cv_papers), "papers": cv_papers},
        "arxiv_tools": ["mcp__arxiv_daily__fetch_announcement_phase"],
        "next_version_check_cursor": int(read_json(root / "last-successful-run.json").get("version_check_cursor", 0)),
        "local_reports": {"inventory_json": str(result_json), "inventory_markdown": str(result_markdown)},
    }
    digest = canonicalize_digest(digest)
    validate_digest(digest)
    output = run_dir / "digest-v4.json"
    atomic_write_json(output, digest)
    return {"run_id": run_id, "digest": str(output), "focus": len(focus), "watch": len(watch), "cv_remainder": len(cv_papers), "inventory": len(ledger["inventory"]), "local_report": str(result_markdown)}


def prepare_screening(
    root: Path,
    run_id: str,
    *,
    page_size: int = 40,
    page_max_bytes: int = 32_000,
) -> dict[str, Any]:
    'Prepare bounded offline semantic-screening pages from selected checkpoints.'
    configure_public_runtime(root)

    if not 1 <= page_size <= 100:
        raise DigestValidationError("screening page size must be from 1 to 100")
    if not 8_000 <= page_max_bytes <= 90_000:
        raise DigestValidationError(
            "screening page maximum bytes must be from 8000 to 90000"
        )
    root = root.resolve()
    initialize_runtime(root)
    with _exclusive_gate_state_lock(root / "digest-transaction.lock"):
        return _prepare_screening_locked(
            root,
            run_id,
            page_size=page_size,
            page_max_bytes=page_max_bytes,
        )


def _prepare_screening_locked(
    root: Path,
    run_id: str,
    *,
    page_size: int,
    page_max_bytes: int,
) -> dict[str, Any]:
    """Implementation of :func:`prepare_screening` under the transaction lock."""

    pending_path = root / "pending-run.json"
    if pending_path.exists():
        pending = read_json(pending_path)
        pending_status = pending.get("delivery_status")
        if pending_status in {None, "pending", "committing"}:
            raise DigestValidationError(
                "an uncommitted digest transaction must be resumed before screening a new run"
            )
        if pending_status != "committed":
            raise DigestValidationError(
                f"unsupported pending-run delivery_status: {pending_status}"
            )

    last_state = read_json(root / "last-successful-run.json")
    sent_state = read_json(root / "sent-papers.json")
    cursors = last_state.get("announcement_cursors", {})
    if not isinstance(cursors, dict):
        raise DigestValidationError(
            "last-successful-run.json announcement_cursors must be an object"
        )
    if cursors and set(cursors) != set(TRACKED_CATEGORIES):
        raise DigestValidationError(
            _report_category_text('last-successful-run.json must contain all seven announcement cursors')
        )

    run_dir = announcement_batch_output_path(root, run_id, TRACKED_CATEGORIES[0]).parent
    all_papers: list[dict[str, Any]] = []
    retrieved_count = 0
    coverages: list[dict[str, Any]] = []
    checkpoint_records: list[dict[str, Any]] = []
    announcement_dates: set[str] = set()
    already_processed_categories: list[str] = []
    for category in TRACKED_CATEGORIES:
        path = announcement_batch_output_path(root, run_id, category)
        batch = read_json(path)
        expected_cursor = cursors.get(category)
        if expected_cursor is not None and not isinstance(expected_cursor, str):
            raise DigestValidationError(
                f"announcement cursor for {category} must be a date string or null"
            )
        coverage = _validate_screening_checkpoint(batch, category, expected_cursor, root=root)
        announcement_dates.add(str(batch["announcement_date"]))
        coverages.append(coverage)
        retrieved_count += len(batch["papers"])
        if batch.get("cursor_action") == "already_processed":
            already_processed_categories.append(category)
        else:
            all_papers.extend(copy.deepcopy(batch["papers"]))
        checkpoint_records.append(
            {
                "category": category,
                "path": str(path),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "requested_cursor_date": expected_cursor,
                "announcement_date": batch["announcement_date"],
                "count": len(batch["papers"]),
            }
        )
    if len(announcement_dates) != 1:
        raise DigestValidationError(
            _report_category_text('the seven announcement checkpoints do not share one announcement date')
        )
    if already_processed_categories and len(already_processed_categories) != len(
        TRACKED_CATEGORIES
    ):
        raise DigestValidationError(
            "announcement checkpoints mix already-processed and new category states"
        )

    current_inventory = deduplicate_candidates(all_papers)
    deduplicated = deduplicate_candidates(all_papers, sent_state)
    selectable_by_id = {
        str(paper["arxiv_id"]): paper for paper in deduplicated["eligible"]
    }
    hidden_counts = {
        "configured_primary_exclusion": 0,
        "configured_secondary_exclusion": 0,
    }
    hidden: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    cv_appendix_only: list[dict[str, Any]] = []
    cs_cv_total_hidden = 0
    for paper in current_inventory["eligible"]:
        reason = exclusion_reason(paper)
        if reason is not None:
            hidden_counts[reason] += 1
            if REPORT_CATEGORY in paper.get("query_sources", []):
                cs_cv_total_hidden += 1
            hidden.append(
                {
                    "arxiv_id": paper["arxiv_id"],
                    "reason": reason,
                    "query_sources": list(paper.get("query_sources", [])),
                }
            )
            continue
        selectable = selectable_by_id.get(str(paper["arxiv_id"]))
        if selectable is not None:
            paper["delivery_status"] = selectable["delivery_status"]
            paper["screening_scope"] = "selection_candidate"
            candidates.append(paper)
            continue
        if REPORT_CATEGORY in paper.get("query_sources", []):
            paper["delivery_status"] = "already_known"
            paper["screening_scope"] = "cs_cv_appendix_only"
            cv_appendix_only.append(paper)

    screening_papers = candidates + cv_appendix_only

    ledger = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "announcement_date": next(iter(announcement_dates)),
        "retrieved_count": retrieved_count,
        "work_input_count": deduplicated["input_count"],
        "unique_count": deduplicated["unique_count"],
        "already_processed_categories": already_processed_categories,
        "no_new_announcement": len(already_processed_categories) == len(TRACKED_CATEGORIES),
        "already_known_count": len(deduplicated["excluded"]),
        "candidate_count": len(candidates),
        "cv_appendix_only_count": len(cv_appendix_only),
        "screening_count": len(screening_papers),
        "hidden_count": len(hidden),
        "exclusion_stats": {
            **hidden_counts,
            "cs_cv_total_hidden": cs_cv_total_hidden,
            "total_hidden": len(hidden),
        },
        "retrieval_coverage": coverages,
        "already_known": deduplicated["excluded"],
        "hidden": hidden,
        "candidates": candidates,
        "cv_appendix_only": cv_appendix_only,
    }
    ledger_path = run_dir / "screening-ledger.json"
    ledger_sha256 = _json_sha256(ledger)

    page_groups: list[list[dict[str, Any]]] = []
    current_group: list[dict[str, Any]] = []
    for paper in screening_papers:
        item = {field: paper.get(field) for field in SCREENING_PAGE_FIELDS}
        proposed = current_group + [item]
        proposed_page = {
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id,
            "page": len(page_groups) + 1,
            "page_size": len(proposed),
            "papers": proposed,
        }
        proposed_bytes = len(
            (json.dumps(proposed_page, ensure_ascii=False, indent=2) + "\n").encode(
                "utf-8"
            )
        )
        if current_group and (
            len(proposed) > page_size or proposed_bytes > page_max_bytes
        ):
            page_groups.append(current_group)
            current_group = [item]
            single_page = {
                "schema_version": SCHEMA_VERSION,
                "run_id": run_id,
                "page": len(page_groups) + 1,
                "page_size": 1,
                "papers": current_group,
            }
            single_bytes = len(
                (json.dumps(single_page, ensure_ascii=False, indent=2) + "\n").encode(
                    "utf-8"
                )
            )
            if single_bytes > page_max_bytes:
                raise DigestValidationError(
                    f"screening record {paper['arxiv_id']} exceeds the page byte limit"
                )
        else:
            if proposed_bytes > page_max_bytes:
                raise DigestValidationError(
                    f"screening record {paper['arxiv_id']} exceeds the page byte limit"
                )
            current_group = proposed
    if current_group:
        page_groups.append(current_group)

    pages: list[dict[str, Any]] = []
    page_values: list[tuple[Path, dict[str, Any]]] = []
    for page_papers in page_groups:
        number = len(pages) + 1
        page_path = run_dir / f"screening-page-{number:03d}.json"
        page = {
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id,
            "page": number,
            "page_size": len(page_papers),
            "papers": page_papers,
        }
        page_bytes = _json_bytes(page)
        page_values.append((page_path, page))
        pages.append(
            {
                "page": number,
                "path": str(page_path),
                "count": len(page_papers),
                "bytes": len(page_bytes),
                "sha256": hashlib.sha256(page_bytes).hexdigest(),
            }
        )

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "announcement_date": ledger["announcement_date"],
        "page_size": page_size,
        "page_max_bytes": page_max_bytes,
        "page_count": len(pages),
        "candidate_count": len(candidates),
        "cv_appendix_only_count": len(cv_appendix_only),
        "screening_count": len(screening_papers),
        "already_processed_categories": already_processed_categories,
        "no_new_announcement": ledger["no_new_announcement"],
        "ledger_path": str(ledger_path),
        "ledger_sha256": ledger_sha256,
        "checkpoints": checkpoint_records,
        "pages": pages,
    }
    manifest_path = run_dir / "screening-manifest.json"
    if manifest_path.exists():
        existing = read_json(manifest_path)
        decision_paths = sorted(run_dir.glob("screening-decision-*.json"))
        unchanged = existing == manifest
        if unchanged:
            if not ledger_path.is_file() or hashlib.sha256(
                ledger_path.read_bytes()
            ).hexdigest() != ledger_sha256:
                unchanged = False
            for record in pages:
                page_path = Path(record["path"])
                if not page_path.is_file() or hashlib.sha256(
                    page_path.read_bytes()
                ).hexdigest() != record["sha256"]:
                    unchanged = False
                    break
        if unchanged:
            return {
                "run_id": run_id,
                "announcement_date": ledger["announcement_date"],
                "retrieved": retrieved_count,
                "work_input": deduplicated["input_count"],
                "unique": deduplicated["unique_count"],
                "already_known": len(deduplicated["excluded"]),
                "hidden": len(hidden),
                "candidates": len(candidates),
                "cv_appendix_only": len(cv_appendix_only),
                "screening": len(screening_papers),
                "pages": len(pages),
                "no_new_announcement": ledger["no_new_announcement"],
                "manifest": str(manifest_path),
                "reused": True,
            }
        if decision_paths:
            raise DigestValidationError(
                "screening_source_changed: existing decisions are bound to a different "
                "screening source"
            )

    atomic_write_json(ledger_path, ledger)
    for page_path, page in page_values:
        atomic_write_json(page_path, page)
    atomic_write_json(manifest_path, manifest)
    return {
        "run_id": run_id,
        "announcement_date": ledger["announcement_date"],
        "retrieved": retrieved_count,
        "work_input": deduplicated["input_count"],
        "unique": deduplicated["unique_count"],
        "already_known": len(deduplicated["excluded"]),
        "hidden": len(hidden),
        "candidates": len(candidates),
        "cv_appendix_only": len(cv_appendix_only),
        "screening": len(screening_papers),
        "pages": len(pages),
        "no_new_announcement": ledger["no_new_announcement"],
        "manifest": str(manifest_path),
        "reused": False,
    }


def _run_directory(root: Path, run_id: str) -> Path:
    return announcement_batch_output_path(root.resolve(), run_id, TRACKED_CATEGORIES[0]).parent


def _load_screening_state(
    root: Path,
    run_id: str,
) -> tuple[Path, dict[str, Any], dict[str, Any], list[tuple[dict[str, Any], dict[str, Any]]]]:
    run_dir = _run_directory(root, run_id)
    manifest_path = run_dir / "screening-manifest.json"
    manifest = read_json(manifest_path)
    if manifest.get("run_id") != run_id:
        raise DigestValidationError("screening manifest run ID mismatch")
    ledger_path = Path(str(manifest.get("ledger_path") or ""))
    if not ledger_path.is_file():
        raise DigestValidationError("screening ledger is missing")
    if hashlib.sha256(ledger_path.read_bytes()).hexdigest() != manifest.get(
        "ledger_sha256"
    ):
        raise DigestValidationError("screening ledger hash mismatch")
    ledger = read_json(ledger_path)
    if ledger.get("run_id") != run_id:
        raise DigestValidationError("screening ledger run ID mismatch")
    page_records = manifest.get("pages")
    if not isinstance(page_records, list) or manifest.get("page_count") != len(
        page_records
    ):
        raise DigestValidationError("screening manifest page count mismatch")
    pages: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for expected_page, record in enumerate(page_records, start=1):
        if not isinstance(record, dict) or record.get("page") != expected_page:
            raise DigestValidationError("screening manifest page order mismatch")
        path = Path(str(record.get("path") or ""))
        if not path.is_file():
            raise DigestValidationError(f"missing screening page {expected_page}")
        if hashlib.sha256(path.read_bytes()).hexdigest() != record.get("sha256"):
            raise DigestValidationError(f"screening page {expected_page} hash mismatch")
        page = read_json(path)
        papers = page.get("papers")
        if (
            page.get("run_id") != run_id
            or page.get("page") != expected_page
            or not isinstance(papers, list)
            or record.get("count") != len(papers)
        ):
            raise DigestValidationError(
                f"screening page {expected_page} does not match its manifest"
            )
        pages.append((record, page))
    return run_dir, manifest, ledger, pages


def _validate_screening_decision(
    run_id: str,
    record: dict[str, Any],
    page: dict[str, Any],
    value: dict[str, Any],
) -> dict[str, Any]:
    page_number = int(record["page"])
    if value.get("run_id") != run_id or value.get("page") != page_number:
        raise DigestValidationError(
            f"screening decision run/page mismatch for page {page_number}"
        )
    if value.get("source_page_sha256") != record.get("sha256"):
        raise DigestValidationError(
            f"screening decision source hash mismatch for page {page_number}"
        )
    decisions = value.get("decisions")
    papers = page["papers"]
    if not isinstance(decisions, list) or len(decisions) != len(papers):
        raise DigestValidationError(
            f"screening decision count mismatch for page {page_number}"
        )
    expected_ids = [str(paper.get("arxiv_id")) for paper in papers]
    received_ids = [
        str(decision.get("arxiv_id")) if isinstance(decision, dict) else ""
        for decision in decisions
    ]
    if received_ids != expected_ids:
        raise DigestValidationError(
            f"screening decision IDs/order mismatch for page {page_number}"
        )
    normalized: list[dict[str, Any]] = []
    for paper, decision in zip(papers, decisions):
        arxiv_id = str(paper["arxiv_id"])
        if not isinstance(decision, dict):
            raise DigestValidationError(f"screening decision for {arxiv_id} must be an object")
        priority_class = decision.get("priority_class")
        if priority_class not in SCREENING_PRIORITY_CLASSES:
            raise DigestValidationError(
                f"screening decision priority_class is invalid for {arxiv_id}"
            )
        if paper.get("screening_scope") == "cs_cv_appendix_only" and priority_class in {
            "focus_candidate",
            "watch_candidate",
        }:
            raise DigestValidationError(
                f"cs_cv_appendix_only paper {arxiv_id} cannot be selected"
            )
        score = decision.get("relevance_score")
        if type(score) is not int or not 0 <= score <= 100:
            raise DigestValidationError(
                f"screening decision relevance_score is invalid for {arxiv_id}"
            )
        topic_group = decision.get("topic_group")
        if topic_group not in TOPIC_GROUPS:
            raise DigestValidationError(
                f"screening decision topic_group is invalid for {arxiv_id}"
            )
        core_conclusion = decision.get("core_conclusion")
        if validate_chinese_prose(
            core_conclusion, f"screening decision core_conclusion for {arxiv_id}"
        ):
            raise DigestValidationError(
                f"screening decision core_conclusion must contain Chinese prose for {arxiv_id}"
            )
        evidence_level = decision.get("evidence_level")
        if evidence_level not in EVIDENCE_LEVELS:
            raise DigestValidationError(
                f"screening decision evidence_level is invalid for {arxiv_id}"
            )
        exclusion = decision.get("semantic_exclusion_reason")
        if exclusion is not None and exclusion not in SEMANTIC_EXCLUSION_REASONS:
            raise DigestValidationError(
                f"screening semantic exclusion reason is invalid for {arxiv_id}"
            )
        if exclusion is not None and priority_class != "exclude":
            raise DigestValidationError(
                f"semantic exclusion requires priority_class exclude for {arxiv_id}"
            )
        normalized.append(
            {
                "arxiv_id": arxiv_id,
                "priority_class": priority_class,
                "relevance_score": score,
                "topic_group": topic_group,
                "core_conclusion": str(core_conclusion).strip(),
                "evidence_level": evidence_level,
                "semantic_exclusion_reason": exclusion,
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "page": page_number,
        "source_page_sha256": record["sha256"],
        "decisions": normalized,
    }


def record_screening_page(
    root: Path,
    run_id: str,
    page_number: int,
    input_path: Path,
) -> dict[str, Any]:
    configure_public_runtime(root)
    root = root.resolve()
    initialize_runtime(root)
    with _exclusive_gate_state_lock(root / "digest-transaction.lock"):
        run_dir, _manifest, _ledger, pages = _load_screening_state(root, run_id)
        if not 1 <= page_number <= len(pages):
            raise DigestValidationError("screening page number is out of range")
        record, page = pages[page_number - 1]
        value = _validate_screening_decision(
            run_id,
            record,
            page,
            read_json(input_path.resolve()),
        )
        output = run_dir / f"screening-decision-{page_number:03d}.json"
        if output.exists():
            existing = read_json(output)
            if existing != value:
                raise DigestValidationError(
                    f"screening decision page {page_number} already exists with different content"
                )
            replayed = True
        else:
            atomic_write_json(output, value)
            replayed = False
        return {
            "run_id": run_id,
            "page": page_number,
            "recorded": len(value["decisions"]),
            "path": str(output),
            "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
            "replayed": replayed,
        }


def _load_all_screening_decisions(
    run_dir: Path,
    run_id: str,
    pages: list[tuple[dict[str, Any], dict[str, Any]]],
    *,
    require_complete: bool,
) -> tuple[list[dict[str, Any]], list[int]]:
    decisions: list[dict[str, Any]] = []
    missing: list[int] = []
    for record, page in pages:
        number = int(record["page"])
        path = run_dir / f"screening-decision-{number:03d}.json"
        if not path.exists():
            missing.append(number)
            continue
        value = _validate_screening_decision(run_id, record, page, read_json(path))
        decisions.extend(value["decisions"])
    if require_complete and missing:
        raise DigestValidationError(
            "screening is incomplete; missing decision page " + str(missing[0])
        )
    return decisions, missing


def _validate_enrichment_record(
    run_id: str,
    record: dict[str, Any],
    page: dict[str, Any],
    value: dict[str, Any],
) -> dict[str, Any]:
    page_number = int(record["page"])
    if value.get("run_id") != run_id or value.get("page") != page_number:
        raise DigestValidationError(
            f"enrichment decision run/page mismatch for page {page_number}"
        )
    if value.get("source_page_sha256") != record.get("sha256"):
        raise DigestValidationError(
            f"enrichment decision source hash mismatch for page {page_number}"
        )
    enrichments = value.get("enrichments")
    items = page.get("items")
    if not isinstance(enrichments, list) or not isinstance(items, list) or len(
        enrichments
    ) != len(items):
        raise DigestValidationError(
            f"enrichment decision count mismatch for page {page_number}"
        )
    expected_ids = [str(item.get("arxiv_id")) for item in items]
    received_ids = [
        str(item.get("arxiv_id")) if isinstance(item, dict) else ""
        for item in enrichments
    ]
    if received_ids != expected_ids:
        raise DigestValidationError(
            f"enrichment decision IDs/order mismatch for page {page_number}"
        )
    normalized: list[dict[str, Any]] = []
    for source, enrichment in zip(items, enrichments):
        arxiv_id = str(source["arxiv_id"])
        if not isinstance(enrichment, dict):
            raise DigestValidationError(f"enrichment for {arxiv_id} must be an object")
        target = source.get("target")
        fields = (
            SELECTED_ENRICHMENT_FIELDS
            if target in {"focus", "watch"}
            else DETAILED_REMAINDER_ENRICHMENT_FIELDS
        )
        missing = [field for field in fields if field not in enrichment]
        if missing:
            raise DigestValidationError(
                f"enrichment for {arxiv_id} is missing {', '.join(missing)}"
            )
        result = {"arxiv_id": arxiv_id}
        for field in fields:
            field_value = enrichment[field]
            if field == "evidence_level":
                if field_value not in EVIDENCE_LEVELS:
                    raise DigestValidationError(
                        f"enrichment evidence_level is invalid for {arxiv_id}"
                    )
            elif validate_chinese_prose(
                field_value, f"enrichment {field} for {arxiv_id}"
            ):
                raise DigestValidationError(
                    f"enrichment {field} must contain Chinese prose for {arxiv_id}"
                )
            result[field] = str(field_value).strip()
        normalized.append(result)
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "page": page_number,
        "source_page_sha256": record["sha256"],
        "enrichments": normalized,
    }


def _load_enrichment_state(
    root: Path,
    run_id: str,
) -> tuple[Path, dict[str, Any], dict[str, Any], list[tuple[dict[str, Any], dict[str, Any]]]]:
    run_dir = _run_directory(root, run_id)
    manifest_path = run_dir / "enrichment-manifest.json"
    manifest = read_json(manifest_path)
    if manifest.get("run_id") != run_id:
        raise DigestValidationError("enrichment manifest run ID mismatch")
    result_path = Path(str(manifest.get("screening_result_path") or ""))
    if not result_path.is_file() or hashlib.sha256(
        result_path.read_bytes()
    ).hexdigest() != manifest.get("screening_result_sha256"):
        raise DigestValidationError("screening result hash mismatch")
    screening_result = read_json(result_path)
    records = manifest.get("pages")
    if not isinstance(records, list) or manifest.get("page_count") != len(records):
        raise DigestValidationError("enrichment manifest page count mismatch")
    pages: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for expected, record in enumerate(records, start=1):
        if not isinstance(record, dict) or record.get("page") != expected:
            raise DigestValidationError("enrichment manifest page order mismatch")
        path = Path(str(record.get("path") or ""))
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != record.get(
            "sha256"
        ):
            raise DigestValidationError(f"enrichment page {expected} hash mismatch")
        page = read_json(path)
        items = page.get("items")
        if (
            page.get("run_id") != run_id
            or page.get("page") != expected
            or not isinstance(items, list)
            or record.get("count") != len(items)
        ):
            raise DigestValidationError(
                f"enrichment page {expected} does not match its manifest"
            )
        pages.append((record, page))
    return run_dir, manifest, screening_result, pages


def _screening_decision_contract(
    run_id: str,
    record: dict[str, Any],
) -> dict[str, Any]:
    page_number = int(record["page"])
    return {
        "schema_version": SCHEMA_VERSION,
        "input_template": {
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id,
            "page": page_number,
            "source_page_sha256": record["sha256"],
            "decisions": [],
        },
        "expected_decision_count": int(record["count"]),
        "preserve_source_order": True,
        "decision_fields": list(SCREENING_DECISION_FIELDS),
        "priority_classes": list(SCREENING_PRIORITY_CLASSES),
        "topic_groups": list(TOPIC_GROUPS),
        "evidence_levels": list(EVIDENCE_LEVELS),
        "semantic_exclusion_reasons": list(SEMANTIC_EXCLUSION_REASONS),
        "semantic_exclusion_requires_priority_class": "exclude",
        "appendix_only_forbidden_priority_classes": [
            "focus_candidate",
            "watch_candidate",
        ],
    }


def _enrichment_decision_contract(
    run_id: str,
    record: dict[str, Any],
) -> dict[str, Any]:
    page_number = int(record["page"])
    return {
        "schema_version": SCHEMA_VERSION,
        "input_template": {
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id,
            "page": page_number,
            "source_page_sha256": record["sha256"],
            "enrichments": [],
        },
        "expected_enrichment_count": int(record["count"]),
        "preserve_source_order": True,
        "common_fields": ["arxiv_id"],
        "fields_by_target": {
            "focus": list(SELECTED_ENRICHMENT_FIELDS),
            "watch": list(SELECTED_ENRICHMENT_FIELDS),
            "detailed_remainder": list(DETAILED_REMAINDER_ENRICHMENT_FIELDS),
        },
        "evidence_levels": list(EVIDENCE_LEVELS),
    }


def screening_status(root: Path, run_id: str) -> dict[str, Any]:
    configure_public_runtime(root)
    root = root.resolve()
    run_dir, manifest, _ledger, pages = _load_screening_state(root, run_id)
    if manifest.get("no_new_announcement") is True:
        return {
            "run_id": run_id,
            "phase": "no_new_announcement",
            "completed_pages": 0,
            "total_pages": 0,
            "next_page": None,
            "next_action": "no_work",
        }
    _decisions, missing = _load_all_screening_decisions(
        run_dir, run_id, pages, require_complete=False
    )
    if missing:
        number = missing[0]
        record = manifest["pages"][number - 1]
        return {
            "run_id": run_id,
            "phase": "screening",
            "completed_pages": len(pages) - len(missing),
            "total_pages": len(pages),
            "next_page": str(Path(record["path"])),
            "next_page_number": number,
            "next_page_sha256": record["sha256"],
            "decision_contract": _screening_decision_contract(run_id, record),
            "next_action": "record_screening_page",
        }
    enrichment_manifest = run_dir / "enrichment-manifest.json"
    if not enrichment_manifest.exists():
        return {
            "run_id": run_id,
            "phase": "screening_complete",
            "completed_pages": len(pages),
            "total_pages": len(pages),
            "next_page": None,
            "next_action": "prepare_enrichment",
        }
    _erun_dir, enrichment, _result, enrichment_pages = _load_enrichment_state(
        root, run_id
    )
    missing_enrichment: list[int] = []
    for record, page in enrichment_pages:
        number = int(record["page"])
        path = run_dir / f"enrichment-decision-{number:03d}.json"
        if not path.exists():
            missing_enrichment.append(number)
        else:
            _validate_enrichment_record(run_id, record, page, read_json(path))
    if missing_enrichment:
        number = missing_enrichment[0]
        record = enrichment["pages"][number - 1]
        return {
            "run_id": run_id,
            "phase": "enrichment",
            "completed_pages": len(enrichment_pages) - len(missing_enrichment),
            "total_pages": len(enrichment_pages),
            "next_page": str(Path(record["path"])),
            "next_page_number": number,
            "next_page_sha256": record["sha256"],
            "decision_contract": _enrichment_decision_contract(run_id, record),
            "next_action": "record_enrichment_page",
        }
    return {
        "run_id": run_id,
        "phase": "ready_to_assemble",
        "completed_pages": len(enrichment_pages),
        "total_pages": len(enrichment_pages),
        "next_page": None,
        "next_action": "assemble_digest",
    }


def prepare_enrichment(
    root: Path,
    run_id: str,
    *,
    page_size: int = 20,
    page_max_bytes: int = 32_000,
) -> dict[str, Any]:
    configure_public_runtime(root)
    if not 1 <= page_size <= 100:
        raise DigestValidationError("enrichment page size must be from 1 to 100")
    if not 8_000 <= page_max_bytes <= 32_000:
        raise DigestValidationError(
            "enrichment page maximum bytes must be from 8000 to 32000"
        )
    root = root.resolve()
    initialize_runtime(root)
    with _exclusive_gate_state_lock(root / "digest-transaction.lock"):
        run_dir, screening_manifest, _ledger, pages = _load_screening_state(
            root, run_id
        )
        decisions, _missing = _load_all_screening_decisions(
            run_dir, run_id, pages, require_complete=True
        )
        papers = [paper for _record, page in pages for paper in page["papers"]]
        if len(papers) != len(decisions):
            raise DigestValidationError("screening papers and decisions do not align")
        entries = []
        for paper, decision in zip(papers, decisions):
            item = copy.deepcopy(paper)
            item.update(copy.deepcopy(decision))
            entries.append(item)
        eligible = [
            item for item in entries if item.get("semantic_exclusion_reason") is None
        ]
        selectable = [
            item for item in eligible if item.get("screening_scope") == "selection_candidate"
        ]
        focus_candidates = sorted(
            [item for item in selectable if item["priority_class"] == "focus_candidate"],
            key=paper_sort_key,
        )
        focus = focus_candidates[:10]
        watch_pool = focus_candidates[10:] + [
            item for item in selectable if item["priority_class"] == "watch_candidate"
        ]
        watch = sorted(watch_pool, key=paper_sort_key)[:10]
        selected_ids = {str(item["arxiv_id"]) for item in focus + watch}
        remainder = sorted(
            [
                item
                for item in eligible
                if REPORT_CATEGORY in item.get("query_sources", [])
                and str(item["arxiv_id"]) not in selected_ids
            ],
            key=paper_sort_key,
        )
        detailed = remainder[:50]
        compact = remainder[50:]
        target_by_id = {
            **{str(item["arxiv_id"]): "focus" for item in focus},
            **{str(item["arxiv_id"]): "watch" for item in watch},
            **{str(item["arxiv_id"]): "detailed_remainder" for item in detailed},
        }
        source_by_id = {str(paper["arxiv_id"]): paper for paper in papers}
        decision_by_id = {str(item["arxiv_id"]): item for item in decisions}
        enrichment_items = []
        for arxiv_id, target in target_by_id.items():
            enrichment_items.append(
                {
                    "arxiv_id": arxiv_id,
                    "target": target,
                    "paper": copy.deepcopy(source_by_id[arxiv_id]),
                    "screening": copy.deepcopy(decision_by_id[arxiv_id]),
                }
            )

        groups: list[list[dict[str, Any]]] = []
        current: list[dict[str, Any]] = []
        for item in enrichment_items:
            proposed = current + [item]
            value = {
                "schema_version": SCHEMA_VERSION,
                "run_id": run_id,
                "page": len(groups) + 1,
                "page_size": len(proposed),
                "items": proposed,
            }
            if current and (
                len(proposed) > page_size or len(_json_bytes(value)) > page_max_bytes
            ):
                groups.append(current)
                current = [item]
                single = {
                    "schema_version": SCHEMA_VERSION,
                    "run_id": run_id,
                    "page": len(groups) + 1,
                    "page_size": 1,
                    "items": current,
                }
                if len(_json_bytes(single)) > page_max_bytes:
                    raise DigestValidationError(
                        f"enrichment record {item['arxiv_id']} exceeds the page byte limit"
                    )
            else:
                if len(_json_bytes(value)) > page_max_bytes:
                    raise DigestValidationError(
                        f"enrichment record {item['arxiv_id']} exceeds the page byte limit"
                    )
                current = proposed
        if current:
            groups.append(current)

        screening_result = {
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id,
            "focus_ids": [str(item["arxiv_id"]) for item in focus],
            "watch_ids": [str(item["arxiv_id"]) for item in watch],
            "detailed_remainder_ids": [str(item["arxiv_id"]) for item in detailed],
            "compact_remainder_ids": [str(item["arxiv_id"]) for item in compact],
            "semantic_exclusions": [
                {
                    "arxiv_id": str(item["arxiv_id"]),
                    "reason": item["semantic_exclusion_reason"],
                    "query_sources": list(item.get("query_sources", [])),
                }
                for item in entries
                if item.get("semantic_exclusion_reason") is not None
            ],
            "top_three_full_text_ids": [
                str(item["arxiv_id"]) for item in (focus + watch)[:3]
            ],
        }
        result_path = run_dir / "screening-result.json"
        page_values: list[tuple[Path, dict[str, Any]]] = []
        page_records: list[dict[str, Any]] = []
        for number, items in enumerate(groups, start=1):
            value = {
                "schema_version": SCHEMA_VERSION,
                "run_id": run_id,
                "page": number,
                "page_size": len(items),
                "items": items,
            }
            path = run_dir / f"enrichment-page-{number:03d}.json"
            payload = _json_bytes(value)
            page_values.append((path, value))
            page_records.append(
                {
                    "page": number,
                    "path": str(path),
                    "count": len(items),
                    "bytes": len(payload),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                }
            )
        decision_records = []
        for record, _page in pages:
            path = run_dir / f"screening-decision-{int(record['page']):03d}.json"
            decision_records.append(
                {
                    "page": record["page"],
                    "path": str(path),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
            )
        enrichment_manifest = {
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id,
            "page_size": page_size,
            "page_max_bytes": page_max_bytes,
            "page_count": len(page_records),
            "screening_manifest_sha256": hashlib.sha256(
                (run_dir / "screening-manifest.json").read_bytes()
            ).hexdigest(),
            "screening_decisions": decision_records,
            "screening_result_path": str(result_path),
            "screening_result_sha256": _json_sha256(screening_result),
            "pages": page_records,
        }
        manifest_path = run_dir / "enrichment-manifest.json"
        if manifest_path.exists():
            existing = read_json(manifest_path)
            decision_paths = sorted(run_dir.glob("enrichment-decision-*.json"))
            unchanged = existing == enrichment_manifest
            if unchanged:
                unchanged = result_path.is_file() and hashlib.sha256(
                    result_path.read_bytes()
                ).hexdigest() == enrichment_manifest["screening_result_sha256"]
                for record in page_records:
                    path = Path(record["path"])
                    if not path.is_file() or hashlib.sha256(
                        path.read_bytes()
                    ).hexdigest() != record["sha256"]:
                        unchanged = False
                        break
            if unchanged:
                return {
                    "run_id": run_id,
                    "focus": len(focus),
                    "watch": len(watch),
                    "detailed_remainder": len(detailed),
                    "compact_remainder": len(compact),
                    "pages": len(page_records),
                    "top_three_full_text_ids": screening_result[
                        "top_three_full_text_ids"
                    ],
                    "manifest": str(manifest_path),
                    "reused": True,
                }
            if decision_paths:
                raise DigestValidationError(
                    "enrichment_source_changed: existing enrichment decisions are bound "
                    "to different screening results"
                )
        atomic_write_json(result_path, screening_result)
        for path, value in page_values:
            atomic_write_json(path, value)
        atomic_write_json(manifest_path, enrichment_manifest)
        return {
            "run_id": run_id,
            "focus": len(focus),
            "watch": len(watch),
            "detailed_remainder": len(detailed),
            "compact_remainder": len(compact),
            "pages": len(page_records),
            "top_three_full_text_ids": screening_result["top_three_full_text_ids"],
            "manifest": str(manifest_path),
            "reused": False,
        }


def record_enrichment_page(
    root: Path,
    run_id: str,
    page_number: int,
    input_path: Path,
) -> dict[str, Any]:
    configure_public_runtime(root)
    root = root.resolve()
    initialize_runtime(root)
    with _exclusive_gate_state_lock(root / "digest-transaction.lock"):
        run_dir, _manifest, _result, pages = _load_enrichment_state(root, run_id)
        if not 1 <= page_number <= len(pages):
            raise DigestValidationError("enrichment page number is out of range")
        record, page = pages[page_number - 1]
        value = _validate_enrichment_record(
            run_id,
            record,
            page,
            read_json(input_path.resolve()),
        )
        output = run_dir / f"enrichment-decision-{page_number:03d}.json"
        if output.exists():
            existing = read_json(output)
            if existing != value:
                raise DigestValidationError(
                    f"enrichment decision page {page_number} already exists with different content"
                )
            replayed = True
        else:
            atomic_write_json(output, value)
            replayed = False
        return {
            "run_id": run_id,
            "page": page_number,
            "recorded": len(value["enrichments"]),
            "path": str(output),
            "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
            "replayed": replayed,
        }


def assemble_digest(
    root: Path,
    run_id: str,
    narrative_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    configure_public_runtime(root)
    root = root.resolve()
    run_dir, _screening_manifest, ledger, screening_pages = _load_screening_state(
        root, run_id
    )
    _erun_dir, _enrichment_manifest, screening_result, enrichment_pages = (
        _load_enrichment_state(root, run_id)
    )
    narrative_file = narrative_path.resolve()
    if not narrative_file.is_file():
        raise DigestValidationError(f"missing narrative JSON file: {narrative_file}")
    if narrative_file.stat().st_size > 32_000:
        raise DigestValidationError("narrative JSON must not exceed 32000 bytes")
    narrative = read_json(narrative_file)
    if narrative.get("run_id") not in {None, run_id}:
        raise DigestValidationError("narrative run ID mismatch")
    if validate_chinese_prose(narrative.get("overview"), "narrative.overview"):
        raise DigestValidationError("narrative overview must contain Chinese prose")
    for field in ("trends", "actionable_insights"):
        values = narrative.get(field)
        if not isinstance(values, list) or any(
            validate_chinese_prose(value, f"narrative.{field}") for value in values
        ):
            raise DigestValidationError(f"narrative {field} must contain Chinese prose")
    arxiv_tools = narrative.get("arxiv_tools")
    if not isinstance(arxiv_tools, list) or not arxiv_tools or any(
        not isinstance(value, str) or not value.strip() for value in arxiv_tools
    ):
        raise DigestValidationError("narrative arxiv_tools must be a non-empty string array")
    next_cursor = narrative.get("next_version_check_cursor")
    if type(next_cursor) is not int or next_cursor < 0:
        raise DigestValidationError(
            "narrative next_version_check_cursor must be a non-negative integer"
        )
    source_papers = [
        paper for _record, page in screening_pages for paper in page["papers"]
    ]
    source_by_id = {str(paper["arxiv_id"]): paper for paper in source_papers}
    screening_decisions, _missing = _load_all_screening_decisions(
        run_dir, run_id, screening_pages, require_complete=True
    )
    decision_by_id = {
        str(decision["arxiv_id"]): decision for decision in screening_decisions
    }
    enrichment_by_id: dict[str, dict[str, Any]] = {}
    for record, page in enrichment_pages:
        number = int(record["page"])
        path = run_dir / f"enrichment-decision-{number:03d}.json"
        if not path.exists():
            raise DigestValidationError(
                f"enrichment is incomplete; missing decision page {number}"
            )
        value = _validate_enrichment_record(run_id, record, page, read_json(path))
        for enrichment in value["enrichments"]:
            enrichment_by_id[str(enrichment["arxiv_id"])] = enrichment

    def selected_paper(arxiv_id: str) -> dict[str, Any]:
        paper = copy.deepcopy(source_by_id[arxiv_id])
        decision = decision_by_id[arxiv_id]
        enrichment = enrichment_by_id[arxiv_id]
        paper["relevance_score"] = decision["relevance_score"]
        paper["topic_group"] = decision["topic_group"]
        for field in SELECTED_ENRICHMENT_FIELDS:
            paper[field] = enrichment[field]
        return {field: paper.get(field) for field in PAPER_FIELDS}

    focus = [selected_paper(arxiv_id) for arxiv_id in screening_result["focus_ids"]]
    watch = [selected_paper(arxiv_id) for arxiv_id in screening_result["watch_ids"]]
    detailed = []
    for arxiv_id in screening_result["detailed_remainder_ids"]:
        paper = copy.deepcopy(source_by_id[arxiv_id])
        decision = decision_by_id[arxiv_id]
        paper["relevance_score"] = decision["relevance_score"]
        paper["core_conclusion"] = decision["core_conclusion"]
        enrichment = enrichment_by_id[arxiv_id]
        for field in DETAILED_REMAINDER_ENRICHMENT_FIELDS:
            paper[field] = enrichment[field]
        detailed.append({field: paper.get(field) for field in CV_DETAILED_FIELDS})
    compact = []
    for arxiv_id in screening_result["compact_remainder_ids"]:
        paper = copy.deepcopy(source_by_id[arxiv_id])
        decision = decision_by_id[arxiv_id]
        paper["relevance_score"] = decision["relevance_score"]
        paper["core_conclusion"] = decision["core_conclusion"]
        compact.append({field: paper.get(field) for field in CV_COMPACT_FIELDS})
    exclusion_stats = copy.deepcopy(ledger["exclusion_stats"])
    for item in screening_result["semantic_exclusions"]:
        reason = item["reason"]
        exclusion_stats[reason] += 1
        exclusion_stats["total_hidden"] += 1
        if REPORT_CATEGORY in item.get("query_sources", []):
            exclusion_stats["cs_cv_total_hidden"] += 1
    report_date = str(ledger["announcement_date"])
    digest = {
        "schema_version": LEGACY_DAILY_SCHEMA_VERSION,
        "run_id": run_id,
        "date": report_date,
        "retrieval_window": {
            "basis": "announcement_batch",
            "from": report_date,
            "to": report_date,
        },
        "stats": {
            "retrieved": int(ledger["retrieved_count"]),
            "unique": int(ledger["unique_count"]),
            "candidates": int(ledger["candidate_count"]),
            "focus": len(focus),
            "watch": len(watch),
            "cv_remainder": len(detailed) + len(compact),
            "excluded_hidden": int(exclusion_stats["total_hidden"]),
        },
        "overview": str(narrative["overview"]).strip(),
        "reading_order": [],
        "focus_papers": focus,
        "watch_papers": watch,
        "trends": [str(value).strip() for value in narrative["trends"]],
        "actionable_insights": [
            str(value).strip() for value in narrative["actionable_insights"]
        ],
        "retrieval_coverage": copy.deepcopy(ledger["retrieval_coverage"]),
        "exclusion_stats": exclusion_stats,
        "cv_daily_remainder": {
            "total": len(detailed) + len(compact),
            "detailed": detailed,
            "compact": compact,
        },
        "arxiv_tools": [str(value).strip() for value in arxiv_tools],
        "next_version_check_cursor": next_cursor,
    }
    digest = canonicalize_digest(digest)
    validate_digest(digest)
    output = output_path.resolve()
    if output != run_dir and run_dir not in output.parents:
        raise DigestValidationError("assembled digest output must stay inside the stable run directory")
    atomic_write_json(output, digest)
    return {
        "run_id": run_id,
        "digest": str(output),
        "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "focus": len(focus),
        "watch": len(watch),
        "cv_remainder": len(detailed) + len(compact),
    }


def require_fields(value: dict[str, Any], fields: tuple[str, ...], label: str) -> list[str]:
    return [f"{label}.{field}" for field in fields if field not in value]


def validate_chinese_prose(value: Any, label: str) -> list[str]:
    if not isinstance(value, str) or not CHINESE_PROSE_RE.search(value):
        return [f"{label} must contain Chinese explanatory prose"]
    return []


def validate_announcement_identity(
    paper: dict[str, Any],
    label: str,
) -> list[str]:
    errors: list[str] = []
    announcement_date = paper.get("announcement_date")
    if not isinstance(announcement_date, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}",
        announcement_date,
    ):
        errors.append(f"{label}.announcement_date must use YYYY-MM-DD")
    announcement_types = paper.get("announcement_types")
    if (
        not isinstance(announcement_types, list)
        or not announcement_types
        or any(value not in ANNOUNCEMENT_TYPES for value in announcement_types)
    ):
        errors.append(
            f"{label}.announcement_types must contain recognized announcement types"
        )
    return errors


def validate_digest_v4(digest: dict[str, Any]) -> None:
    public_profile = _require_public_configuration()
    if digest.get("report_category") != REPORT_CATEGORY:
        raise DigestValidationError("digest.report_category must match the configured complete-report category")
    if digest.get("public_profile_sha256") != public_profile["_config_sha256"]:
        raise DigestValidationError("digest.public_profile_sha256 must match this state root's immutable configuration")
    if type(digest.get("report_already_known_count")) is not int or digest["report_already_known_count"] < 0:
        raise DigestValidationError("digest.report_already_known_count must be a non-negative integer from the frozen inventory")
    _validate_public_report_accounting(digest)
    errors: list[str] = []
    required = (
        "schema_version",
        "coverage_policy",
        "run_id",
        "date",
        "retrieval_window",
        "stats",
        "inventory_summary",
        "overview",
        "reading_order",
        "focus_papers",
        "watch_papers",
        "trends",
        "actionable_insights",
        "retrieval_coverage",
        "exclusion_stats",
        "cs_cv_report",
        "arxiv_tools",
        "local_reports",
    )
    errors.extend(require_fields(digest, required, "digest"))
    if digest.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"digest.schema_version must be {SCHEMA_VERSION}")
    if digest.get("coverage_policy") != DAILY_COVERAGE_POLICY:
        errors.append(f"digest.coverage_policy must be {DAILY_COVERAGE_POLICY}")
    digest_date = digest.get("date")
    if not isinstance(digest_date, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}", str(digest_date or "")
    ):
        errors.append("digest.date must use YYYY-MM-DD")
    retrieval_window = digest.get("retrieval_window")
    if not isinstance(retrieval_window, dict) or (
        retrieval_window.get("basis") != "announcement_batch"
        or retrieval_window.get("from") != digest_date
        or retrieval_window.get("to") != digest_date
    ):
        errors.append(
            "digest.retrieval_window must bind exactly one digest.date announcement batch"
        )
    errors.extend(validate_chinese_prose(digest.get("overview"), "digest.overview"))
    for field in ("trends", "actionable_insights"):
        values = digest.get(field)
        if not isinstance(values, list) or any(
            validate_chinese_prose(value, f"digest.{field}") for value in values
        ):
            errors.append(f"digest.{field} must be a Chinese prose array")

    selected_ids: set[str] = set()
    for collection_name, minimum in (
        ("focus_papers", FOCUS_SCORE_MINIMUM),
        ("watch_papers", WATCH_SCORE_MINIMUM),
    ):
        papers = digest.get(collection_name)
        if not isinstance(papers, list):
            errors.append(f"digest.{collection_name} must be an array")
            continue
        maximum = MAX_EMAIL_FOCUS if collection_name == "focus_papers" else MAX_EMAIL_WATCH
        if len(papers) > maximum:
            errors.append(f"digest.{collection_name} exceeds {maximum} papers")
        for index, paper in enumerate(papers):
            label = f"digest.{collection_name}[{index}]"
            if not isinstance(paper, dict):
                errors.append(f"{label} must be an object")
                continue
            errors.extend(require_fields(paper, V3_PAPER_FIELDS, label))
            errors.extend(validate_announcement_identity(paper, label))
            if paper.get("announcement_date") != digest_date:
                errors.append(f"{label}.announcement_date must equal digest.date")
            score = paper.get("relevance_score")
            if type(score) is not int or not minimum <= score <= 100:
                errors.append(f"{label}.relevance_score must be {minimum}..100")
            if paper.get("topic_group") not in TOPIC_GROUPS:
                errors.append(f"{label}.topic_group is invalid")
            if paper.get("evidence_level") != "abstract":
                errors.append(f"{label}.evidence_level must be abstract")
            for field in PAPER_CHINESE_PROSE_FIELDS:
                errors.extend(validate_chinese_prose(paper.get(field), f"{label}.{field}"))
            try:
                base_id, parsed_version = normalize_arxiv_id(
                    str(paper.get("arxiv_id", "")), str(paper.get("pdf_url", ""))
                )
                if base_id != paper.get("arxiv_id"):
                    errors.append(f"{label}.arxiv_id must be unversioned")
                if paper.get("version") is not None and paper.get("version") != parsed_version:
                    errors.append(f"{label}.version must match the PDF URL")
                if base_id in selected_ids:
                    errors.append(f"selected paper {base_id} is duplicated")
                selected_ids.add(base_id)
            except DigestValidationError as exc:
                errors.append(f"{label}: {exc}")

    stats = digest.get("stats")
    required_stats = (
        "retrieved",
        "unique",
        "candidates",
        "model_reviewed",
        "budget_deferred",
        "local_background",
        "focus",
        "watch",
        "cv_remainder",
        "excluded_hidden",
    )
    if not isinstance(stats, dict):
        errors.append("digest.stats must be an object")
    else:
        errors.extend(require_fields(stats, required_stats, "digest.stats"))
        for field in required_stats:
            value = stats.get(field)
            if type(value) is not int or value < 0:
                errors.append(f"digest.stats.{field} must be a non-negative integer")
        if isinstance(digest.get("focus_papers"), list) and stats.get("focus") != len(digest["focus_papers"]):
            errors.append("digest.stats.focus must equal focus_papers length")
        if isinstance(digest.get("watch_papers"), list) and stats.get("watch") != len(digest["watch_papers"]):
            errors.append("digest.stats.watch must equal watch_papers length")
        if isinstance(stats.get("model_reviewed"), int) and stats["model_reviewed"] > DEFAULT_REVIEW_CANDIDATE_LIMIT:
            errors.append("digest.stats.model_reviewed exceeds 30")

    inventory_summary = digest.get("inventory_summary")
    if not isinstance(inventory_summary, dict):
        errors.append("digest.inventory_summary must be an object")
    else:
        errors.extend(
            require_fields(
                inventory_summary,
                ("inventory_count", "report_record_count", "model_candidate_limit", "model_visible_bytes", "review_page_count"),
                "digest.inventory_summary",
            )
        )
        if inventory_summary.get("model_candidate_limit") != DEFAULT_REVIEW_CANDIDATE_LIMIT:
            errors.append("digest.inventory_summary.model_candidate_limit must be 30")
        if not isinstance(inventory_summary.get("review_page_count"), int) or not 0 <= inventory_summary.get("review_page_count", -1) <= MAX_REVIEW_PAGES:
            errors.append("digest.inventory_summary.review_page_count must be 0..2")
        if not isinstance(inventory_summary.get("model_visible_bytes"), int) or not 0 <= inventory_summary.get("model_visible_bytes", -1) <= DEFAULT_REVIEW_PAGE_MAX_BYTES * MAX_REVIEW_PAGES:
            errors.append("digest.inventory_summary.model_visible_bytes exceeds 60000")
        if (
            not isinstance(inventory_summary.get("report_record_count"), int)
            or inventory_summary.get("report_record_count", -1)
            < inventory_summary.get("inventory_count", 0)
        ):
            errors.append(
                "digest.inventory_summary.report_record_count must cover the candidate inventory"
            )

    coverage = digest.get("retrieval_coverage")
    coverage_announcement_dates: set[str] = set()
    if not isinstance(coverage, list) or len(coverage) != len(TRACKED_CATEGORIES):
        errors.append(_report_category_text('digest.retrieval_coverage must contain seven categories'))
    else:
        categories = []
        for index, entry in enumerate(coverage):
            label = f"digest.retrieval_coverage[{index}]"
            if not isinstance(entry, dict):
                errors.append(f"{label} must be an object")
                continue
            category = entry.get("category")
            categories.append(category)
            if category not in TRACKED_CATEGORIES or entry.get("complete") is not True:
                errors.append(f"{label} must be a complete tracked category")
            batches = entry.get("batches")
            if not isinstance(batches, list) or len(batches) != 1 or any(
                not isinstance(batch, dict)
                or batch.get("complete") is not True
                or batch.get("inventory_validated") is not True
                or batch.get("source") != "arxiv_announcement"
                for batch in batches
            ):
                errors.append(
                    f"{label}.batches must contain exactly one validated announcement"
                )
            if isinstance(batches, list):
                coverage_announcement_dates.update(
                    str(batch.get("announcement_date"))
                    for batch in batches
                    if isinstance(batch, dict)
                    and isinstance(batch.get("announcement_date"), str)
                )
        if set(categories) != set(TRACKED_CATEGORIES):
            errors.append("digest.retrieval_coverage categories are incomplete")
        if (
            not isinstance(digest_date, str)
            or coverage_announcement_dates != {digest_date}
        ):
            errors.append(
                "digest.retrieval_coverage must contain exactly one announcement "
                "date matching digest.date"
            )

    exclusions = digest.get("exclusion_stats")
    if not isinstance(exclusions, dict):
        errors.append("digest.exclusion_stats must be an object")
    else:
        expected = exclusions.get("configured_primary_exclusion", 0) + exclusions.get(
            "configured_secondary_exclusion", 0
        )
        if exclusions.get("total_hidden") != expected:
            errors.append("digest.exclusion_stats.total_hidden must equal reason counts")
    remainder = digest.get("cs_cv_report")
    if not isinstance(remainder, dict):
        errors.append("digest.cs_cv_report must be an object")
    else:
        papers = remainder.get("papers")
        if not isinstance(papers, list):
            errors.append("digest.cs_cv_report.papers must be an array")
        else:
            if remainder.get("total") != len(papers):
                errors.append("digest.cs_cv_report.total must equal papers length")
            if isinstance(stats, dict) and stats.get("cv_remainder") != remainder.get("total"):
                errors.append("digest.stats.cv_remainder must equal cs_cv_report.total")
            remainder_ids: set[str] = set()
            for index, paper in enumerate(papers):
                label = f"digest.cs_cv_report.papers[{index}]"
                if not isinstance(paper, dict):
                    errors.append(f"{label} must be an object")
                    continue
                errors.extend(require_fields(paper, CS_CV_REPORT_FIELDS, label))
                errors.extend(validate_announcement_identity(paper, label))
                if paper.get("announcement_date") != digest_date:
                    errors.append(f"{label}.announcement_date must equal digest.date")
                arxiv_id = str(paper.get("arxiv_id", ""))
                if arxiv_id in selected_ids or arxiv_id in remainder_ids:
                    errors.append(f"paper {arxiv_id} is duplicated across digest sections")
                remainder_ids.add(arxiv_id)
                score = paper.get("relevance_score")
                if type(score) is not int or not 0 <= score <= 100:
                    errors.append(f"{label}.relevance_score must be 0..100")
    local_reports = digest.get("local_reports")
    if not isinstance(local_reports, dict) or not all(
        isinstance(local_reports.get(field), str) and local_reports[field].strip()
        for field in ("inventory_json", "inventory_markdown")
    ):
        errors.append("digest.local_reports must contain inventory paths")
    if not errors:
        report = digest["cs_cv_report"]
        for paper in [*digest["focus_papers"], *digest["watch_papers"], *report["papers"]]:
            sources = paper.get("query_sources")
            if (not isinstance(sources, list) or not sources
                    or any(not isinstance(value, str) or value not in TRACKED_CATEGORIES for value in sources)
                    or len(sources) != len(set(sources))):
                errors.append("Every delivered paper must retain nonempty unique query_sources from the configured categories")
        errors.extend(cv_delivery_coverage_errors(digest))
    if errors:
        raise DigestValidationError("\n".join(errors))


def validate_digest(digest: dict[str, Any]) -> None:
    if digest.get("schema_version") == SCHEMA_VERSION:
        validate_digest_v4(digest)
        return
    errors = require_fields(digest, TOP_LEVEL_FIELDS, "digest")
    errors.extend(validate_chinese_prose(digest.get("overview"), "digest.overview"))
    for collection_name in ("trends", "actionable_insights"):
        values = digest.get(collection_name)
        if isinstance(values, list):
            for index, value in enumerate(values):
                errors.extend(
                    validate_chinese_prose(
                        value,
                        f"digest.{collection_name}[{index}]",
                    )
                )
    window = digest.get("retrieval_window")
    if not isinstance(window, dict):
        errors.append("digest.retrieval_window must be an object")
    else:
        errors.extend(require_fields(window, ("from", "to"), "digest.retrieval_window"))
    stats = digest.get("stats")
    if not isinstance(stats, dict):
        errors.append("digest.stats must be an object")
    else:
        errors.extend(require_fields(stats, STATS_FIELDS, "digest.stats"))
        for field in STATS_FIELDS:
            value = stats.get(field)
            if field in stats and (not isinstance(value, int) or value < 0):
                errors.append(f"digest.stats.{field} must be a non-negative integer")

    for collection_name in ("focus_papers", "watch_papers"):
        papers = digest.get(collection_name)
        if not isinstance(papers, list):
            errors.append(f"digest.{collection_name} must be an array")
            continue
        if len(papers) > 10:
            errors.append(f"digest.{collection_name} may contain at most 10 papers")
        for index, paper in enumerate(papers):
            label = f"digest.{collection_name}[{index}]"
            if not isinstance(paper, dict):
                errors.append(f"{label} must be an object")
                continue
            errors.extend(require_fields(paper, PAPER_FIELDS, label))
            errors.extend(validate_announcement_identity(paper, label))
            for field in PAPER_CHINESE_PROSE_FIELDS:
                errors.extend(
                    validate_chinese_prose(paper.get(field), f"{label}.{field}")
                )
            score = paper.get("relevance_score")
            if "relevance_score" in paper and (
                not isinstance(score, int) or not 0 <= score <= 100
            ):
                errors.append(f"{label}.relevance_score must be an integer from 0 to 100")
            if paper.get("evidence_level") not in {"abstract", "full_text"}:
                errors.append(f"{label}.evidence_level must be abstract or full_text")
            if paper.get("topic_group") not in TOPIC_GROUPS:
                errors.append(f"{label}.topic_group must be a configured topic group")
            try:
                base_id, parsed_version = normalize_arxiv_id(
                    str(paper.get("arxiv_id", "")),
                    str(paper.get("pdf_url", "")),
                )
                if paper.get("arxiv_id") != base_id:
                    errors.append(f"{label}.arxiv_id must be unversioned")
                if paper.get("version") is not None and paper.get("version") != parsed_version:
                    errors.append(f"{label}.version must match the PDF URL version")
            except DigestValidationError as exc:
                errors.append(f"{label}: {exc}")

    coverage = digest.get("retrieval_coverage")
    if not isinstance(coverage, list):
        errors.append("digest.retrieval_coverage must be an array")
    else:
        coverage_categories: list[str] = []
        for index, entry in enumerate(coverage):
            label = f"digest.retrieval_coverage[{index}]"
            if not isinstance(entry, dict):
                errors.append(f"{label} must be an object")
                continue
            errors.extend(
                require_fields(
                    entry,
                    ("category", "complete", "raw_count", "unique_count"),
                    label,
                )
            )
            category = entry.get("category")
            if category in coverage_categories:
                errors.append(f"{label}.category is duplicated")
            coverage_categories.append(category)
            if category not in TRACKED_CATEGORIES:
                errors.append(f"{label}.category is not tracked")
            if entry.get("complete") is not True:
                errors.append(f"{label}.complete must be true before rendering")
            for field in ("raw_count", "unique_count"):
                count = entry.get(field)
                if field in entry and (not isinstance(count, int) or count < 0):
                    errors.append(f"{label}.{field} must be a non-negative integer")
            batches = entry.get("batches")
            if batches is not None:
                if not isinstance(batches, list) or not batches:
                    errors.append(f"{label}.batches must be a non-empty array")
                    continue
                batch_returned = 0
                for batch_index, batch in enumerate(batches):
                    batch_label = f"{label}.batches[{batch_index}]"
                    if not isinstance(batch, dict):
                        errors.append(f"{batch_label} must be an object")
                        continue
                    errors.extend(
                        require_fields(
                            batch,
                            (
                                "announcement_date",
                                "listing_url",
                                "source",
                                "counts",
                                "returned",
                                "complete",
                                "inventory_validated",
                            ),
                            batch_label,
                        )
                    )
                    announcement_date = batch.get("announcement_date")
                    if not isinstance(announcement_date, str) or not re.fullmatch(
                        r"\d{4}-\d{2}-\d{2}",
                        announcement_date,
                    ):
                        errors.append(
                            f"{batch_label}.announcement_date must use YYYY-MM-DD"
                        )
                    listing_url = batch.get("listing_url")
                    if not isinstance(listing_url, str) or not listing_url.startswith(
                        f"https://arxiv.org/list/{category}/"
                    ):
                        errors.append(
                            f"{batch_label}.listing_url must be the category's arXiv list URL"
                        )
                    if batch.get("source") != "arxiv_announcement":
                        errors.append(
                            f"{batch_label}.source must be arxiv_announcement"
                        )
                    counts = batch.get("counts")
                    if not isinstance(counts, dict):
                        errors.append(f"{batch_label}.counts must be an object")
                    else:
                        errors.extend(
                            require_fields(
                                counts,
                                (
                                    "new_submissions",
                                    "cross_lists",
                                    "replacements",
                                    "total",
                                ),
                                f"{batch_label}.counts",
                            )
                        )
                        count_values = [
                            counts.get("new_submissions"),
                            counts.get("cross_lists"),
                            counts.get("replacements"),
                        ]
                        if any(
                            not isinstance(value, int) or value < 0
                            for value in count_values
                        ):
                            errors.append(
                                f"{batch_label}.counts values must be non-negative integers"
                            )
                        elif counts.get("total") != sum(count_values):
                            errors.append(
                                f"{batch_label}.counts.total must equal its three sections"
                            )
                    returned = batch.get("returned")
                    if not isinstance(returned, int) or not 0 <= returned <= 2000:
                        errors.append(
                            f"{batch_label}.returned must be an integer from 0 to 2000"
                        )
                    else:
                        batch_returned += returned
                        if isinstance(counts, dict) and counts.get("total") != returned:
                            errors.append(
                                f"{batch_label}.returned must equal counts.total"
                            )
                    if batch.get("complete") is not True:
                        errors.append(f"{batch_label}.complete must be true")
                    if batch.get("inventory_validated") is not True:
                        errors.append(
                            f"{batch_label}.inventory_validated must be true"
                        )
                if (
                    isinstance(entry.get("raw_count"), int)
                    and entry.get("raw_count") != batch_returned
                ):
                    errors.append(
                        f"{label}.raw_count must equal its announcement batch totals"
                    )
                continue
            shards = entry.get("shards")
            if not isinstance(shards, list):
                errors.append(f"{label} must contain batches or legacy shards")
                continue
            for shard_index, shard in enumerate(shards):
                shard_label = f"{label}.shards[{shard_index}]"
                if not isinstance(shard, dict):
                    errors.append(f"{shard_label} must be an object")
                    continue
                errors.extend(
                    require_fields(
                        shard,
                        (
                            "from",
                            "to",
                            "query",
                            "date_from",
                            "date_to",
                            "search_args",
                            "returned",
                            "complete",
                            "bounds_validated",
                        ),
                        shard_label,
                    )
                )
                returned = shard.get("returned")
                if not isinstance(returned, int) or not 0 <= returned < 50:
                    errors.append(f"{shard_label}.returned must be an integer below 50")
                if shard.get("complete") is not True:
                    errors.append(f"{shard_label}.complete must be true")
                if shard.get("bounds_validated") is not True:
                    errors.append(f"{shard_label}.bounds_validated must be true")
                source = shard.get("source", "arxiv_mcp")
                if source not in ARXIV_RETRIEVAL_SOURCES:
                    errors.append(
                        f"{shard_label}.source must be one of "
                        + ", ".join(ARXIV_RETRIEVAL_SOURCES)
                    )
                try:
                    validate_shard_search_args(shard)
                except DigestValidationError as exc:
                    errors.append(f"{shard_label}: {exc}")
        if set(coverage_categories) != set(TRACKED_CATEGORIES):
            errors.append(_report_category_text('digest.retrieval_coverage must contain all seven tracked categories'))

    exclusion_stats = digest.get("exclusion_stats")
    if not isinstance(exclusion_stats, dict):
        errors.append("digest.exclusion_stats must be an object")
    else:
        errors.extend(
            require_fields(
                exclusion_stats,
                (
                    "configured_primary_exclusion",
                    "configured_secondary_exclusion",
                    "cs_cv_total_hidden",
                    "total_hidden",
                ),
                "digest.exclusion_stats",
            )
        )
        for field in (
            "configured_primary_exclusion",
            "configured_secondary_exclusion",
            "cs_cv_total_hidden",
            "total_hidden",
        ):
            count = exclusion_stats.get(field)
            if field in exclusion_stats and (not isinstance(count, int) or count < 0):
                errors.append(f"digest.exclusion_stats.{field} must be non-negative")
        if (
            isinstance(exclusion_stats.get("configured_primary_exclusion"), int)
            and isinstance(exclusion_stats.get("configured_secondary_exclusion"), int)
            and exclusion_stats.get("total_hidden")
            != exclusion_stats["configured_primary_exclusion"]
            + exclusion_stats["configured_secondary_exclusion"]
        ):
            errors.append("digest.exclusion_stats.total_hidden must equal reason counts")
        cs_cv_total_hidden = exclusion_stats.get("cs_cv_total_hidden")
        if cs_cv_total_hidden is not None and (
            not isinstance(cs_cv_total_hidden, int)
            or cs_cv_total_hidden < 0
            or cs_cv_total_hidden > exclusion_stats.get("total_hidden", 0)
        ):
            errors.append(
                "digest.exclusion_stats.cs_cv_total_hidden must be between zero and "
                "total_hidden"
            )

    remainder = digest.get("cv_daily_remainder")
    if not isinstance(remainder, dict):
        errors.append("digest.cv_daily_remainder must be an object")
    else:
        errors.extend(
            require_fields(
                remainder,
                ("total", "detailed", "compact"),
                "digest.cv_daily_remainder",
            )
        )
        detailed = remainder.get("detailed")
        compact = remainder.get("compact")
        if not isinstance(detailed, list):
            errors.append("digest.cv_daily_remainder.detailed must be an array")
            detailed = []
        if not isinstance(compact, list):
            errors.append("digest.cv_daily_remainder.compact must be an array")
            compact = []
        if len(detailed) > 50:
            errors.append("digest.cv_daily_remainder.detailed may contain at most 50 papers")
        for collection_name, papers, required_fields in (
            ("detailed", detailed, CV_DETAILED_FIELDS),
            ("compact", compact, CV_COMPACT_FIELDS),
        ):
            for index, paper in enumerate(papers):
                label = f"digest.cv_daily_remainder.{collection_name}[{index}]"
                if not isinstance(paper, dict):
                    errors.append(f"{label} must be an object")
                    continue
                errors.extend(require_fields(paper, required_fields, label))
                errors.extend(validate_announcement_identity(paper, label))
                prose_fields = (
                    CV_DETAILED_CHINESE_PROSE_FIELDS
                    if collection_name == "detailed"
                    else CV_COMPACT_CHINESE_PROSE_FIELDS
                )
                for field in prose_fields:
                    errors.extend(
                        validate_chinese_prose(paper.get(field), f"{label}.{field}")
                    )
                score = paper.get("relevance_score")
                if "relevance_score" in paper and (
                    not isinstance(score, int) or not 0 <= score <= 100
                ):
                    errors.append(f"{label}.relevance_score must be 0..100")
                if collection_name == "detailed" and REPORT_CATEGORY not in paper.get(
                    "categories", []
                ):
                    errors.append((f'{label}' + _report_category_text('.categories must include cs.CV')))
                try:
                    base_id, parsed_version = normalize_arxiv_id(
                        str(paper.get("arxiv_id", "")),
                        str(paper.get("pdf_url", "")),
                    )
                    if paper.get("arxiv_id") != base_id:
                        errors.append(f"{label}.arxiv_id must be unversioned")
                    if paper.get("version") is not None and paper.get("version") != parsed_version:
                        errors.append(f"{label}.version must match the PDF URL version")
                except DigestValidationError as exc:
                    errors.append(f"{label}: {exc}")
        total = remainder.get("total")
        if total != len(detailed) + len(compact):
            errors.append("digest.cv_daily_remainder.total must equal detailed + compact")
        if detailed and compact:
            minimum_detailed = min(
                int(paper.get("relevance_score", 0)) for paper in detailed
            )
            maximum_compact = max(
                int(paper.get("relevance_score", 0)) for paper in compact
            )
            if minimum_detailed < maximum_compact:
                errors.append("detailed remainder must contain the 50 highest scores")

    errors.extend(cv_delivery_coverage_errors(digest))

    if isinstance(stats, dict):
        focus = digest.get("focus_papers")
        watch = digest.get("watch_papers")
        if isinstance(focus, list) and stats.get("focus") != len(focus):
            errors.append("digest.stats.focus must equal focus_papers length")
        if isinstance(watch, list) and stats.get("watch") != len(watch):
            errors.append("digest.stats.watch must equal watch_papers length")
        if isinstance(remainder, dict) and stats.get("cv_remainder") != remainder.get("total"):
            errors.append("digest.stats.cv_remainder must equal cv_daily_remainder.total")
        if (
            isinstance(exclusion_stats, dict)
            and stats.get("excluded_hidden") != exclusion_stats.get("total_hidden")
        ):
            errors.append("digest.stats.excluded_hidden must equal exclusion total")
    if errors:
        raise DigestValidationError("\n".join(errors))


def emphasized(value: Any) -> str:
    escaped = html.escape(str(value), quote=True)
    return THEME_RE.sub(r"<strong>\1</strong>", escaped)


def safe_url(value: Any) -> str:
    text = str(value)
    parsed = urlparse(text)
    if parsed.scheme != "https" or parsed.netloc not in {"arxiv.org", "www.arxiv.org"}:
        return "#"
    return html.escape(text, quote=True)


def html_list(values: Any) -> str:
    items = values if isinstance(values, list) else [values]
    return "".join(f"<li>{emphasized(item)}</li>" for item in items)


def coverage_records(entry: dict[str, Any]) -> list[dict[str, Any]]:
    batches = entry.get("batches")
    if isinstance(batches, list):
        return [record for record in batches if isinstance(record, dict)]
    shards = entry.get("shards")
    if isinstance(shards, list):
        return [record for record in shards if isinstance(record, dict)]
    return []


def coverage_sources(entry: dict[str, Any]) -> list[str]:
    return sorted(
        {
            str(record.get("source", "arxiv_mcp"))
            for record in coverage_records(entry)
        }
    )


def versioned_arxiv_label(paper: dict[str, Any]) -> str:
    version = paper.get("version")
    suffix = f"v{version}" if isinstance(version, int) else ""
    return f"{paper.get('arxiv_id', '')}{suffix}"


V3_FOCUS_CARD_FIELDS = (
    ("一句话核心结论", "core_conclusion"),
    ("主要研究问题", "research_problem"),
    ("方法概述", "method_overview"),
    ("主要贡献", "contributions"),
    ("与当前研究的具体关系", "research_relation"),
    ("可迁移内容", "transferable_ideas"),
    ("局限或验证点", "limitations"),
    ("是否值得精读", "worth_reading"),
    ("建议 follow", "follow_up"),
)
V3_WATCH_CARD_FIELDS = V3_FOCUS_CARD_FIELDS


def render_paper_html(paper: dict[str, Any], index: int) -> str:
    authors = ", ".join(str(author) for author in paper["authors"])
    categories = ", ".join(str(category) for category in paper["categories"])
    fields = (
        ("一句话核心结论", "core_conclusion"),
        ("主要研究问题", "research_problem"),
        ("方法概述", "method_overview"),
        ("主要贡献", "contributions"),
        ("与当前研究的具体关系", "research_relation"),
        ("可迁移内容", "transferable_ideas"),
        ("局限或验证点", "limitations"),
        ("是否值得精读", "worth_reading"),
        ("建议 follow", "follow_up"),
    )
    details = "".join(
        (
            "<div style=\"margin:8px 0\"><span style=\"font-weight:600;color:#334155\">"
            f"{label}：</span>{emphasized(paper[key])}</div>"
        )
        for label, key in fields
    )
    return f"""
<section style="border:1px solid #dbe4ee;border-radius:12px;padding:18px;margin:16px 0;background:#ffffff">
  <h3 style="margin:0 0 8px;color:#0f172a">{index}. {emphasized(paper['title'])}</h3>
  <div style="color:#475569;font-size:13px;line-height:1.6">
    {emphasized(authors)} · {emphasized(versioned_arxiv_label(paper))}
    · {emphasized(categories)} · {emphasized(paper['submitted_or_updated'])}
  </div>
  <div style="margin:10px 0">
    <span style="display:inline-block;background:#dbeafe;color:#1d4ed8;border-radius:999px;padding:4px 9px;margin-right:6px">
      相关性 {emphasized(paper['relevance_score'])}/100
    </span>
    <span style="display:inline-block;background:#ecfdf5;color:#047857;border-radius:999px;padding:4px 9px">
      {emphasized(paper['recommendation'])}
    </span>
    <span style="display:inline-block;background:#f8fafc;color:#475569;border-radius:999px;padding:4px 9px;margin-left:6px">
      证据：{emphasized(paper['evidence_level'])}
    </span>
  </div>
  <div style="margin:8px 0">
    <a href="{safe_url(paper['arxiv_url'])}" style="color:#2563eb">arXiv 页面</a>
    &nbsp;·&nbsp;
    <a href="{safe_url(paper['pdf_url'])}" style="color:#2563eb">PDF</a>
  </div>
  {details}
</section>
"""


def render_cv_detailed_html(paper: dict[str, Any], index: int) -> str:
    authors = ", ".join(str(author) for author in paper["authors"])
    fields = (
        ("一句话核心结论", "core_conclusion"),
        ("主要研究问题", "research_problem"),
        ("方法概述", "method_overview"),
        ("主要贡献", "contributions"),
    )
    details = "".join(
        (
            "<div style=\"margin:7px 0\"><span style=\"font-weight:600;color:#334155\">"
            f"{label}：</span>{emphasized(paper[key])}</div>"
        )
        for label, key in fields
    )
    return f"""
<section style="border:1px solid #e2e8f0;border-radius:10px;padding:15px;margin:12px 0;background:#ffffff">
  <h3 style="margin:0 0 6px;color:#0f172a">{index}. {emphasized(paper['title'])}</h3>
  <div style="color:#64748b;font-size:13px;line-height:1.6">
    {emphasized(authors)} · {emphasized(versioned_arxiv_label(paper))}
    · {emphasized(paper['submitted_or_updated'])} · 相关性 {emphasized(paper['relevance_score'])}/100
  </div>
  <div style="margin:7px 0"><a href="{safe_url(paper['arxiv_url'])}" style="color:#2563eb">arXiv 页面</a>
    &nbsp;·&nbsp;<a href="{safe_url(paper['pdf_url'])}" style="color:#2563eb">PDF</a></div>
  {details}
</section>
"""


def render_cv_compact_html(paper: dict[str, Any], index: int) -> str:
    return f"""
<section style="border-bottom:1px solid #e2e8f0;padding:10px 0">
  <div style="font-weight:600;color:#0f172a">{index}. <a href="{safe_url(paper['arxiv_url'])}" style="color:#2563eb">{emphasized(paper['title'])}</a></div>
  <div style="color:#64748b;font-size:13px">{emphasized(versioned_arxiv_label(paper))}
    · {emphasized(paper['submitted_or_updated'])} · 相关性 {emphasized(paper['relevance_score'])}/100</div>
  <div style="margin-top:5px">{emphasized(paper['core_conclusion'])}</div>
</section>
"""


def grouped_focus_html(papers: list[dict[str, Any]]) -> str:
    sections: list[str] = []
    global_index = 1
    for group in TOPIC_GROUPS:
        grouped = [paper for paper in papers if paper.get("topic_group") == group]
        if not grouped:
            continue
        cards = "".join(
            render_paper_html(paper, index)
            for index, paper in enumerate(grouped, global_index)
        )
        sections.append(
            f"<h3 style=\"margin:24px 0 8px;color:#1e3a8a\">{emphasized(TOPIC_LABELS[group])}</h3>{cards}"
        )
        global_index += len(grouped)
    return "".join(sections)


def render_v3_paper_html(
    paper: dict[str, Any],
    index: int,
    *,
    kind: str,
) -> str:
    fields = V3_FOCUS_CARD_FIELDS if kind == "focus" else V3_WATCH_CARD_FIELDS
    authors = ", ".join(str(author) for author in paper["authors"])
    categories = ", ".join(str(category) for category in paper["categories"])
    details = "".join(
        f"<div class=\"detail\"><strong>{label}：</strong>{emphasized(paper[key])}</div>"
        for label, key in fields
    )
    return (
        f'<section class="paper {kind}" data-id="{emphasized(paper["arxiv_id"])}">'
        f'<h3>{index}. {emphasized(paper["title"])}</h3>'
        f'<div class="meta">{emphasized(authors)} · {emphasized(versioned_arxiv_label(paper))}'
        f' · {emphasized(categories)} · {emphasized(paper["submitted_or_updated"])}</div>'
        f'<div class="badges"><b>相关性 {emphasized(paper["relevance_score"])}/100</b>'
        f'<span>{emphasized(paper["recommendation"])}</span>'
        f'<span>{emphasized(TOPIC_LABELS[paper["topic_group"]])}</span>'
        f'<span>证据：abstract</span></div>'
        f'<div class="links"><a href="{safe_url(paper["arxiv_url"])}">arXiv 页面</a> · '
        f'<a href="{safe_url(paper["pdf_url"])}">PDF</a></div>{details}</section>'
    )


def grouped_focus_html_v3(papers: list[dict[str, Any]]) -> str:
    sections: list[str] = []
    global_index = 1
    for group in TOPIC_GROUPS:
        grouped = [paper for paper in papers if paper.get("topic_group") == group]
        if not grouped:
            continue
        cards = "".join(
            render_v3_paper_html(paper, index, kind="focus")
            for index, paper in enumerate(grouped, global_index)
        )
        sections.append(f'<h3 class="group">{emphasized(TOPIC_LABELS[group])}</h3>{cards}')
        global_index += len(grouped)
    return "".join(sections)


V3_EMAIL_STYLE = """body{margin:0;background:#f1f5f9;font-family:Arial,sans-serif;color:#1e293b}main{max-width:820px;margin:auto;padding:22px}header{background:#0f172a;color:#fff;border-radius:14px;padding:21px}header h1{margin:0 0 8px}.range{color:#cbd5e1}.panel,.paper{background:#fff;border-radius:12px;padding:16px;margin:14px 0}.paper{border:1px solid #dbe4ee}.paper h3{margin:0 0 7px;color:#0f172a}.meta,.muted,footer{color:#64748b;font-size:13px}.badges{margin:9px 0}.badges b,.badges span{display:inline-block;border-radius:999px;padding:3px 8px;margin:0 5px 3px 0;background:#eaf2ff}.badges span{background:#ecfdf5}.links{margin:7px 0}a{color:#2563eb}.detail{margin:7px 0;line-height:1.55}.detail strong{color:#334155}.group{color:#1e3a8a;margin:22px 0 7px}.part{font-weight:600;color:#93c5fd}footer{line-height:1.7}"""


def _v3_card_units(digest: dict[str, Any]) -> list[dict[str, Any]]:
    units: list[dict[str, Any]] = []
    focus_index = 1
    for group in TOPIC_GROUPS:
        grouped = [
            paper
            for paper in digest["focus_papers"]
            if paper.get("topic_group") == group
        ]
        for local_index, paper in enumerate(grouped):
            prefix = (
                f'<h3 class="group">{emphasized(TOPIC_LABELS[group])}</h3>'
                if local_index == 0
                else ""
            )
            units.append(
                {
                    "kind": "focus",
                    "arxiv_id": str(paper["arxiv_id"]),
                    "html": prefix
                    + render_v3_paper_html(paper, focus_index, kind="focus"),
                }
            )
            focus_index += 1
    for index, paper in enumerate(digest["watch_papers"], 1):
        units.append(
            {
                "kind": "watch",
                "arxiv_id": str(paper["arxiv_id"]),
                "html": render_v3_paper_html(paper, index, kind="watch"),
            }
        )
    return units


def _bounded_text_chunks(value: Any, chunk_chars: int = 1_500) -> list[str]:
    """Split unusually long prose without dropping or rewriting any characters."""

    text = str(value)
    return [text[index : index + chunk_chars] for index in range(0, len(text), chunk_chars)] or [""]


def _v3_transport_units(digest: dict[str, Any]) -> list[dict[str, Any]]:
    """Build independently packable HTML blocks for lossless Gmail sharding."""

    stats = digest["stats"]
    units: list[dict[str, Any]] = []
    overview_chunks = _bounded_text_chunks(digest["overview"])
    for index, chunk in enumerate(overview_chunks):
        heading = "每日总览" if index == 0 else "每日总览（续）"
        stats_html = (
            f'<p class="muted">检索 {stats["retrieved"]} · 去重 {stats["unique"]} · '
            f'本地预筛 {stats["candidates"]} · 模型复核 {stats["model_reviewed"]} · '
            f'重点 {stats["focus"]} · 潜在 {stats["watch"]}</p>'
            if index == 0
            else ""
        )
        units.append(
            {
                "kind": "narrative",
                "arxiv_id": None,
                "html": f'<section class="panel"><h2>{heading}</h2><p>{emphasized(chunk)}</p>{stats_html}</section>',
            }
        )
    reading = [
        chunk
        for value in digest["reading_order"]
        for chunk in _bounded_text_chunks(value)
    ]
    for index in range(0, len(reading), 5):
        heading = "今日优先阅读顺序" if index == 0 else "今日优先阅读顺序（续）"
        units.append(
            {
                "kind": "narrative",
                "arxiv_id": None,
                "html": f'<section class="panel"><h2>{heading}</h2><ol start="{index + 1}">{html_list(reading[index:index + 5])}</ol></section>',
            }
        )
    paper_units = _v3_card_units(digest)
    first_focus = True
    first_watch = True
    for unit in paper_units:
        prefix = ""
        if unit["kind"] == "focus" and first_focus:
            prefix = "<h2>重点推荐论文</h2>"
            first_focus = False
        elif unit["kind"] == "watch" and first_watch:
            prefix = "<h2>潜在关注论文</h2>"
            first_watch = False
        units.append({**unit, "html": prefix + str(unit["html"])})
    if not paper_units:
        units.append(
            {
                "kind": "narrative",
                "arxiv_id": None,
                "html": '<section class="panel muted">本次更新没有达到邮件展示阈值的论文。</section>',
            }
        )
    for heading, field in (
        ("今日研究趋势", "trends"),
        ("对当前研究的可执行启发", "actionable_insights"),
    ):
        values = [
            chunk
            for value in digest[field]
            for chunk in _bounded_text_chunks(value)
        ]
        for index in range(0, len(values), 3):
            suffix = "" if index == 0 else "（续）"
            units.append(
                {
                    "kind": "narrative",
                    "arxiv_id": None,
                    "html": f'<section class="panel"><h2>{heading}{suffix}</h2><ul>{html_list(values[index:index + 3])}</ul></section>',
                }
            )
    units.append(
        {
            "kind": "narrative",
            "arxiv_id": None,
            "html": f'<footer>完整 {digest["inventory_summary"]["inventory_count"]} 篇分类结果已保存到本地。入选论文均保留九项完整卡片；证据等级为 abstract，无附件。</footer>',
        }
    )
    return units


def _render_v3_transport_document(
    digest: dict[str, Any],
    units: list[dict[str, Any]],
    *,
    part_index: int,
    part_count: int,
) -> str:
    window = digest["retrieval_window"]
    ids = ",".join(
        str(unit["arxiv_id"]) for unit in units if unit.get("arxiv_id") is not None
    )
    part_label = (
        f'<div class="part">第 {part_index}/{part_count} 部分</div>'
        if part_count > 1
        else ""
    )
    body = "".join(str(unit["html"]) for unit in units)
    return f"""<!doctype html>
<html lang="zh-CN">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><meta name="daily-arxiv-delivery-format" content="html-sequence-v3"><meta name="daily-arxiv-part" content="{part_index}/{part_count}"><meta name="daily-arxiv-ids" content="{emphasized(ids)}"><style>{V3_EMAIL_STYLE}</style></head>
<body><main><header><h1>arXiv Daily · {emphasized(digest['date'])}</h1>{part_label}<div class="range">检索范围：{emphasized(window['from'])} — {emphasized(window['to'])}</div></header>
{body}</main></body></html>
"""


def _render_v3_html_document(
    digest: dict[str, Any],
    units: list[dict[str, Any]],
    *,
    part_index: int,
    part_count: int,
    include_front: bool,
    include_back: bool,
) -> str:
    focus = "".join(unit["html"] for unit in units if unit["kind"] == "focus")
    watch = "".join(unit["html"] for unit in units if unit["kind"] == "watch")
    if not focus:
        focus = ""
    if not watch:
        watch = ""
    stats = digest["stats"]
    window = digest["retrieval_window"]
    part_label = (
        f'<div class="part">第 {part_index}/{part_count} 部分</div>'
        if part_count > 1
        else ""
    )
    front = ""
    if include_front:
        front = f"""<section class="panel"><h2>每日总览</h2><p>{emphasized(digest['overview'])}</p>
<p class="muted">检索 {stats['retrieved']} · 去重 {stats['unique']} · 本地预筛 {stats['candidates']} · 模型复核 {stats['model_reviewed']} · 重点 {stats['focus']} · 潜在 {stats['watch']}</p></section>
<section class="panel"><h2>今日优先阅读顺序</h2><ol>{html_list(digest['reading_order'])}</ol></section>"""
    papers = ""
    if focus:
        papers += f"<h2>重点推荐论文</h2>{focus}"
    if watch:
        papers += f"<h2>潜在关注论文</h2>{watch}"
    if not papers:
        papers = '<section class="panel muted">本次更新没有达到邮件展示阈值的论文。</section>'
    back = ""
    if include_back:
        back = f"""<section class="panel"><h2>今日研究趋势</h2><ul>{html_list(digest['trends'])}</ul></section>
<section class="panel"><h2>对当前研究的可执行启发</h2><ul>{html_list(digest['actionable_insights'])}</ul></section>
<footer>完整 {digest['inventory_summary']['inventory_count']} 篇分类结果已保存到本地。入选论文均保留九项完整卡片；证据等级为 abstract，无附件。</footer>"""
    ids = ",".join(str(unit["arxiv_id"]) for unit in units)
    return f"""<!doctype html>
<html lang="zh-CN">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><meta name="daily-arxiv-delivery-format" content="html-sequence-v3"><meta name="daily-arxiv-part" content="{part_index}/{part_count}"><meta name="daily-arxiv-ids" content="{emphasized(ids)}"><style>{V3_EMAIL_STYLE}</style></head>
<body><main><header><h1>arXiv Daily · {emphasized(digest['date'])}</h1>{part_label}<div class="range">检索范围：{emphasized(window['from'])} — {emphasized(window['to'])}</div></header>
{front}{papers}{back}</main></body></html>
"""


def render_html_v3(digest: dict[str, Any]) -> str:
    """Render the complete logical digest before transport sharding."""

    return _render_v3_html_document(
        digest,
        _v3_card_units(digest),
        part_index=1,
        part_count=1,
        include_front=True,
        include_back=True,
    )


def render_html_parts_v3(
    digest: dict[str, Any],
    *,
    max_chars: int,
) -> list[dict[str, Any]]:
    """Partition a validated v3 digest into complete, bounded Gmail bodies."""

    if max_chars < 1:
        raise DigestValidationError("Gmail part character limit must be positive")
    units = _v3_transport_units(digest)

    partitions: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    worst_case_total = len(units)
    for unit in units:
        candidate = [*current, unit]
        preview = _render_v3_transport_document(
            digest,
            candidate,
            part_index=len(partitions) + 1,
            part_count=worst_case_total,
        )
        if current and len(preview) > max_chars:
            partitions.append(current)
            current = [unit]
            single = _render_v3_transport_document(
                digest,
                current,
                part_index=len(partitions) + 1,
                part_count=worst_case_total,
            )
            if len(single) > max_chars:
                label = unit.get("arxiv_id") or unit["kind"]
                raise DigestValidationError(
                    f"delivery block {label} cannot fit one Gmail HTML part"
                )
        else:
            current = candidate
    if current:
        partitions.append(current)

    part_count = len(partitions)
    rendered: list[dict[str, Any]] = []
    for index, partition in enumerate(partitions, 1):
        html_text = _render_v3_transport_document(
            digest,
            partition,
            part_index=index,
            part_count=part_count,
        )
        if len(html_text) > max_chars:
            raise DigestValidationError(
                f"Gmail HTML part {index} exceeds {max_chars} characters"
            )
        rendered.append(
            {
                "html": html_text,
                "paper_ids": [
                    str(unit["arxiv_id"])
                    for unit in partition
                    if unit.get("arxiv_id") is not None
                ],
                "focus_ids": [
                    str(unit["arxiv_id"])
                    for unit in partition
                    if unit["kind"] == "focus"
                ],
                "watch_ids": [
                    str(unit["arxiv_id"])
                    for unit in partition
                    if unit["kind"] == "watch"
                ],
            }
        )
    return rendered


def _clip_email_prose(value: Any, limit: int) -> str:
    prose = str(value or "").strip()
    return prose if len(prose) <= limit else prose[: max(1, limit - 1)].rstrip() + "…"


def render_html_v4(digest: dict[str, Any]) -> str:
    selected_fields = (
        ("一句话核心结论", "core_conclusion"),
        ("主要研究问题", "research_problem"),
        ("方法概述", "method_overview"),
        ("主要贡献", "contributions"),
        ("与当前研究的具体关系", "research_relation"),
        ("可迁移内容", "transferable_ideas"),
        ("局限或验证点", "limitations"),
        ("是否值得精读", "worth_reading"),
        ("建议 follow", "follow_up"),
    )
    style = "body{margin:0;background:#f5f7fb;color:#172033;font:14px/1.55 Arial,'Microsoft YaHei',sans-serif}main{max-width:920px;margin:auto;padding:18px}header,.panel,.paper{background:#fff;border:1px solid #dfe5ef;border-radius:10px;padding:14px;margin:0 0 12px}.paper{border-left:4px solid #4263eb}h1{margin:0 0 5px;font-size:25px}h2{font-size:19px;margin:18px 0 9px}h3{font-size:16px;margin:0 0 5px}.group{color:#1e3a8a;margin:22px 0 7px}p{margin:5px 0}.meta,.muted{color:#667085}.label{font-weight:700;color:#243b64}a{color:#2457c5;text-decoration:none}.stats{word-spacing:8px}footer{color:#667085;padding:10px 2px}"
    for selected_limit in (180, 145, 115, 90):
        blocks = [
            "<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>",
            "<meta name='daily-arxiv-delivery-format' content='html-pdf-single-v4'>",
            f"<style>{style}</style></head><body><main><!--DAILY_ARXIV_BODY_BEGIN-->",
            f"<header><h1>arXiv Daily · {emphasized(digest['date'])}</h1><div class='muted'>单封完整日报 · abstract 证据</div></header>",
            ("<section class='panel'><h2>每日总览</h2><p>" + f"{emphasized(digest['overview'])}" + "</p><p class='stats muted'>检索 " + f"{digest['stats']['retrieved']}" + ' 去重 ' + f"{digest['stats']['unique']}" + ' 模型复核 ' + f"{digest['stats']['model_reviewed']}" + ' 重点 ' + f"{digest['stats']['focus']}" + ' 潜在 ' + f"{digest['stats']['watch']}" + _report_category_text(' cs.CV ') + f"{digest['stats']['cv_remainder']}" + '</p></section>'),
            f"<section class='panel'><h2>今日优先阅读顺序</h2><ol>{html_list(digest['reading_order'])}</ol></section>",
        ]
        for heading, collection, group_by_topic in (
            ("重点推荐论文", digest["focus_papers"], True),
            ("潜在关注论文", digest["watch_papers"], False),
        ):
            blocks.append(f"<h2>{heading}</h2>")
            if not collection:
                blocks.append("<section class='panel muted'>本次没有达到该阈值的论文。</section>")
            grouped_collections = (
                [
                    (
                        group,
                        [paper for paper in collection if paper.get("topic_group") == group],
                    )
                    for group in TOPIC_GROUPS
                ]
                if group_by_topic
                else [(None, collection)]
            )
            paper_index = 1
            for group, grouped_collection in grouped_collections:
                if group is not None and grouped_collection:
                    blocks.append(
                        f"<h3 class='group'>{emphasized(TOPIC_LABELS[group])}</h3>"
                    )
                for paper in grouped_collection:
                    rows = "".join(
                        f"<p><span class='label'>{label}：</span>{emphasized(_clip_email_prose(paper[field], selected_limit))}</p>"
                        for label, field in selected_fields
                    )
                    blocks.append(
                        f"<article class='paper' data-arxiv-id='{emphasized(paper['arxiv_id'])}'><h3>{paper_index}. <a href='{emphasized(paper['arxiv_url'])}'>{emphasized(paper['title'])}</a></h3><p class='meta'>arXiv:{emphasized(paper['arxiv_id'])} · 相关度 {paper['relevance_score']} · {emphasized(TOPIC_LABELS[paper['topic_group']])}</p>{rows}</article>"
                    )
                    paper_index += 1
        blocks.append(f"<section class='panel'><h2>今日研究趋势</h2><ul>{html_list(digest['trends'])}</ul></section>")
        blocks.append(f"<section class='panel'><h2>对当前研究的可执行启发</h2><ul>{html_list(digest['actionable_insights'])}</ul></section>")
        blocks.append(_report_category_text('<footer>七类检索覆盖及筛选统计见 PDF 附件。<!--DAILY_ARXIV_BODY_END--></footer></main></body></html>'))
        rendered = "".join(blocks)
        if len(rendered.encode("utf-8")) <= MAX_EMAIL_HTML_BYTES:
            return rendered
    raise DigestValidationError(
        f"single Gmail HTML body exceeds {MAX_EMAIL_HTML_BYTES} UTF-8 bytes after compact rendering"
    )


def render_html(digest: dict[str, Any]) -> str:
    digest = canonicalize_digest(digest)
    validate_digest(digest)
    if digest.get("schema_version") == SCHEMA_VERSION:
        return render_html_v4(digest)
    focus = grouped_focus_html(digest["focus_papers"])
    watch = "".join(
        render_paper_html(paper, index)
        for index, paper in enumerate(digest["watch_papers"], 1)
    )
    if not focus:
        focus = "<p style=\"color:#64748b\">本次更新没有发现需要重点推荐的论文。</p>"
    if not watch:
        watch = "<p style=\"color:#64748b\">本次更新没有潜在关注论文。</p>"
    remainder = digest["cv_daily_remainder"]
    detailed_remainder = "".join(
        render_cv_detailed_html(paper, index)
        for index, paper in enumerate(remainder["detailed"], 1)
    )
    compact_remainder = "".join(
        render_cv_compact_html(paper, index)
        for index, paper in enumerate(
            remainder["compact"],
            len(remainder["detailed"]) + 1,
        )
    )
    cv_remainder = detailed_remainder + compact_remainder
    if not cv_remainder:
        cv_remainder = _report_category_text('<p style="color:#64748b">本次没有其它符合展示条件的 cs.CV 更新。</p>')
    window = digest["retrieval_window"]
    stats = digest["stats"]
    coverage = " · ".join(
        (
            f"{entry['category']}={entry['unique_count']}"
            f" ({','.join(coverage_sources(entry))})"
        )
        for entry in digest["retrieval_coverage"]
    )
    return ('<!doctype html>\n<html lang="zh-CN">\n<head><meta charset="utf-8"><meta name="viewport" content="width=device-width"></head>\n<body style="margin:0;padding:0;background:#f1f5f9;font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',Arial,sans-serif;color:#1e293b">\n<main style="max-width:820px;margin:0 auto;padding:24px">\n  <header style="background:#0f172a;color:#fff;border-radius:14px;padding:22px">\n    <h1 style="margin:0 0 8px">arXiv Daily · ' + f"{emphasized(digest['date'])}" + '</h1>\n    <div style="color:#cbd5e1">检索范围：' + f"{emphasized(window['from'])}" + ' — ' + f"{emphasized(window['to'])}" + '</div>\n  </header>\n  <section style="background:#fff;border-radius:12px;padding:18px;margin:16px 0">\n    <h2 style="margin-top:0">每日总览</h2>\n    <p style="line-height:1.75">' + f"{emphasized(digest['overview'])}" + '</p>\n    <p style="color:#475569">检索 ' + f"{stats['retrieved']}" + ' · 去重 ' + f"{stats['unique']}" + ' · 候选 ' + f"{stats['candidates']}" + ' · 重点 ' + f"{stats['focus']}" + ' · 潜在 ' + f"{stats['watch']}" + _report_category_text(' · cs.CV 余项 ') + f"{stats['cv_remainder']}" + '</p>\n  </section>\n  <section style="background:#fff;border-radius:12px;padding:18px;margin:16px 0">\n    <h2 style="margin-top:0">今日优先阅读顺序</h2><ol>' + f"{html_list(digest['reading_order'])}" + '</ol>\n  </section>\n  <h2>重点推荐论文</h2>' + f'{focus}' + '\n  <h2>潜在关注论文</h2>' + f'{watch}' + '\n  <section style="background:#fff;border-radius:12px;padding:18px;margin:16px 0">\n    <h2 style="margin-top:0">今日研究趋势</h2><ul>' + f"{html_list(digest['trends'])}" + '</ul>\n  </section>\n  <section style="background:#fff;border-radius:12px;padding:18px;margin:16px 0">\n    <h2 style="margin-top:0">对当前研究的可执行启发</h2><ul>' + f"{html_list(digest['actionable_insights'])}" + _report_category_text('</ul>\n  </section>\n  <h2>当日其它 cs.CV 更新</h2>\n  <p style="color:#64748b">按相关性降序；前 50 篇展示四项摘要，其余使用紧凑格式。共 ') + f"{remainder['total']}" + ' 篇。</p>\n  ' + f'{cv_remainder}' + '\n  <section style="color:#64748b;font-size:13px;line-height:1.7">\n    <div>检索和筛选统计：retrieved=' + f"{stats['retrieved']}" + ', unique=' + f"{stats['unique']}" + ', candidates=' + f"{stats['candidates']}" + ', focus=' + f"{stats['focus']}" + ', watch=' + f"{stats['watch']}" + ', cv_remainder=' + f"{stats['cv_remainder']}" + ', excluded_hidden=' + f"{stats['excluded_hidden']}" + _report_category_text('</div>\n    <div>七类完整覆盖：') + f'{emphasized(coverage)}' + '</div>\n    <div>本次使用的 arXiv 检索工具：' + f"{emphasized(', '.join(digest['arxiv_tools']))}" + '</div>\n  </section>\n</main>\n</body>\n</html>\n')


def markdown_paper(paper: dict[str, Any], index: int) -> str:
    authors = ", ".join(str(author) for author in paper["authors"])
    categories = ", ".join(str(category) for category in paper["categories"])
    return f"""### {index}. {paper['title']}

- 作者：{authors}
- arXiv ID：{versioned_arxiv_label(paper)}
- 分类：{categories}
- 提交或更新时间：{paper['submitted_or_updated']}
- 链接：[arXiv]({paper['arxiv_url']}) · [PDF]({paper['pdf_url']})
- 相关性：{paper['relevance_score']}/100
- 推荐等级：{paper['recommendation']}
- 证据级别：{paper['evidence_level']}
- 一句话核心结论：{paper['core_conclusion']}
- 主要研究问题：{paper['research_problem']}
- 方法概述：{paper['method_overview']}
- 主要贡献：{paper['contributions']}
- 与当前研究的具体关系：{paper['research_relation']}
- 可迁移内容：{paper['transferable_ideas']}
- 局限或验证点：{paper['limitations']}
- 是否值得精读：{paper['worth_reading']}
- 建议 follow：{paper['follow_up']}

"""


def grouped_focus_markdown(papers: list[dict[str, Any]]) -> str:
    sections: list[str] = []
    global_index = 1
    for group in TOPIC_GROUPS:
        grouped = [paper for paper in papers if paper.get("topic_group") == group]
        if not grouped:
            continue
        cards = "".join(
            markdown_paper(paper, index)
            for index, paper in enumerate(grouped, global_index)
        )
        sections.append(f"### {TOPIC_LABELS[group]}\n\n{cards}")
        global_index += len(grouped)
    return "".join(sections)


def render_markdown_v3(digest: dict[str, Any]) -> str:
    stats = digest["stats"]
    lines = [
        f"# arXiv Daily — {digest['date']}",
        "",
        "## 每日总览",
        "",
        digest["overview"],
        "",
        f"检索 {stats['retrieved']} 篇；去重 {stats['unique']} 篇；本地预筛 {stats['candidates']} 篇；模型复核 {stats['model_reviewed']} 篇；重点 {stats['focus']} 篇；关注 {stats['watch']} 篇。",
        "",
        "## 今日优先阅读顺序",
        "",
    ]
    lines.extend(f"{index}. {item}" for index, item in enumerate(digest["reading_order"], 1))
    lines.extend(["", "## 重点推荐论文", ""])
    focus = grouped_focus_markdown(digest["focus_papers"])
    lines.append(focus if focus else "本次更新没有达到重点阈值的论文。\n")
    lines.extend(["## 潜在关注论文", ""])
    watch = "".join(
        markdown_paper(paper, index)
        for index, paper in enumerate(digest["watch_papers"], 1)
    )
    lines.append(watch if watch else "本次更新没有达到关注阈值的论文。\n")
    lines.extend(["## 今日研究趋势", ""])
    lines.extend(f"- {item}" for item in digest["trends"])
    lines.extend(["", "## 对当前研究的可执行启发", ""])
    lines.extend(f"- {item}" for item in digest["actionable_insights"])
    lines.extend(
        [
            "",
            "## 本地完整报告",
            "",
            f"- Markdown：{digest['local_reports']['inventory_markdown']}",
            f"- JSON：{digest['local_reports']['inventory_json']}",
            "",
        ]
    )
    return "\n".join(lines)


def markdown_cv_detailed(paper: dict[str, Any], index: int) -> str:
    authors = ", ".join(str(author) for author in paper["authors"])
    return f"""### {index}. {paper['title']}

- 作者：{authors}
- arXiv ID：{versioned_arxiv_label(paper)}
- 提交或更新时间：{paper['submitted_or_updated']}
- 链接：[arXiv]({paper['arxiv_url']}) · [PDF]({paper['pdf_url']})
- 相关性：{paper['relevance_score']}/100
- 一句话核心结论：{paper['core_conclusion']}
- 主要研究问题：{paper['research_problem']}
- 方法概述：{paper['method_overview']}
- 主要贡献：{paper['contributions']}

"""


def markdown_cv_compact(paper: dict[str, Any], index: int) -> str:
    return (
        f"{index}. [{paper['title']}]({paper['arxiv_url']})"
        f" · {versioned_arxiv_label(paper)}"
        f" · 相关性 {paper['relevance_score']}/100"
        f" — {paper['core_conclusion']}\n"
    )


def render_markdown_v4(digest: dict[str, Any]) -> str:
    coverage = "\n".join(
        f"- {entry['category']}: raw={entry['raw_count']}, unique={entry['unique_count']}, complete=true"
        for entry in digest["retrieval_coverage"]
    )
    return render_markdown_v3(digest) + _report_category_text('\n## 七类检索覆盖\n\n') + coverage + "\n"


def render_markdown(digest: dict[str, Any]) -> str:
    digest = canonicalize_digest(digest)
    validate_digest(digest)
    if digest.get("schema_version") == SCHEMA_VERSION:
        return render_markdown_v4(digest)
    window = digest["retrieval_window"]
    stats = digest["stats"]
    focus = grouped_focus_markdown(
        digest["focus_papers"]
    ) or "本次更新没有发现需要重点推荐的论文。\n\n"
    watch = "".join(
        markdown_paper(paper, index)
        for index, paper in enumerate(digest["watch_papers"], 1)
    ) or "本次更新没有潜在关注论文。\n\n"
    reading = "\n".join(f"{index}. {item}" for index, item in enumerate(digest["reading_order"], 1))
    trends = "\n".join(f"- {item}" for item in digest["trends"])
    insights = "\n".join(f"- {item}" for item in digest["actionable_insights"])
    remainder = digest["cv_daily_remainder"]
    cv_detailed = "".join(
        markdown_cv_detailed(paper, index)
        for index, paper in enumerate(remainder["detailed"], 1)
    )
    cv_compact = "".join(
        markdown_cv_compact(paper, index)
        for index, paper in enumerate(
            remainder["compact"],
            len(remainder["detailed"]) + 1,
        )
    )
    cv_remainder = cv_detailed + cv_compact
    if not cv_remainder:
        cv_remainder = _report_category_text('本次没有其它符合展示条件的 cs.CV 更新。\n')
    coverage = "\n".join(
        (
            f"- {entry['category']}: raw={entry['raw_count']}, "
            f"unique={entry['unique_count']}, records={len(coverage_records(entry))}, "
            f"sources={','.join(coverage_sources(entry))}, "
            "complete=true"
        )
        for entry in digest["retrieval_coverage"]
    )
    tools = ", ".join(digest["arxiv_tools"])
    return ('# arXiv Daily — ' + f"{digest['date']}" + '\n\n检索范围：' + f"{window['from']}" + ' — ' + f"{window['to']}" + '\n\n## 每日总览\n\n' + f"{digest['overview']}" + '\n\n检索 ' + f"{stats['retrieved']}" + ' 篇，去重后 ' + f"{stats['unique']}" + ' 篇，初筛候选 ' + f"{stats['candidates']}" + ' 篇，重点 ' + f"{stats['focus']}" + ' 篇，潜在关注 ' + f"{stats['watch']}" + _report_category_text(' 篇，cs.CV 余项 ') + f"{stats['cv_remainder']}" + ' 篇。\n\n## 今日优先阅读顺序\n\n' + f"{reading or '本次无优先阅读项。'}" + '\n\n## 重点推荐论文\n\n' + f'{focus}' + '## 潜在关注论文\n\n' + f'{watch}' + '## 今日研究趋势\n\n' + f"{trends or '- 本次更新没有形成可靠的新趋势判断。'}" + '\n\n## 对当前研究的可执行启发\n\n' + f"{insights or '- 本次更新没有新增可执行启发。'}" + _report_category_text('\n\n## 当日其它 cs.CV 更新\n\n按相关性降序；前 50 篇展示四项摘要，其余使用紧凑格式。共 ') + f"{remainder['total']}" + ' 篇。\n\n' + f'{cv_remainder}' + _report_category_text('\n\n## 七类检索覆盖\n\n') + f'{coverage}' + '\n\n## 检索和筛选统计\n\n- retrieved: ' + f"{stats['retrieved']}" + '\n- unique: ' + f"{stats['unique']}" + '\n- candidates: ' + f"{stats['candidates']}" + '\n- focus: ' + f"{stats['focus']}" + '\n- watch: ' + f"{stats['watch']}" + '\n- cv_remainder: ' + f"{stats['cv_remainder']}" + '\n- excluded_hidden: ' + f"{stats['excluded_hidden']}" + '\n- arXiv retrieval tools: ' + f'{tools}' + '\n')


def render_reports(root: Path, digest: dict[str, Any]) -> dict[str, Path]:
    configure_public_runtime(root)
    initialize_runtime(root)
    digest = canonicalize_digest(digest)
    validate_digest(digest)
    report_date = str(digest["date"])
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", report_date):
        raise DigestValidationError("digest.date must use YYYY-MM-DD")
    html_text = render_html(digest)
    markdown_text = render_markdown(digest)
    latest_html = root / "latest.html"
    latest_markdown = root / "latest.md"
    dated_markdown = root / f"{report_date}.md"
    pending = root / "pending-run.json"
    transaction_id = digest_transaction_id(digest)
    with _exclusive_gate_state_lock(root / "digest-transaction.lock"):
        if pending.exists():
            existing = read_json(pending)
            existing_status = existing.get("delivery_status")
            existing_id = str(
                existing.get("transaction_id") or digest_transaction_id(existing)
            )
            if existing_status == "pending" and existing_id != transaction_id:
                raise DigestValidationError(
                    "cannot overwrite an uncommitted pending digest transaction"
                )
            if existing_status == "committed" and existing_id == transaction_id:
                return {
                    "html": latest_html,
                    "markdown": latest_markdown,
                    "dated_markdown": dated_markdown,
                    "pending": pending,
                }
            if existing_status == "committing":
                raise DigestValidationError(
                    "cannot render while a digest transaction is committing"
                )
            if existing_status not in {"pending", "committing", "committed"}:
                raise DigestValidationError(
                    f"unsupported pending-run delivery_status: {existing_status}"
                )
        atomic_write_text(latest_html, html_text)
        atomic_write_text(latest_markdown, markdown_text)
        atomic_write_text(dated_markdown, markdown_text)
        pending_value = copy.deepcopy(digest)
        pending_value["schema_version"] = digest.get("schema_version", SCHEMA_VERSION)
        pending_value["transaction_id"] = transaction_id
        pending_value["delivery_status"] = "pending"
        pending_value["rendered_at"] = utc_now()
        pending_value["report_files"] = {
            "html": str(latest_html),
            "markdown": str(latest_markdown),
            "dated_markdown": str(dated_markdown),
        }
        if digest.get("schema_version") == SCHEMA_VERSION:
            pending_value["report_files"].update(digest["local_reports"])
        atomic_write_json(pending, pending_value)
    return {
        "html": latest_html,
        "markdown": latest_markdown,
        "dated_markdown": dated_markdown,
        "pending": pending,
    }


def announcement_cursors_from_coverage(
    coverage: list[dict[str, Any]],
) -> dict[str, str]:
    """Return the latest validated announcement date for each covered category."""

    cursors: dict[str, str] = {}
    for entry in coverage:
        if not isinstance(entry, dict):
            continue
        category = entry.get("category")
        batches = entry.get("batches")
        if category not in TRACKED_CATEGORIES or not isinstance(batches, list):
            continue
        dates = [
            str(batch.get("announcement_date"))
            for batch in batches
            if isinstance(batch, dict)
            and batch.get("complete") is True
            and batch.get("inventory_validated") is True
            and isinstance(batch.get("announcement_date"), str)
        ]
        if dates:
            cursors[str(category)] = max(dates)
    return cursors


def _normalize_gmail_message_ids(value: Any) -> list[str]:
    raw = value if isinstance(value, list) else [value]
    ids = [str(item).strip() for item in raw]
    if not ids or any(not item for item in ids):
        raise DigestValidationError("one or more non-empty Gmail message IDs are required")
    if len(set(ids)) != len(ids):
        raise DigestValidationError("Gmail message IDs must be unique")
    return ids


def _stored_gmail_message_ids(value: dict[str, Any]) -> list[str]:
    stored = value.get("gmail_message_ids")
    if isinstance(stored, list) and stored:
        return _normalize_gmail_message_ids(stored)
    single = value.get("gmail_message_id")
    if isinstance(single, str) and single.strip():
        return [single.strip()]
    return []


def _verified_sent_receipt_for_pending(
    root: Path, pending: dict[str, Any]
) -> dict[str, str] | None:
    """Return a SENT receipt only when it is cryptographically bound to pending."""

    if pending.get("schema_version") != SCHEMA_VERSION:
        return None
    report_date = str(pending.get("date") or "").strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", report_date):
        return None
    manifest_path = root / "deliveries" / f"arxiv-daily-{report_date}-delivery.json"
    receipt_path = (
        root
        / "deliveries"
        / f"arxiv-daily-{report_date}-receipt-v4.json"
    )
    if not receipt_path.is_file():
        receipt_path = root / "deliveries" / "delivery-receipt-v4.json"
    if not receipt_path.is_file() or not manifest_path.is_file():
        return None
    try:
        receipt = read_json(receipt_path)
        manifest = read_json(manifest_path)
        recorded_manifest = Path(str(receipt.get("manifest") or "")).resolve()
    except (DigestValidationError, OSError, TypeError, ValueError):
        return None
    gmail_message_id = str(receipt.get("gmail_message_id") or "").strip()
    manifest_sha256 = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    attestation = receipt.get("attestation")
    attestation_schema_version = receipt.get("attestation_schema_version")
    receipt_failure_code = receipt.get("failure_code")
    receipt_failure_detail = receipt.get("failure_detail")
    has_new_attestation = (
        "attestation_schema_version" in receipt or "attestation" in receipt
    )
    attestation_matches = not has_new_attestation or (
        attestation_schema_version == 1
        and not isinstance(attestation_schema_version, bool)
        and isinstance(attestation, dict)
        and attestation.get("validator") == "gmail_raw_mime_v1"
        and attestation.get("attestation_stage") == "sent"
        and attestation.get("required_label") == "SENT"
        and attestation.get("message_id_match") is True
        and attestation.get("label_verified") is True
        and attestation.get("subject_verified") is True
        and attestation.get("recipient_verified") is True
        and isinstance(attestation.get("mime_part_count"), int)
        and not isinstance(attestation.get("mime_part_count"), bool)
        and attestation["mime_part_count"] >= 3
        and attestation.get("html_part_count") == 1
        and attestation.get("html_bytes") == manifest.get("html_bytes")
        and attestation.get("html_sha256") == manifest.get("html_sha256")
        and attestation.get("attachment_count") == manifest.get("attachment_count")
        and attestation.get("pdf_part_count") == 1
        and attestation.get("pdf_filename") == manifest.get("pdf_filename")
        and attestation.get("pdf_mime_type") == "application/pdf"
        and attestation.get("pdf_disposition") == "attachment"
        and attestation.get("pdf_bytes") == manifest.get("pdf_bytes")
        and attestation.get("pdf_sha256") == manifest.get("pdf_sha256")
    )
    if (
        receipt.get("schema_version") != SCHEMA_VERSION
        or receipt.get("delivery_format") != "html_pdf_single"
        or receipt.get("stage") != "sent_verified"
        or receipt.get("body_verified") is not True
        or receipt.get("attachment_verified") is not True
        or (receipt_failure_code is not None and receipt_failure_code != "")
        or (receipt_failure_detail is not None and receipt_failure_detail != "")
        or not attestation_matches
        or not gmail_message_id
        or recorded_manifest != manifest_path.resolve()
        or receipt.get("manifest_sha256") != manifest_sha256
        or manifest.get("schema_version") != SCHEMA_VERSION
        or manifest.get("coverage_policy") != DAILY_COVERAGE_POLICY
        or manifest.get("delivery_format") != "html_pdf_single"
        or manifest.get("message_count") != 1
        or manifest.get("validated") is not True
        or receipt.get("subject") != manifest.get("subject")
        or receipt.get("html_sha256") != manifest.get("html_sha256")
        or receipt.get("pdf_sha256") != manifest.get("pdf_sha256")
    ):
        return None
    return {
        "gmail_message_id": gmail_message_id,
        "receipt_stage": "sent_verified",
    }


def _run_ids_equivalent(first: str, second: str) -> bool:
    if first == second:
        return True
    first_key = _run_date_key(first)
    second_key = _run_date_key(second)
    return first_key is not None and first_key == second_key


def _backlog_horizon_identity(requested_run_id: str) -> dict[str, Any]:
    """Return the immutable drain identity carried across one scheduled run."""

    requested_key = _run_date_key(requested_run_id)
    if requested_key is None:
        return {}
    horizon_date = datetime.strptime(requested_key, "%Y%m%d").date().isoformat()
    return {
        "backlog_drain_contract_version": BACKLOG_DRAIN_CONTRACT_VERSION,
        "backlog_horizon_run_id": requested_run_id,
        "backlog_horizon_date": horizon_date,
        # A date-bearing request is not terminal until the backlog planner proves
        # that no announcement remains through this immutable horizon.
        "backlog_drained": False,
        "continuation_required": True,
    }


def _backlog_status_fields(root: Path, requested_run_id: str) -> dict[str, Any]:
    plan = _announcement_backlog_plan(
        _committed_announcement_cursors(root.resolve()), requested_run_id,
        deferred_dates=deferred_announcement_dates(root),
    )
    if plan is None:
        return {}
    deferred = list(deferred_announcement_dates(root))
    pending = list(plan["pending_announcement_dates"])
    return {
        **_backlog_horizon_identity(requested_run_id),
        **plan,
        "deferred_announcement_dates": deferred,
        "historical_coverage_complete": not deferred and not pending,
        "selected_announcement_date": pending[0] if pending else None,
        "backlog_remaining_after_selected": max(0, len(pending) - 1),
        "next_backlog_announcement_date": pending[1] if len(pending) > 1 else None,
        "backlog_drained": not pending,
        "continuation_required": bool(pending),
    }


def transaction_status(root: Path, run_id: str) -> dict[str, Any]:
    """Return the compact, read-only recovery action for one stable run ID."""
    configure_public_runtime(root)

    root = root.resolve()
    requested_run_id = str(run_id).strip()
    if not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._+-]{0,127}", requested_run_id
    ):
        raise DigestValidationError("stable run ID is invalid")

    pending_path = root / "pending-run.json"
    pending = read_json(pending_path) if pending_path.is_file() else None
    horizon_identity = _backlog_horizon_identity(requested_run_id)
    if pending is not None:
        delivery_status = pending.get("delivery_status")
        pending_schema = pending.get("schema_version")
        pending_run_id = str(pending.get("run_id") or "").strip()
        if delivery_status in {None, "pending", "committing"}:
            if not re.fullmatch(
                r"[A-Za-z0-9][A-Za-z0-9._+-]{0,127}", pending_run_id
            ):
                raise DigestValidationError(
                    "uncommitted pending transaction has an invalid run ID"
                )
            result: dict[str, Any] = {
                "run_id": pending_run_id,
                "delivery_status": delivery_status,
                "pending_run_id": pending_run_id,
                "transaction_id": pending.get("transaction_id"),
                "report_date": pending.get("date"),
                "gmail_message_id": pending.get("gmail_message_id"),
                "gmail_message_ids": _stored_gmail_message_ids(pending),
                **horizon_identity,
            }
            if pending_run_id != requested_run_id:
                result["requested_run_id"] = requested_run_id
            if delivery_status in {None, "pending"}:
                sent_receipt = _verified_sent_receipt_for_pending(root, pending)
                if sent_receipt is not None:
                    message_id = sent_receipt["gmail_message_id"]
                    result.update(
                        {
                            "action": "finish_commit",
                            "gmail_message_id": message_id,
                            "gmail_message_ids": [message_id],
                            "receipt_stage": sent_receipt["receipt_stage"],
                            "reason": (
                                "verified SENT receipt matches the current pending "
                                "delivery manifest"
                            ),
                        }
                    )
                elif pending_schema == 3 and not _stored_gmail_message_ids(pending):
                    result["action"] = "upgrade_v3_pending"
                    result["reason"] = (
                        "unsent v3 pending state can be archived explicitly while "
                        "reusing its announcement and Top-30 review checkpoints"
                    )
                elif pending_schema in (1, 2):
                    result["action"] = "legacy_pending_blocked"
                    result["reason"] = (
                        "legacy uncommitted transaction must be resolved explicitly; "
                        "v4 will not overwrite or deliver it"
                    )
                else:
                    result["action"] = "resume_delivery"
            else:
                if not _stored_gmail_message_ids(pending):
                    raise DigestValidationError(
                        "committing transaction is missing its original Gmail message IDs"
                    )
                result["action"] = "finish_commit"
            return result
        if delivery_status != "committed":
            raise DigestValidationError(
                f"unsupported pending-run delivery_status: {delivery_status}"
            )

    backlog_fields = _backlog_status_fields(root, requested_run_id)
    if backlog_fields and not backlog_fields["pending_announcement_dates"]:
        return {
            "run_id": requested_run_id,
            "delivery_status": pending.get("delivery_status") if pending else None,
            "action": "no_announcement_due",
            "phase": "idle",
            "next_action": None,
            "reason": "no weekday announcement is pending through the requested date",
            **backlog_fields,
        }

    normalized_run_id = resolve_stable_run_id(root, requested_run_id)
    identity_fields = {"run_id": normalized_run_id, **horizon_identity}
    if normalized_run_id != requested_run_id:
        identity_fields["requested_run_id"] = requested_run_id
    if pending is not None and _run_ids_equivalent(
        str(pending.get("run_id") or ""), normalized_run_id
    ):
        committed_run_id = str(pending.get("run_id") or normalized_run_id)
        result = {
            "run_id": committed_run_id,
            "delivery_status": "committed",
            "pending_run_id": pending.get("run_id"),
            "transaction_id": pending.get("transaction_id"),
            "report_date": pending.get("date"),
            "gmail_message_id": pending.get("gmail_message_id"),
            "gmail_message_ids": _stored_gmail_message_ids(pending),
            "action": "already_complete",
        }
        if committed_run_id != requested_run_id:
            result["requested_run_id"] = requested_run_id
        result.update(backlog_fields)
        return result

    progress = run_resume_status(root, normalized_run_id)
    return {
        **identity_fields,
        "delivery_status": pending.get("delivery_status") if pending else None,
        **(
            {
                "pending_run_id": pending.get("run_id"),
                "transaction_id": pending.get("transaction_id"),
                "report_date": pending.get("date"),
                "gmail_message_id": pending.get("gmail_message_id"),
                "gmail_message_ids": _stored_gmail_message_ids(pending),
            }
            if pending is not None
            else {}
        ),
        "action": "resume_run" if progress["has_progress"] else "start_new",
        **backlog_fields,
        **{
            key: value
            for key, value in progress.items()
            if key not in {"run_id", "requested_run_id", "has_progress"}
        },
    }


def upgrade_v3_pending(root: Path, run_id: str) -> dict[str, Any]:
    """Archive an unsent v3 pending digest so its stable checkpoints can enter v4."""
    configure_public_runtime(root)

    root = root.resolve()
    with _exclusive_gate_state_lock(root / "digest-transaction.lock"):
        pending_path = root / "pending-run.json"
        if not pending_path.is_file():
            raise DigestValidationError("there is no pending v3 transaction to upgrade")
        pending = read_json(pending_path)
        if pending.get("schema_version") != 3 or pending.get("delivery_status") not in {None, "pending"}:
            raise DigestValidationError("only an unsent pending schema-v3 transaction can be upgraded")
        if _stored_gmail_message_ids(pending):
            raise DigestValidationError("v3 transaction already records external Gmail delivery")
        pending_run_id = str(pending.get("run_id") or "").strip()
        if pending_run_id and pending_run_id != run_id:
            raise DigestValidationError("v3 pending run ID does not match the requested stable run")
        run_dir = announcement_batch_output_path(root, run_id, TRACKED_CATEGORIES[0]).parent
        review_manifest = run_dir / "review-manifest-v3.json"
        if not review_manifest.is_file():
            raise DigestValidationError("v3 upgrade requires the reusable Top-30 review manifest")
        archive = run_dir / "pending-v3-upgrade.json"
        archived = copy.deepcopy(pending)
        archived["upgrade_archived_at"] = utc_now()
        archived["upgrade_target_schema"] = SCHEMA_VERSION
        if archive.exists() and read_json(archive) != archived:
            raise DigestValidationError("a different v3 upgrade archive already exists")
        if not archive.exists():
            atomic_write_json(archive, archived)
        pending_path.unlink()
        _run_dir, _manifest, _ledger, pages = _load_review_state(root, run_id)
        _decisions, missing = _load_review_decisions(
            run_dir, run_id, pages, require_complete=False
        )
        return {
            "run_id": run_id,
            "archived_pending": str(archive),
            "reused_review_pages": len(pages),
            "next_action": "review_status" if missing else "finalize_digest",
        }


def _committed_result(
    last_state: dict[str, Any],
    pending: dict[str, Any],
    transaction_id: str,
    gmail_message_ids: list[str],
) -> dict[str, Any]:
    gmail_message_id = gmail_message_ids[0]
    result = copy.deepcopy(last_state)
    remainder = pending.get("cv_daily_remainder", {})
    delivered_count = result.get("delivered_count")
    if not isinstance(delivered_count, int):
        detailed = remainder.get("detailed", []) if isinstance(remainder, dict) else []
        compact = remainder.get("compact", []) if isinstance(remainder, dict) else []
        delivered_count = (
            len(pending.get("focus_papers", []))
            + len(pending.get("watch_papers", []))
            + len(detailed if isinstance(detailed, list) else [])
            + len(compact if isinstance(compact, list) else [])
        )
    result.update(
        {
            "delivery_status": "committed",
            "transaction_id": transaction_id,
            "gmail_message_id": gmail_message_id,
            "gmail_message_ids": gmail_message_ids,
            "report_date": pending.get("date", result.get("report_date")),
            "coverage_complete": True,
            "delivered_count": delivered_count,
        }
    )
    if isinstance(pending.get("run_id"), str) and pending["run_id"].strip():
        result["run_id"] = pending["run_id"]
    return result


def _backlog_drain_after_commit(
    root: Path,
    backlog_horizon_run_id: str,
) -> dict[str, Any]:
    """Return the mandatory next transaction after one date was committed."""

    horizon_run_id = str(backlog_horizon_run_id).strip()
    identity = _backlog_horizon_identity(horizon_run_id)
    if not identity:
        raise DigestValidationError(
            "backlog horizon run ID must contain YYYYMMDD or YYYY-MM-DD"
        )
    try:
        next_transaction = transaction_status(root.resolve(), horizon_run_id)
    except DigestValidationError as exc:
        return {
            "schema_version": BACKLOG_DRAIN_CONTRACT_VERSION,
            "horizon_run_id": horizon_run_id,
            "horizon_date": identity["backlog_horizon_date"],
            "status": "blocked",
            "drain_complete": False,
            "continuation_required": False,
            "failure_code": "backlog_status_failed",
            "failure_detail": str(exc)[:512],
            "next_transaction": None,
        }

    action = str(next_transaction.get("action") or "").strip()
    if action == "no_announcement_due":
        status = ("complete_with_deferred" if next_transaction.get("deferred_announcement_dates") else "complete")
        drain_complete = not bool(next_transaction.get("deferred_announcement_dates"))
        continuation_required = False
        failure_code = None
        failure_detail = None
    elif next_transaction.get("phase_blocked") is True or action in {
        "legacy_pending_blocked",
    }:
        status = "blocked"
        drain_complete = False
        continuation_required = False
        failure_code = str(
            next_transaction.get("phase_error") or "backlog_action_blocked"
        )
        failure_detail = str(
            next_transaction.get("reason") or "backlog continuation is blocked"
        )[:512]
    else:
        status = "continue"
        drain_complete = False
        continuation_required = True
        failure_code = None
        failure_detail = None
    return {
        "schema_version": BACKLOG_DRAIN_CONTRACT_VERSION,
        "horizon_run_id": horizon_run_id,
        "horizon_date": identity["backlog_horizon_date"],
        "status": status,
        "drain_complete": drain_complete,
        "deferred_announcement_dates": next_transaction.get("deferred_announcement_dates", []),
        "continuation_required": continuation_required,
        "failure_code": failure_code,
        "failure_detail": failure_detail,
        "next_transaction": next_transaction,
    }


def commit_success(
    root: Path,
    gmail_message_id: str | list[str],
    success_at: str | None = None,
    *,
    backlog_horizon_run_id: str | None = None,
) -> dict[str, Any]:
    configure_public_runtime(root)
    gmail_message_ids = _normalize_gmail_message_ids(gmail_message_id)
    initialize_runtime(root)
    pending_path = root / "pending-run.json"
    sent_path = root / "sent-papers.json"
    last_path = root / "last-successful-run.json"
    with _exclusive_gate_state_lock(root / "digest-transaction.lock"):
        committed = _commit_success_locked(
            pending_path,
            sent_path,
            last_path,
            gmail_message_ids,
            success_at,
        )
    if backlog_horizon_run_id is not None:
        committed = copy.deepcopy(committed)
        committed["backlog_drain"] = _backlog_drain_after_commit(
            root, backlog_horizon_run_id
        )
    return committed


def _commit_success_locked(
    pending_path: Path,
    sent_path: Path,
    last_path: Path,
    gmail_message_ids: list[str],
    success_at: str | None,
) -> dict[str, Any]:
    pending = read_json(pending_path)
    validate_digest(pending)
    transaction_id = str(
        pending.get("transaction_id") or digest_transaction_id(pending)
    )
    sent_state = read_json(sent_path)
    last_state = read_json(last_path)
    pending_status = pending.get("delivery_status")
    gmail_message_id = gmail_message_ids[0]
    last_message_ids = _stored_gmail_message_ids(last_state)
    pending_message_ids = _stored_gmail_message_ids(pending)
    if (
        pending.get("schema_version") == SCHEMA_VERSION
        and last_message_ids
        and last_message_ids == gmail_message_ids
        and last_state.get("report_date") != pending.get("date")
    ):
        raise DigestValidationError(
            "each announcement date requires a distinct Gmail message ID"
        )
    last_matches = (
        last_message_ids == gmail_message_ids
        and last_state.get("report_date") == pending.get("date")
        and last_state.get("coverage_complete") is True
        and last_state.get("transaction_id", transaction_id) == transaction_id
    )
    if pending_status == "committed":
        if pending_message_ids == gmail_message_ids and last_matches:
            return _committed_result(
                last_state, pending, transaction_id, gmail_message_ids
            )
        raise DigestValidationError("pending run is already committed to another Gmail message")
    if pending_status == "committing" and pending_message_ids != gmail_message_ids:
        raise DigestValidationError(
            "pending run is committing a different Gmail message"
        )
    if pending_status not in {"pending", "committing"}:
        raise DigestValidationError("pending run is not awaiting delivery")
    # Recover the crash window after last-successful-run.json was atomically written
    # but before pending-run.json received its committed marker. Never send again.
    if last_matches:
        pending["transaction_id"] = transaction_id
        pending["delivery_status"] = "committed"
        pending["gmail_message_id"] = gmail_message_id
        pending["gmail_message_ids"] = gmail_message_ids
        pending["committed_at"] = str(last_state.get("last_successful_run") or utc_now())
        atomic_write_json(pending_path, pending)
        return _committed_result(
            last_state, pending, transaction_id, gmail_message_ids
        )
    sent_papers = sent_state.setdefault("papers", {})
    if not isinstance(sent_papers, dict):
        raise DigestValidationError("sent-papers.json papers must be an object")
    sent_at = success_at or utc_now()

    if pending.get("schema_version") == SCHEMA_VERSION:
        if len(gmail_message_ids) != 1:
            raise DigestValidationError("v4 delivery must commit exactly one Gmail message ID")
        remainder = pending["cs_cv_report"]
        # Pending digests finalized before cs.CV translation was removed still
        # carry the detailed/compact split.
        remainder_papers = remainder.get("papers")
        if remainder_papers is None:
            remainder_papers = [*remainder["detailed"], *remainder["compact"]]
        delivered_papers = (
            list(pending["focus_papers"])
            + list(pending["watch_papers"])
            + list(remainder_papers)
        )
    elif pending.get("schema_version") == 3:
        remainder = {"total": 0, "detailed": [], "compact": []}
        delivered_papers = list(pending["focus_papers"]) + list(pending["watch_papers"])
    else:
        remainder = pending["cv_daily_remainder"]
        delivered_papers = (
            list(pending["focus_papers"])
            + list(pending["watch_papers"])
            + list(remainder["detailed"])
            + list(remainder["compact"])
        )
    for paper in delivered_papers:
        base_id, parsed_version = normalize_arxiv_id(paper["arxiv_id"], paper["pdf_url"])
        version = paper.get("version")
        if version is None:
            version = parsed_version
        prior = sent_papers.get(base_id, {})
        if prior and not isinstance(prior, dict):
            raise DigestValidationError(f"invalid prior sent-paper entry: {base_id}")
        prior_version = prior.get("latest_sent_version") if prior else None
        announcement_date = paper.get("announcement_date")
        prior_announcement_date = (
            prior.get("latest_sent_announcement_date") if prior else None
        )
        version_is_current = version_rank(version) >= version_rank(prior_version)
        announcement_is_newer = (
            isinstance(announcement_date, str)
            and (
                not isinstance(prior_announcement_date, str)
                or announcement_date > prior_announcement_date
            )
        )
        if version_is_current or announcement_is_newer:
            sent_papers[base_id] = {
                "latest_sent_version": (
                    version if isinstance(version, int) else prior_version
                ),
                "latest_sent_announcement_date": (
                    announcement_date
                    if isinstance(announcement_date, str)
                    else prior_announcement_date
                ),
                "title": paper["title"],
                "sent_at": sent_at,
                "first_sent_at": prior.get("first_sent_at", sent_at) if prior else sent_at,
            }

    sent_state["schema_version"] = SCHEMA_VERSION
    next_cursor = pending.get(
        "next_version_check_cursor",
        last_state.get("version_check_cursor", 0),
    )
    announcement_cursors = announcement_cursors_from_coverage(
        pending["retrieval_coverage"]
    )
    if not announcement_cursors:
        existing_cursors = last_state.get("announcement_cursors", {})
        if isinstance(existing_cursors, dict):
            announcement_cursors = {
                str(category): str(batch_date)
                for category, batch_date in existing_cursors.items()
            }
    last_value = {
        "schema_version": SCHEMA_VERSION,
        "last_successful_run": sent_at,
        "retrieval_basis": (
            "announcement_batch"
            if announcement_cursors
            else last_state.get("retrieval_basis", "submitted_date")
        ),
        "announcement_cursors": announcement_cursors,
        "retrieval_window": pending["retrieval_window"],
        "report_date": pending["date"],
        "gmail_message_id": gmail_message_id,
        "gmail_message_ids": gmail_message_ids,
        "selected_count": len(pending["focus_papers"]) + len(pending["watch_papers"]),
        "cv_remainder_count": remainder["total"],
        "delivered_count": len(delivered_papers),
        "coverage_complete": True,
        "version_check_cursor": next_cursor,
        "transaction_id": transaction_id,
    }
    if isinstance(pending.get("run_id"), str) and pending["run_id"].strip():
        last_value["run_id"] = pending["run_id"]

    pending["transaction_id"] = transaction_id
    pending["delivery_status"] = "committing"
    pending["gmail_message_id"] = gmail_message_id
    pending["gmail_message_ids"] = gmail_message_ids
    pending["commit_started_at"] = sent_at
    atomic_write_json(pending_path, pending)
    atomic_write_json(sent_path, sent_state)
    atomic_write_json(last_path, last_value)
    pending["delivery_status"] = "committed"
    pending["transaction_id"] = transaction_id
    pending["gmail_message_id"] = gmail_message_id
    pending["gmail_message_ids"] = gmail_message_ids
    pending["committed_at"] = sent_at
    pending.pop("commit_started_at", None)
    atomic_write_json(pending_path, pending)
    return _committed_result(last_value, pending, transaction_id, gmail_message_ids)


def _report_category_text(value: str) -> str:
    # The selected category comes from the validated immutable user configuration.
    return (value.replace("cs.CV", str(REPORT_CATEGORY or "selected report category"))
            .replace("seven", "selected").replace("Seven", "Selected")
            .replace("七类检索覆盖", "已配置分类检索覆盖")
            .replace("七个", "所选").replace("七类", "所选类别"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public-config", type=Path, help="explicit public user config for rootless commands")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="initialize project-local runtime files")
    init_parser.add_argument("--root", required=True, type=Path)

    subparsers.add_parser(
        "network-preflight",
        help="verify that the Scheduled Task has a reachable HTTPS sandbox proxy",
    )
    subparsers.add_parser(
        "runtime-preflight",
        help="validate and fingerprint one Python runtime for the complete digest run",
    )

    gate_acquire_parser = subparsers.add_parser(
        "gate-acquire",
        help="wait for and acquire the project-wide arXiv MCP call lease",
    )
    gate_acquire_parser.add_argument("--root", required=True, type=Path)
    gate_acquire_parser.add_argument("--owner", required=True)
    gate_acquire_parser.add_argument(
        "--wait-timeout-seconds",
        type=float,
        default=360.0,
    )
    gate_acquire_parser.add_argument(
        "--lease-seconds",
        type=int,
        default=ARXIV_MCP_RATE_LIMIT_POLICY["lease_timeout_seconds"],
    )

    gate_release_parser = subparsers.add_parser(
        "gate-release",
        help="release an arXiv MCP call lease and optionally start HTTP 429 cooldown",
    )
    gate_release_parser.add_argument("--root", required=True, type=Path)
    gate_release_parser.add_argument("--token", required=True)
    gate_release_parser.add_argument("--rate-limited", action="store_true")

    dedupe_parser = subparsers.add_parser("dedupe", help="deduplicate candidate JSON")
    dedupe_parser.add_argument("--input", required=True, type=Path)
    dedupe_parser.add_argument("--sent-state", required=True, type=Path)
    dedupe_parser.add_argument("--output", required=True, type=Path)

    transaction_status_parser = subparsers.add_parser(
        "transaction-status",
        help="report the compact recovery action for one stable run ID",
    )
    transaction_status_parser.add_argument("--root", required=True, type=Path)
    transaction_status_parser.add_argument("--run-id", required=True)

    defer_parser = subparsers.add_parser("defer-announcement", help="operator-authorized missing date registration; never sends")
    defer_parser.add_argument("--root", required=True, type=Path)
    defer_parser.add_argument("--date", required=True)
    defer_parser.add_argument("--reason", required=True)
    defer_parser.add_argument("--authorization", required=True)

    capture_parser = subparsers.add_parser(
        "capture-current-announcements", help="archive current inventories without delivery or cursor changes",
    )
    capture_parser.add_argument("--root", required=True, type=Path)

    upgrade_pending_parser = subparsers.add_parser(
        "upgrade-v3-pending",
        help="archive an unsent v3 pending digest and reuse its stable checkpoints in v4",
    )
    upgrade_pending_parser.add_argument("--root", required=True, type=Path)
    upgrade_pending_parser.add_argument("--run-id", required=True)

    review_parser = subparsers.add_parser(
        "prepare-review",
        help="locally classify the complete inventory and write at most two Top-30 review pages",
    )
    review_parser.add_argument("--root", required=True, type=Path)
    review_parser.add_argument("--run-id", required=True)
    review_parser.add_argument(
        "--candidate-limit", type=int, default=DEFAULT_REVIEW_CANDIDATE_LIMIT
    )
    review_parser.add_argument("--page-size", type=int, default=DEFAULT_REVIEW_PAGE_SIZE)
    review_parser.add_argument(
        "--page-max-bytes", type=int, default=DEFAULT_REVIEW_PAGE_MAX_BYTES
    )

    review_status_parser = subparsers.add_parser(
        "review-status", help="return only the next bounded v3 review page"
    )
    review_status_parser.add_argument("--root", required=True, type=Path)
    review_status_parser.add_argument("--run-id", required=True)

    review_record_parser = subparsers.add_parser(
        "record-review-page", help="validate and record one bounded v3 review page"
    )
    review_record_parser.add_argument("--root", required=True, type=Path)
    review_record_parser.add_argument("--run-id", required=True)
    review_record_parser.add_argument("--page", required=True, type=int)
    review_record_parser.add_argument("--input", required=True, type=Path)

    finalize_parser = subparsers.add_parser(
        "finalize-digest", help="assemble digest-v4 and complete local inventory reports"
    )
    finalize_parser.add_argument("--root", required=True, type=Path)
    finalize_parser.add_argument("--run-id", required=True)

    shard_plan_parser = subparsers.add_parser(
        "plan-shards",
        help="plan inclusive UTC daily coverage shards",
    )
    shard_plan_parser.add_argument("--categories", nargs="+", required=True)
    shard_plan_parser.add_argument("--from-time", required=True)
    shard_plan_parser.add_argument("--to-time", required=True)
    shard_plan_parser.add_argument("--output", required=True, type=Path)

    shard_split_parser = subparsers.add_parser(
        "split-shard",
        help="split one inclusive UTC shard without gaps",
    )
    shard_split_parser.add_argument("--input", required=True, type=Path)
    shard_split_parser.add_argument("--output", required=True, type=Path)

    shard_resolve_parser = subparsers.add_parser(
        "resolve-shard",
        help="validate a search response and resolve one coverage shard",
    )
    shard_resolve_parser.add_argument("--input", required=True, type=Path)
    shard_resolve_parser.add_argument("--response", required=True, type=Path)
    shard_resolve_parser.add_argument("--output", required=True, type=Path)

    official_fetch_parser = subparsers.add_parser(
        "fetch-official-shard",
        help="fetch one validated shard from the official arXiv Atom API",
    )
    official_fetch_parser.add_argument("--root", required=True, type=Path)
    official_fetch_parser.add_argument("--priority-root", type=Path)
    official_fetch_parser.add_argument("--digest-session-token")
    official_fetch_parser.add_argument("--input", required=True, type=Path)
    official_fetch_parser.add_argument("--output", required=True, type=Path)
    official_fetch_parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=OFFICIAL_ARXIV_API_TIMEOUT_SECONDS,
    )

    announcement_fetch_parser = subparsers.add_parser(
        "fetch-announcement-batch",
        help="fetch and validate one category's current arXiv announcement batch",
    )
    announcement_fetch_parser.add_argument("--root", required=True, type=Path)
    announcement_fetch_parser.add_argument("--priority-root", type=Path)
    announcement_fetch_parser.add_argument("--digest-session-token")
    announcement_fetch_parser.add_argument("--category", required=True)
    announcement_fetch_parser.add_argument(
        "--cursor-date",
        help="last successfully delivered announcement date for this category",
    )
    announcement_fetch_parser.add_argument("--output", required=True, type=Path)
    announcement_fetch_parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=OFFICIAL_ARXIV_API_TIMEOUT_SECONDS,
    )
    announcement_fetch_parser.add_argument(
        "--hydrate-versions",
        action="store_true",
        help="optionally resolve vN values omitted by the announcement page",
    )

    failure_report_parser = subparsers.add_parser(
        "write-failure-report",
        help="write a dated failure report using a normalized project-local path",
    )
    failure_report_parser.add_argument("--root", required=True, type=Path)
    failure_report_parser.add_argument("--date", required=True)
    failure_report_parser.add_argument("--input", required=True, type=Path)

    validate_parser = subparsers.add_parser("validate", help="validate a structured digest")
    validate_parser.add_argument("--input", required=True, type=Path)

    render_parser = subparsers.add_parser("render", help="validate and render digest reports")
    render_parser.add_argument("--root", required=True, type=Path)
    render_parser.add_argument("--input", required=True, type=Path)

    commit_parser = subparsers.add_parser(
        "commit-success",
        help="commit delivery state after confirmed Gmail success",
    )
    commit_parser.add_argument("--root", required=True, type=Path)
    commit_parser.add_argument(
        "--gmail-message-id",
        required=True,
        action="append",
        help="verified Gmail message ID; repeat once per delivery part",
    )
    commit_parser.add_argument("--success-at")
    commit_parser.add_argument(
        "--backlog-horizon-run-id",
        required=True,
        help=(
            "immutable original scheduled run ID; commit returns the next oldest "
            "transaction and becomes terminal only after the horizon is drained"
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    configure_public_cli(args)
    if args.command == "init":
        initialize_runtime(args.root.resolve())
        print(f"Initialized digest runtime: {args.root.resolve()}")
        return 0
    if args.command == "network-preflight":
        result = arxiv_network_preflight()
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result["ok"] else 3
    if args.command == "runtime-preflight":
        result = runtime_environment_preflight()
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result["ready"] else 3
    if args.command == "defer-announcement":
        result = defer_announcement(args.root, args.date, reason=args.reason, authorization=args.authorization)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    if args.command == "capture-current-announcements":
        result = capture_current_announcements(args.root)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result["capture_complete"] else 3
    if args.command == "gate-acquire":
        result = acquire_arxiv_mcp_gate(
            args.root.resolve(),
            args.owner,
            wait_timeout_seconds=args.wait_timeout_seconds,
            lease_seconds=args.lease_seconds,
        )
        print(json.dumps(result, ensure_ascii=False))
        return 0
    if args.command == "gate-release":
        result = release_arxiv_mcp_gate(
            args.root.resolve(),
            args.token,
            rate_limited=args.rate_limited,
        )
        print(json.dumps(result, ensure_ascii=False))
        return 0
    if args.command == "dedupe":
        raw = read_json(args.input.resolve())
        candidates = raw.get("papers", raw.get("candidates"))
        if not isinstance(candidates, list):
            raise DigestValidationError("input must contain a papers or candidates array")
        result = deduplicate_candidates(candidates, read_json(args.sent_state.resolve()))
        atomic_write_json(args.output.resolve(), result)
        print(
            f"Deduplicated {result['input_count']} candidates to "
            f"{result['unique_count']} unique and {len(result['eligible'])} eligible."
        )
        return 0
    if args.command == "transaction-status":
        print(
            json.dumps(
                transaction_status(args.root.resolve(), args.run_id),
                ensure_ascii=False,
            )
        )
        return 0
    if args.command == "upgrade-v3-pending":
        print(json.dumps(upgrade_v3_pending(args.root.resolve(), args.run_id), ensure_ascii=False))
        return 0
    if args.command == "prepare-review":
        result = prepare_review(
            args.root.resolve(),
            args.run_id,
            candidate_limit=args.candidate_limit,
            page_size=args.page_size,
            page_max_bytes=args.page_max_bytes,
        )
        print(json.dumps(result, ensure_ascii=False))
        return 0
    if args.command == "review-status":
        print(json.dumps(review_status(args.root.resolve(), args.run_id), ensure_ascii=False))
        return 0
    if args.command == "record-review-page":
        result = record_review_page(
            args.root.resolve(), args.run_id, args.page, args.input
        )
        print(json.dumps(result, ensure_ascii=False))
        return 0
    if args.command == "finalize-digest":
        print(json.dumps(finalize_digest(args.root.resolve(), args.run_id), ensure_ascii=False))
        return 0
    if args.command == "plan-shards":
        shards = initial_coverage_shards(
            args.categories,
            args.from_time,
            args.to_time,
        )
        atomic_write_json(
            args.output.resolve(),
            {"schema_version": SCHEMA_VERSION, "shards": shards},
        )
        print(f"Planned {len(shards)} initial coverage shards.")
        return 0
    if args.command == "split-shard":
        raw = read_json(args.input.resolve())
        shard = raw.get("shard", raw)
        children = split_coverage_shard(shard)
        atomic_write_json(
            args.output.resolve(),
            {"schema_version": SCHEMA_VERSION, "shards": children},
        )
        print("Split shard into 2 gap-free children.")
        return 0
    if args.command == "resolve-shard":
        raw = read_json(args.input.resolve())
        shard = raw.get("shard", raw)
        resolved = resolve_coverage_shard(shard, read_json(args.response.resolve()))
        atomic_write_json(
            args.output.resolve(),
            {"schema_version": SCHEMA_VERSION, "shard": resolved},
        )
        print(json.dumps(resolved, ensure_ascii=False))
        return 0
    if args.command == "fetch-official-shard":
        raw = read_json(args.input.resolve())
        shard = raw.get("shard", raw)
        response = fetch_official_arxiv_shard(
            args.root.resolve(),
            shard,
            priority_root=(
                args.priority_root.resolve() if args.priority_root is not None else None
            ),
            digest_session_token=args.digest_session_token,
            timeout_seconds=args.timeout_seconds,
        )
        atomic_write_json(args.output.resolve(), response)
        print(
            json.dumps(
                {
                    "source": response["source"],
                    "returned": len(response["papers"]),
                    "output": str(args.output.resolve()),
                },
                ensure_ascii=False,
            )
        )
        return 0
    if args.command == "fetch-announcement-batch":
        batch = fetch_announcement_batch(
            args.root.resolve(),
            args.category,
            cursor_date=args.cursor_date,
            priority_root=(
                args.priority_root.resolve() if args.priority_root is not None else None
            ),
            digest_session_token=args.digest_session_token,
            timeout_seconds=args.timeout_seconds,
        )
        if args.hydrate_versions:
            batch = hydrate_announcement_versions(
                args.root.resolve(),
                batch,
                priority_root=(
                    args.priority_root.resolve()
                    if args.priority_root is not None
                    else None
                ),
                digest_session_token=args.digest_session_token,
                timeout_seconds=args.timeout_seconds,
            )
        batch["coverage"] = announcement_batch_coverage(batch)
        atomic_write_json(args.output.resolve(), batch)
        print(
            json.dumps(
                {
                    "source": batch["source"],
                    "category": batch["category"],
                    "announcement_date": batch["announcement_date"],
                    "counts": batch["counts"],
                    "output": str(args.output.resolve()),
                },
                ensure_ascii=False,
            )
        )
        return 0
    if args.command == "write-failure-report":
        content = args.input.resolve().read_text(encoding="utf-8")
        outputs = write_failure_report(args.root.resolve(), args.date, content)
        print(json.dumps({key: str(path) for key, path in outputs.items()}))
        return 0
    if args.command == "validate":
        validate_digest(read_json(args.input.resolve()))
        print("Digest validation passed.")
        return 0
    if args.command == "render":
        outputs = render_reports(args.root.resolve(), read_json(args.input.resolve()))
        for label, path in outputs.items():
            print(f"{label}: {path}")
        return 0
    if args.command == "commit-success":
        result = commit_success(
            args.root.resolve(),
            args.gmail_message_id,
            args.success_at,
            backlog_horizon_run_id=args.backlog_horizon_run_id,
        )
        print(json.dumps(result, ensure_ascii=False))
        return 0
    raise DigestValidationError(f"unsupported command: {args.command}")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except DigestValidationError as exc:
        raise SystemExit(f"error: {exc}") from exc
