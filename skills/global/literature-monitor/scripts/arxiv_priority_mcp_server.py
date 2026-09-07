#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Upstream reference: arxiv-mcp-server 0.5.0, server.py tool and stdio scaffold.
# Copyright 2024 Joseph Blazick
# Source: https://github.com/blazickjp/arxiv-mcp-server/blob/d22255b0c24578ed214d2918d2ff2786d92a778e/src/arxiv_mcp_server/server.py
# Upstream attribution is retained for possible scaffold adaptation; the exact
# historical provenance of that scaffold is not established.
# Changes in VibeResearch: priority leases, digest session authorization,
# configured announcement categories, checkpoints, and PDF compatibility.
# Public export changes: one tool/handler binding table, role-specific tool
# assembly, and explicit capability and stdio stream setup. Existing priority
# enforcement, profile validation, dispatch errors, and cleanup are retained.
# See LICENSES/Apache-2.0.txt at the source or plugin distribution root.

"""Priority-enforcing stdio wrapper for arxiv-mcp-server 0.5.0."""

from __future__ import annotations

import argparse
import asyncio
import importlib.metadata
import json
import logging
import re
from pathlib import Path
from typing import Any, Awaitable, Callable

import mcp.types as types
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server

from arxiv_priority_gate import ArxivPriorityGate, PriorityGateError
from arxiv_pdf_compat import install_pdf_download_compat
import daily_digest_runtime as runtime
from daily_digest_runtime import (
    OfficialArxivFetchError,
    announcement_batch_coverage,
    fetch_announcement_phase,
    fetch_announcement_batch,
    hydrate_announcement_versions,
    store_announcement_checkpoint,
)


