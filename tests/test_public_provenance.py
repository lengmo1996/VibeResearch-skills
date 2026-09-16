"""Offline MCP adapter contracts, runnable in a source or public distribution.

The actual wrapper's selected AST nodes execute with inert interface doubles.
No arXiv, Gmail, package installation, real lease, or filesystem state is used.
Pass ``--wrapper PATH`` to check a separately generated public candidate.
"""
from __future__ import annotations

import argparse
import ast
import asyncio
from contextlib import asynccontextmanager
import copy
import json
from pathlib import Path
import re
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock


WRAPPER_PATH = (Path(__file__).resolve().parents[1]
                / "skills/global/literature-monitor/scripts/arxiv_priority_mcp_server.py")
WRAPPER_SOURCE = None  # Optional in-memory fixture for the private build tests.

# This is the pinned upstream 0.5.0 public API, independent of adapter layout.
UPSTREAM_API = (
    ("search_papers", "search_tool", "handle_search"),
    ("download_paper", "download_tool", "handle_download"),
    ("list_papers", "list_tool", "handle_list_papers"),
    ("read_paper", "read_tool", "handle_read_paper"),
    ("get_abstract", "abstract_tool", "handle_get_abstract"),
    ("semantic_search", "semantic_search_tool", "handle_semantic_search"),
    ("reindex", "reindex_tool", "handle_reindex"),
    ("citation_graph", "citation_graph_tool", "handle_citation_graph"),
    ("watch_topic", "watch_topic_tool", "handle_watch_topic"),
    ("check_alerts", "check_alerts_tool", "handle_check_alerts"),
)


class ToolDouble:
    def __init__(self, *, name, description="test tool", inputSchema=None):
        self.name = name
        self.description = description
        self.inputSchema = inputSchema or {"type": "object", "properties": {}, "required": []}

    def model_copy(self, *, update, deep):
        self_copy = copy.deepcopy(self) if deep else copy.copy(self)
        for key, value in update.items():
            setattr(self_copy, key, value)
        return self_copy


class PriorityGateError(Exception):
    pass


def adapter_namespace(role):
    """Execute real definitions without running startup imports or CLI parsing."""
    ns = {
        "__name__": "_offline_public_mcp_contract",
        "ARGS": SimpleNamespace(role=role, wait_timeout_seconds=25,
                                digest_session_wait_timeout_seconds=4, digest_root=Path("fixture-root"),
                                coordination_root=Path("fixture-gate")),
        "settings": SimpleNamespace(APP_NAME="arxiv-mcp-server", APP_VERSION="0.5.0"),
        "types": SimpleNamespace(Tool=ToolDouble, TextContent=SimpleNamespace),
        "runtime": SimpleNamespace(TRACKED_CATEGORIES=("astro-ph.GA", "math.PR")),
        "TRACKED_CATEGORIES": ("astro-ph.GA", "math.PR"),
        "PriorityGateError": PriorityGateError,
        "asyncio": asyncio, "json": json, "re": re, "Path": Path,
        "NotificationOptions": Mock(side_effect=lambda **kw: SimpleNamespace(**kw)),
        "InitializationOptions": Mock(side_effect=lambda **kw: SimpleNamespace(**kw)),
        "server": SimpleNamespace(get_capabilities=Mock(return_value={"fixture_capability": True}),
                                  run=AsyncMock()),
        "gate": SimpleNamespace(acquire_call=Mock(return_value={"token": "lease-fixture"}),
                                release_call=Mock(), status=Mock(return_value={"ready": True})),
        "_tool_error_message": Mock(return_value=None),
    }
    for public_name, tool_symbol, handler_symbol in UPSTREAM_API:
        ns[tool_symbol] = ToolDouble(name=public_name, inputSchema={
            "type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"],
        })
        ns[handler_symbol] = AsyncMock(return_value=[SimpleNamespace(type="text", text=public_name)])
    selected_names = {
        "UPSTREAM_TOOL_BINDINGS", "UPSTREAM_TOOLS", "HANDLERS", "RATE_LIMIT_PATTERN",
        "DIGEST_SESSION_TOKEN_ARGUMENT", "DIGEST_SESSION_TOKEN_SCHEMA", "_digest_tool", "DIGEST_TOOLS",
        "BEGIN_DIGEST_TOOL", "END_DIGEST_TOOL", "STATUS_TOOL", "FETCH_ANNOUNCEMENT_BATCH_TOOL",
        "CAPTURE_CURRENT_ANNOUNCEMENTS_TOOL", "FETCH_ANNOUNCEMENT_PHASE_TOOL", "handle_list_tools", "handle_call_tool", "_json_content",
        "initialization_options", "main",
    }
    text = WRAPPER_SOURCE if WRAPPER_SOURCE is not None else WRAPPER_PATH.read_text(encoding="utf-8")
    source_tree = ast.parse(text, filename=str(WRAPPER_PATH))
    nodes = [ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)]
    for node in source_tree.body:
        name = None
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            name = node.name
        elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            name = node.target.id
        if name in selected_names:
            node = copy.deepcopy(node)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                node.decorator_list = []
            nodes.append(node)
    tree = ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[]))
    exec(compile(tree, str(WRAPPER_PATH), "exec"), ns)
    return ns


