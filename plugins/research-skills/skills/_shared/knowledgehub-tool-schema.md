# KnowledgeHub MCP Tool Schema Snapshot

Observed by read-only MCP `initialize` + `tools/list` on 2026-07-15, protocol `2025-03-26`, using the normalized `/mcp/` endpoint. Discover again at runtime because schemas may change.

| Tool | Required input | Important optional inputs / constraints |
|---|---|---|
| `rag_search` | `query` (1–4000 chars) | `mode`: dense/sparse/hybrid (default hybrid); `limit`: 1–50 (default 10); `prefetch_limit`: 1–200 (default 50); `filters`; `fallback`: strict/degrade; `reranker`: off/auto/light/quality; `neighbors.before/after`: 0–5; `max_chars_per_hit`: 256–20000 |
| `rag_get_chunk` | `chunk_id` | `max_chars`: 256–120000 (default 20000) |
| `rag_get_document` | `document_id` | `include_abstract`; `chunk_cursor`; `chunk_limit`: 1–500. Returns metadata and paginated chunk index, not full text. |
| `rag_get_neighbors` | `chunk_id` | `before/after`: 0–10 (default 2); `max_chars_per_chunk`: 256–20000 |
| `rag_resolve_reference` | exactly one logical identifier | `doi`, `citation_key`, `item_key`, `attachment_key`, or `title`; send one even though the JSON schema does not enforce exclusivity |
| `rag_list_facets` | `facet` | facet: collection/tag/year/source; numeric-string `cursor`; `limit`: 1–200 |
| `rag_status` | none | `verbose` boolean, default false |

`rag_search.filters` accepts `collection`, `tag`, `year_from`, `year_to`, `doi`, `document_id`, `attachment_key`, and `source` (currently constant `zotero`). All schemas set `additionalProperties: false`. No write, ingest, index, update, or delete tool was exposed.

The configured URL without a trailing slash responds with HTTP 307. Generic clients must use the normalized `/mcp/` URL or preserve Authorization across the redirect; otherwise the redirected request can appear as `invalid_token`.