EXPECTED_UPSTREAM_VERSION = "0.5.0"
RATE_LIMIT_PATTERN = re.compile(
    r"(?:http(?:\s+status)?\s*)?429|too\s+many\s+requests|rate.?limit",
    flags=re.IGNORECASE,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role", choices=("normal", "digest"), required=True)
    parser.add_argument("--coordination-root", type=Path, required=True)
    parser.add_argument("--storage-path", type=Path, required=True)
    parser.add_argument(
        "--digest-root",
        type=Path,
        help=(
            "Trusted persistent Daily Digest root. Required by digest role for the "
            "fixed announcement-batch output path."
        ),
    )
    parser.add_argument("--wait-timeout-seconds", type=float, default=21600.0)
    parser.add_argument(
        "--digest-session-wait-timeout-seconds",
        type=float,
        default=300.0,
        help="bounded wait for begin_digest_session; data calls retain the normal wait timeout",
    )
    parser.add_argument("--min-interval-seconds", type=int, default=5)
    parser.add_argument("--post-digest-cooldown-seconds", type=int, default=60)
    parser.add_argument("--rate-limit-cooldown-seconds", type=int, default=60)
    parser.add_argument("--call-lease-seconds", type=int, default=21600)
    parser.add_argument("--digest-session-seconds", type=int, default=14400)
    parser.add_argument("--digest-idle-seconds", type=int, default=600)
    return parser.parse_args()


ARGS = parse_args()
if ARGS.role == "digest":
    if ARGS.digest_root is None:
        raise RuntimeError("public_digest_not_configured: digest role requires --digest-root")
    from daily_digest_runtime import configure_public_runtime
    public_profile = configure_public_runtime(ARGS.digest_root)
    if ARGS.coordination_root.resolve() != Path(public_profile["coordination_root"]):
        raise RuntimeError("public_digest_coordination_mismatch")
installed_version = importlib.metadata.version("arxiv-mcp-server")
if installed_version != EXPECTED_UPSTREAM_VERSION:
    raise RuntimeError(
        "Unsupported arxiv-mcp-server version "
        f"{installed_version}; expected {EXPECTED_UPSTREAM_VERSION}. "
        "Validate tool-schema compatibility before upgrading."
    )

from arxiv_mcp_server.config import Settings  # noqa: E402
from arxiv_mcp_server.prompts.handlers import get_prompt, list_prompts  # noqa: E402
from arxiv_mcp_server.server import _tool_error_message  # noqa: E402
from arxiv_mcp_server.tools import (  # noqa: E402
    abstract_tool,
    check_alerts_tool,
    citation_graph_tool,
    download_tool,
    handle_check_alerts,
    handle_citation_graph,
    handle_download,
    handle_get_abstract,
    handle_list_papers,
    handle_read_paper,
    handle_reindex,
    handle_search,
    handle_semantic_search,
    handle_watch_topic,
    list_tool,
    read_tool,
    reindex_tool,
    search_tool,
    semantic_search_tool,
    watch_topic_tool,
)
import arxiv_mcp_server.tools.download as upstream_download_module  # noqa: E402


PDF_DOWNLOAD_COMPAT_ACTIVE = install_pdf_download_compat(upstream_download_module)


settings = Settings()
logger = logging.getLogger("vibe-arxiv-priority-mcp")
logging.basicConfig(level=logging.INFO)
if PDF_DOWNLOAD_COMPAT_ACTIVE:
    logger.info(
        "Installed arxiv 4.x PDF fallback compatibility for arxiv-mcp-server 0.5.0"
    )
gate = ArxivPriorityGate(
    ARGS.coordination_root,
    min_interval_seconds=ARGS.min_interval_seconds,
    rate_limit_cooldown_seconds=ARGS.rate_limit_cooldown_seconds,
    post_digest_cooldown_seconds=ARGS.post_digest_cooldown_seconds,
    call_lease_seconds=ARGS.call_lease_seconds,
    digest_session_seconds=ARGS.digest_session_seconds,
    digest_idle_seconds=ARGS.digest_idle_seconds,
)
server = Server(f"{settings.APP_NAME}-{ARGS.role}-priority")

UPSTREAM_TOOL_BINDINGS = (
    (search_tool, handle_search),
    (download_tool, handle_download),
    (list_tool, handle_list_papers),
    (read_tool, handle_read_paper),
    (abstract_tool, handle_get_abstract),
    (semantic_search_tool, handle_semantic_search),
    (reindex_tool, handle_reindex),
    (citation_graph_tool, handle_citation_graph),
    (watch_topic_tool, handle_watch_topic),
    (check_alerts_tool, handle_check_alerts),
)
UPSTREAM_TOOLS = [tool for tool, _handler in UPSTREAM_TOOL_BINDINGS]

DIGEST_SESSION_TOKEN_ARGUMENT = "digest_session_token"
DIGEST_SESSION_TOKEN_SCHEMA = {
    "type": "string",
    "minLength": 1,
    "description": (
        "Opaque token returned by begin_digest_session for the active Daily Digest run. "
        "Required on every digest arXiv data-tool call so work can continue after an MCP "
        "stdio server restart."
    ),
}


def _digest_tool(tool: types.Tool) -> types.Tool:
    schema = dict(tool.inputSchema)
    properties = dict(schema.get("properties", {}))
    properties[DIGEST_SESSION_TOKEN_ARGUMENT] = DIGEST_SESSION_TOKEN_SCHEMA
    required = list(schema.get("required", []))
    if DIGEST_SESSION_TOKEN_ARGUMENT not in required:
        required.append(DIGEST_SESSION_TOKEN_ARGUMENT)
    schema["properties"] = properties
    schema["required"] = required
    return tool.model_copy(
        update={
            "description": (
                f"{tool.description or ''}\n\n"
                "Daily Digest authorization: pass digest_session_token from "
                "begin_digest_session on every call."
            ).strip(),
            "inputSchema": schema,
        },
        deep=True,
    )


DIGEST_TOOLS = [_digest_tool(tool) for tool in UPSTREAM_TOOLS]

BEGIN_DIGEST_TOOL = types.Tool(
    name="begin_digest_session",
    description=(
        "Acquire the machine-wide high-priority arXiv phase for one Daily Digest run. "
        "This operation is idempotent for the same stable run ID and returns the existing "
        "token after an MCP stdio server restart."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "run_id": {
                "type": "string",
                "description": "Stable identifier for this Daily Digest run.",
            }
        },
        "required": ["run_id"],
        "additionalProperties": False,
    },
)
END_DIGEST_TOOL = types.Tool(
    name="end_digest_session",
    description=(
        "Release the active Daily Digest arXiv phase by its machine-wide token, even when "
        "the begin call was handled by a different MCP stdio server process, then hold "
        "normal calls for 60 seconds."
    ),
    inputSchema={
        "type": "object",
        "properties": {"session_token": {"type": "string"}},
        "required": ["session_token"],
        "additionalProperties": False,
    },
)
STATUS_TOOL = types.Tool(
    name="get_priority_status",
    description="Return sanitized machine-wide arXiv priority-gate status.",
    inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
)
FETCH_ANNOUNCEMENT_BATCH_TOOL = types.Tool(
    name="fetch_announcement_batch",
    description=(
        "Fetch and validate one official arXiv /new announcement batch through the "
        "active Daily Digest priority session. The complete batch is written only to "
        "<digest-root>/runs/<active-run-id>/<category>-announcement.json; callers "
        "cannot supply a URL or output path."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "digest_session_token": DIGEST_SESSION_TOKEN_SCHEMA,
            "category": {
                "type": "string",
                "enum": list(runtime.TRACKED_CATEGORIES),
                "description": "One configured Daily Digest arXiv category.",
            },
            "cursor_date": {
                "anyOf": [
                    {
                        "type": "string",
                        "pattern": r"^\d{4}-\d{2}-\d{2}$",
                    },
                    {"type": "null"},
                ],
                "default": None,
                "description": "Last committed announcement cursor for this category.",
            },
            "hydrate_versions": {
                "type": "boolean",
                "default": False,
                "description": (
                    "Optionally resolve exact versions omitted by the announcement page."
                ),
            },
        },
        "required": ["digest_session_token", "category"],
        "additionalProperties": False,
    },
)
FETCH_ANNOUNCEMENT_PHASE_TOOL = types.Tool(
    name="fetch_announcement_phase",
    description=(
        "Atomically resume the Daily Digest announcement phase: resolve the stable "
        "run ID or newest unfinished prior-day run, reuse validated checkpoints, hold "
        "one cross-process phase lock, acquire one priority session, serially fetch "
        "every missing configured category, and release the session in a finally "
        "block. Returns compact progress only."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "run_id": {
                "type": "string",
                "minLength": 1,
                "description": (
                    "Scheduled run identifier or YYYY-MM-DD alias. The returned run_id "
                    "is the canonical identity for all later phases."
                ),
            }
        },
        "required": ["run_id"],
        "additionalProperties": False,
    },
)