class PublicMcpAdapterContracts(unittest.IsolatedAsyncioTestCase):
    async def test_role_inventory_and_digest_tokens_do_not_mutate_upstream(self):
        for role in ("normal", "digest"):
            with self.subTest(role=role):
                ns = adapter_namespace(role)
                tools = await ns["handle_list_tools"]()
                names = [tool.name for tool in tools]
                expected = [entry[0] for entry in UPSTREAM_API]
                if role == "digest":
                    expected += ["capture_current_announcements", "fetch_announcement_phase", "fetch_announcement_batch",
                                 "begin_digest_session", "end_digest_session"]
                self.assertEqual(expected + ["get_priority_status"], names)
                self.assertEqual(len(names), len(set(names)))
                self.assertEqual({entry[0] for entry in UPSTREAM_API}, set(ns["HANDLERS"]))
                for original in ns["UPSTREAM_TOOLS"]:
                    self.assertNotIn("digest_session_token", original.inputSchema["properties"])
                if role == "digest":
                    for tool in tools[:len(UPSTREAM_API)]:
                        self.assertIn("digest_session_token", tool.inputSchema["required"])
                        self.assertIn("query", tool.inputSchema["required"])
                    category_schema = tools[len(UPSTREAM_API) + 2].inputSchema["properties"]["category"]
                    self.assertEqual(["astro-ph.GA", "math.PR"], category_schema["enum"])
                tools.clear()
                self.assertEqual(names, [tool.name for tool in await ns["handle_list_tools"]()])

    async def test_every_exposed_data_tool_dispatches_its_bound_handler_under_a_lease(self):
        for role in ("normal", "digest"):
            for public_name, _tool_symbol, handler_symbol in UPSTREAM_API:
                with self.subTest(role=role, tool=public_name):
                    ns = adapter_namespace(role)
                    arguments = {"query": "fixture"}
                    if role == "digest":
                        arguments["digest_session_token"] = " fixture-session "
                    original = dict(arguments)
                    result = await ns["handle_call_tool"](public_name, arguments)
                    ns[handler_symbol].assert_awaited_once_with({"query": "fixture"})
                    self.assertEqual(public_name, result[0].text)
                    self.assertEqual(original, arguments)
                    ns["gate"].acquire_call.assert_called_once_with(
                        role, f"{role}:{public_name}", digest_token="fixture-session" if role == "digest" else None,
                        wait_timeout_seconds=25,
                    )
                    ns["gate"].release_call.assert_called_once_with("lease-fixture", rate_limited=False)

    async def test_unknown_and_unauthorized_calls_do_not_acquire_a_lease(self):
        ns = adapter_namespace("normal")
        for name in ("capture_current_announcements", "begin_digest_session", "end_digest_session", "fetch_announcement_batch", "fetch_announcement_phase"):
            with self.subTest(name=name), self.assertRaises(PriorityGateError):
                await ns["handle_call_tool"](name, {})
        with self.assertRaises(ValueError):
            await ns["handle_call_tool"]("not_an_upstream_tool", {})
        ns["gate"].acquire_call.assert_not_called()
        ns = adapter_namespace("digest")
        with self.assertRaises(PriorityGateError):
            await ns["handle_call_tool"]("search_papers", {"query": "fixture"})
        ns["gate"].acquire_call.assert_not_called()
        ns["handle_search"].assert_not_awaited()

    async def test_rate_limit_error_and_cancellation_always_release_the_lease(self):
        for failure in (RuntimeError("HTTP 429"), asyncio.CancelledError(), RuntimeError("other failure")):
            with self.subTest(failure=type(failure).__name__, text=str(failure)):
                ns = adapter_namespace("digest")
                ns["handle_search"].side_effect = failure
                with self.assertRaises(type(failure)):
                    await ns["handle_call_tool"]("search_papers", {"digest_session_token": "fixture-session"})
                ns["gate"].release_call.assert_called_once_with(
                    "lease-fixture", rate_limited=isinstance(failure, RuntimeError) and "429" in str(failure),
                )

    async def test_upstream_error_payload_remains_an_error_with_rate_limit_cooldown(self):
        ns = adapter_namespace("normal")
        ns["_tool_error_message"].return_value = "Too many requests"
        with self.assertRaisesRegex(RuntimeError, "Too many requests"):
            await ns["handle_call_tool"]("search_papers", {})
        ns["gate"].release_call.assert_called_once_with("lease-fixture", rate_limited=True)

    async def test_stdio_identity_capabilities_stream_order_and_cleanup(self):
        for role in ("normal", "digest"):
            for run_failure in (None, RuntimeError("fixture transport failure")):
                with self.subTest(role=role, failure=run_failure):
                    ns = adapter_namespace(role)
                    incoming, outgoing = object(), object()
                    lifecycle = []

                    @asynccontextmanager
                    async def stdio():
                        lifecycle.append("opened")
                        try:
                            yield incoming, outgoing
                        finally:
                            lifecycle.append("closed")

                    ns["stdio_server"] = stdio
                    ns["server"].run.side_effect = run_failure
                    if run_failure:
                        with self.assertRaisesRegex(RuntimeError, "fixture transport failure"):
                            await ns["main"]()
                    else:
                        await ns["main"]()
                    ns["server"].run.assert_awaited_once()
                    supplied_in, supplied_out, options = ns["server"].run.await_args.args
                    self.assertIs(incoming, supplied_in)
                    self.assertIs(outgoing, supplied_out)
                    self.assertEqual(f"arxiv-mcp-server-{role}-priority", options.server_name)
                    self.assertEqual("0.5.0+priority.6", options.server_version)
                    self.assertEqual({"fixture_capability": True}, options.capabilities)
                    ns["NotificationOptions"].assert_called_once_with(resources_changed=True)
                    capability_args = ns["server"].get_capabilities.call_args.kwargs
                    self.assertTrue(capability_args["notification_options"].resources_changed)
                    self.assertEqual({}, capability_args["experimental_capabilities"])
                    self.assertEqual(["opened", "closed"], lifecycle)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--wrapper", type=Path)
    args, rest = parser.parse_known_args()
    if args.wrapper:
        WRAPPER_PATH = args.wrapper.resolve()
    unittest.main(argv=[sys.argv[0], *rest])
