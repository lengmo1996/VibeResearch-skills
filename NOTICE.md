# Attribution and third-party terms

The [MIT license](LICENSE) applies to contributor-owned VibeResearch content,
except files expressly identified below under other terms. References to papers,
products, tools or standards do not transfer rights in those materials.

## Included arXiv adapters

Two files in `skills/global/literature-monitor/scripts/`, and their matching
`skills/literature-monitor/scripts/` copies in the standalone plugin, are
distributed under [Apache-2.0](LICENSES/Apache-2.0.txt):

- `arxiv_pdf_compat.py`: adapts the PDF fallback in
  `src/arxiv_mcp_server/tools/download.py` from arxiv-mcp-server 0.5.0.
  Changes include streaming into a temporary PDF for arxiv 4.x compatibility and
  ensuring cleanup after conversion. The file carries its source and modification
  notice; this distribution preserves its runtime behavior.
- `arxiv_priority_mcp_server.py`: the tool catalog and stdio initialization refer
  to the upstream `src/arxiv_mcp_server/server.py` interface. The public adapter
  uses an explicit tool/handler table, derives role-visible tools and dispatch
  from that table, and supplies its own guarded daily workflow. Upstream notices
  are retained with this file; revising its short adapter skeleton is not used
  as a claim that earlier code had no upstream origin.

Upstream: [arxiv-mcp-server, fixed source revision](https://github.com/blazickjp/arxiv-mcp-server/tree/d22255b0c24578ed214d2918d2ff2786d92a778e)
(`v0.5.0`, `d22255b0c24578ed214d2918d2ff2786d92a778e`).
Copyright 2024 Joseph Blazick. File headers describe the corresponding changes.
The root MIT license does not replace the Apache-2.0 terms for these two files.

The full external `arxiv-mcp-server==0.5.0` Python distribution and its handlers
are not bundled. Users install that dependency separately. No upstream NOTICE
file was found in the checked 0.5.0 wheel or source distribution; the attribution
above is this project's own record, not a claimed upstream NOTICE.

## Visual workflow reference and presentation resources

Visual-system workflow ideas were informed by
[UI UX Pro Max, Next Level Builder](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill/tree/4857a2c5ef989794751a0f66b8545a4a49566286),
revision `4857a2c5ef989794751a0f66b8545a4a49566286`.
The referenced project's root [MIT notice](LICENSES/UI-UX-Pro-Max-MIT.txt),
Copyright (c) 2024 Next Level Builder, is retained with this acknowledgement.
Upstream CSV databases, fonts, screenshots and runtime packages are not bundled
in these visual Skill directories.

The three `paper-to-ppt/assets/catalogs/` JSON resources and four references
(`visual-decision-framework.md`, `layout-and-style-rules.md`,
`typography-color-chart-rules.md`, and
`interaction-motion-responsive-accessibility.md`) were written for this public
distribution from academic-presentation requirements and the existing program
interfaces. Their accompanying text distinguishes project heuristics from cited
accessibility guidance. This replacement records how the current resources were
prepared; it does not certify the authorship of every earlier resource.

## Separately supplied software and services

ReportLab, pypdf, timezone data, Node.js, Poppler, fonts, Gmail and other connectors
remain separately supplied components subject to their own terms. Font names in
configuration or code do not grant permission to redistribute font files.
The package includes no account, credentials, private endpoint, scheduler or
consent to send mail. See [external services](docs/external-services.md) and
[Daily setup](docs/daily-arxiv-setup.md) for configuration and validation limits.

## arXiv category identifiers

The offline catalog records 149 canonical identifiers and six alias mappings from
the [official arXiv category taxonomy](https://arxiv.org/category_taxonomy), checked
on 2026-09-07. It includes no category descriptions or paper content. The snapshot
supports local input validation; it is not an arXiv endorsement or a claim that
future taxonomy changes have already been incorporated.
