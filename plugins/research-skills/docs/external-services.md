# External capabilities

Skills are instructions and small validation helpers, not a hosted research service.
Only configure the integrations needed for the chosen workflow. Keep credentials,
endpoints, local library roots, and user research profiles outside tracked files.

- Retrieval: the shared KnowledgeHub contract describes a read-only interface.
  Supply a compatible service or adapter if a mode requires it. Optional modes may
  work from supplied documents. Required retrieval failure stops dependent claims.
- Zotero: use an authorized local export or read-only metadata source. This package
  does not enable an API, choose a library, or grant write access.
- Documents and visuals: supply suitable PDF/Office readers or rendering tools
  for the requested artifact. Report unsupported rendering as not performed.
- Code and experiments: inspect the actual project runtime and resources before
  execution. Bundled version-specific references are scoped references, not a
  command to replace the user's environment.

## Daily arXiv integrations

The public package includes its own Daily transaction runtime, delivery validator,
Gmail bridge and priority wrapper. It does not install external packages, connect a
Gmail account, deploy an MCP service, create a scheduled task or grant send rights.
Use [Daily setup](daily-arxiv-setup.md) and keep the completed user configuration
outside the public checkout.

| Capability | Bundled implementation | User-supplied requirement |
|---|---|---|
| arXiv announcement retrieval | `arxiv_priority_mcp_server.py`, priority gate and compatibility helper | Python environment containing `arxiv-mcp-server==0.5.0`; configure its bundled wrapper as a stdio MCP server and bind the actual exposed tool names |
| Local reports and MIME validation | `daily_digest_runtime.py` and `daily_digest_delivery.py` | ReportLab, pypdf, IANA timezone data, Poppler `pdftoppm`/`pdfinfo` and supported Chinese fonts |
| Gmail Draft/SENT attestation and delivery | `daily_digest_gmail_bridge.js` | Authenticated compatible Gmail connector, PowerShell/PTY execution tools, bounded host phases, and explicit authorization from the actual account user |
| Configuration | Unconfigured JSON template, local validator and dated category-code snapshot | 1–16 official specific arXiv categories, one selected complete-report category, actual interests, private roots, IANA timezone and optional exclusions; recipient remains authenticated self (`me`) |
| JavaScript verification | Bridge source and applicable tests | Node.js for local JavaScript checks; Node alone does not supply Gmail connector or host tool bindings |
| Scheduling | Reusable prompt that references the full protocol | User-selected scheduler, executable, timezone, schedule and explicit recurring-send authorization |

The wrapper checks upstream version 0.5.0 before importing its tool implementations.
That [versioned upstream release](https://pypi.org/project/arxiv-mcp-server/0.5.0/)
declares Python 3.11+ and Apache-2.0. This is a compatibility pin, not a claim that it
is the latest release or that a newer version is compatible.

Category selection is validated offline against the bundled snapshot of the
[official arXiv taxonomy](https://arxiv.org/category_taxonomy), dated 2026-09-07.
It contains category identifiers and alias mappings, not paper content. A valid
configuration does not establish complete announcement coverage: each live run
must still validate every selected category's exact-date official batch under the
full transaction protocol.

The current Gmail bridge calls `mcp__codex_apps__gmail_*`, `tools.exec_command` and
`tools.write_stdin`, and launches PowerShell for bounded PTY validation. A host must
expose the expected operation schemas, including raw-MIME readback and underlying
Draft/message identities. A generic OAuth token or Gmail REST client does not by
itself satisfy that contract. Stop if the host lacks these capabilities; do not
replace raw attestation with connector summaries or attachment URLs.

Font lookup currently targets Windows DengXian or Microsoft YaHei regular/bold
files. Fonts are not bundled. The platform-independent Skill instructions and
static checks do not establish that the Daily sending bridge runs unchanged on
another operating system. Missing rendering or host support must be reported as
unavailable, not worked around by weakening validation.

No scheduling configuration, connector secret, research corpus, private project
state, completed user preference profile, or external-service installation is
bundled. Connecting an account and filling configuration never authorizes sending.