HANDLERS: dict[
    str, Callable[[dict[str, Any]], Awaitable[list[types.TextContent]]]
] = {tool.name: handler for tool, handler in UPSTREAM_TOOL_BINDINGS}


def _json_content(value: dict[str, Any]) -> list[types.TextContent]:
    return [
        types.TextContent(
            type="text",
            text=json.dumps(value, ensure_ascii=False),
        )
    ]


@server.list_prompts()
async def handle_list_prompts() -> list[types.Prompt]:
    return await list_prompts()


@server.get_prompt()
async def handle_get_prompt(
    name: str, arguments: dict[str, str] | None = None
) -> types.GetPromptResult:
    return await get_prompt(name, arguments)


@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    tools = list(DIGEST_TOOLS if ARGS.role == "digest" else UPSTREAM_TOOLS)
    if ARGS.role == "digest":
        tools.extend((
            FETCH_ANNOUNCEMENT_PHASE_TOOL,
            FETCH_ANNOUNCEMENT_BATCH_TOOL,
            BEGIN_DIGEST_TOOL,
            END_DIGEST_TOOL,
        ))
    tools.append(STATUS_TOOL)
    return tools


@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict[str, Any]
) -> list[types.TextContent]:
    if name == "get_priority_status":
        return _json_content(gate.status())
    if name == "begin_digest_session":
        if ARGS.role != "digest":
            raise PriorityGateError("begin_digest_session is available only in digest role")
        result = await asyncio.to_thread(
            gate.begin_digest_session,
            str(arguments.get("run_id", "")),
            wait_timeout_seconds=ARGS.digest_session_wait_timeout_seconds,
        )
        return _json_content(result)
    if name == "end_digest_session":
        if ARGS.role != "digest":
            raise PriorityGateError("end_digest_session is available only in digest role")
        supplied_token = str(arguments.get("session_token", ""))
        result = await asyncio.to_thread(gate.end_digest_session, supplied_token)
        return _json_content(result)
    if name == "fetch_announcement_phase":
        if ARGS.role != "digest":
            raise PriorityGateError(
                "fetch_announcement_phase is available only in digest role"
            )
        if ARGS.digest_root is None:
            raise RuntimeError(
                "fetch_announcement_phase requires the MCP server --digest-root option"
            )
        result = await asyncio.to_thread(
            fetch_announcement_phase,
            ARGS.digest_root,
            str(arguments.get("run_id", "")),
            priority_root=ARGS.coordination_root,
            gate=gate,
            session_wait_timeout_seconds=ARGS.digest_session_wait_timeout_seconds,
        )
        return _json_content(result)
    if name == "fetch_announcement_batch":
        if ARGS.role != "digest":
            raise PriorityGateError(
                "fetch_announcement_batch is available only in digest role"
            )
        if ARGS.digest_root is None:
            raise RuntimeError(
                "fetch_announcement_batch requires the MCP server --digest-root option"
            )
        supplied_token = str(
            arguments.get(DIGEST_SESSION_TOKEN_ARGUMENT, "")
        ).strip()
        if not supplied_token:
            raise PriorityGateError(
                "digest_session_token is required for fetch_announcement_batch"
            )
        category = str(arguments.get("category", "")).strip()
        if category not in runtime.TRACKED_CATEGORIES:
            raise ValueError(f"unsupported tracked category: {category}")
        cursor_value = arguments.get("cursor_date")
        cursor_date = None if cursor_value is None else str(cursor_value).strip()
        if cursor_date is not None and not re.fullmatch(
            r"\d{4}-\d{2}-\d{2}", cursor_date
        ):
            raise ValueError("cursor_date must use YYYY-MM-DD")
        hydrate_versions = arguments.get("hydrate_versions", False)
        if not isinstance(hydrate_versions, bool):
            raise ValueError("hydrate_versions must be a boolean")

        bound_session = gate.require_digest_session(supplied_token)
        run_id = str(bound_session["run_id"])

        batch = await asyncio.to_thread(
            fetch_announcement_batch,
            ARGS.digest_root,
            category,
            cursor_date=cursor_date,
            priority_root=ARGS.coordination_root,
            priority_gate=gate,
            digest_session_token=supplied_token,
        )
        version_hydration: dict[str, Any] = {
            "requested": hydrate_versions,
            "complete": not hydrate_versions,
        }
        if hydrate_versions:
            try:
                batch = await asyncio.to_thread(
                    hydrate_announcement_versions,
                    ARGS.digest_root,
                    batch,
                    priority_root=ARGS.coordination_root,
                    priority_gate=gate,
                    digest_session_token=supplied_token,
                )
                version_hydration["complete"] = True
            except OfficialArxivFetchError as exc:
                version_hydration["complete"] = False
                version_hydration["failure"] = exc.as_record()
        cursor_action = str(batch.get("cursor_action", "")).strip()
        if not cursor_action:
            raise RuntimeError("announcement batch is missing cursor_action")
        coverage = announcement_batch_coverage(batch)
        complete_batch = dict(batch)
        complete_batch["requested_cursor_date"] = cursor_date
        complete_batch["cursor_action"] = cursor_action
        complete_batch["coverage"] = coverage
        complete_batch["version_hydration"] = version_hydration
        stored_batch, output_path, checkpoint_reused = store_announcement_checkpoint(
            ARGS.digest_root,
            run_id,
            category,
            complete_batch,
            cursor_date,
        )
        return _json_content(
            {
                "run_id": run_id,
                "category": category,
                "announcement_date": stored_batch.get("announcement_date"),
                "counts": stored_batch.get("counts"),
                "returned": len(stored_batch.get("papers", [])),
                "coverage": stored_batch.get("coverage"),
                "cursor_action": stored_batch.get("cursor_action"),
                "hydrate_versions": hydrate_versions,
                "version_hydration": stored_batch.get("version_hydration"),
                "checkpoint_reused": checkpoint_reused,
                "output_path": str(output_path),
            }
        )

    handler = HANDLERS.get(name)
    if handler is None:
        raise ValueError(f"unknown arXiv tool: {name}")
    handler_arguments = dict(arguments)
    digest_token: str | None = None
    if ARGS.role == "digest":
        digest_token = str(
            handler_arguments.pop(DIGEST_SESSION_TOKEN_ARGUMENT, "")
        ).strip()
        if not digest_token:
            raise PriorityGateError(
                "digest_session_token is required for a digest arXiv tool call"
            )

    lease = await asyncio.to_thread(
        gate.acquire_call,
        ARGS.role,
        f"{ARGS.role}:{name}",
        digest_token=digest_token,
        wait_timeout_seconds=ARGS.wait_timeout_seconds,
    )
    rate_limited = False
    try:
        result = await handler(handler_arguments)
        if error_message := _tool_error_message(result):
            rate_limited = bool(RATE_LIMIT_PATTERN.search(error_message))
            raise RuntimeError(error_message)
        return result
    except BaseException as exc:
        rate_limited = rate_limited or bool(RATE_LIMIT_PATTERN.search(str(exc)))
        raise
    finally:
        await asyncio.to_thread(
            gate.release_call,
            str(lease["token"]),
            rate_limited=rate_limited,
        )


def initialization_options() -> InitializationOptions:
    notifications = NotificationOptions(resources_changed=True)
    capabilities = server.get_capabilities(
        notification_options=notifications,
        experimental_capabilities={},
    )
    identity = {
        "server_name": f"{settings.APP_NAME}-{ARGS.role}-priority",
        "server_version": f"{settings.APP_VERSION}+priority.6",
    }
    return InitializationOptions(capabilities=capabilities, **identity)


async def main() -> None:
    async with stdio_server() as (incoming, outgoing):
        options = initialization_options()
        await server.run(incoming, outgoing, options)


if __name__ == "__main__":
    asyncio.run(main())
