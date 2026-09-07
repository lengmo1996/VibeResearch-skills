# VibeResearch

31 reusable research workflows for paper reading, literature work, experiment
design, code changes, academic writing, submission checks, and research visuals.
Each Skill declares its modes, evidence limits, inputs, outputs, and side effects.

VibeResearch provides configurable workflows and their local validation tools.
See [NOTICE.md](NOTICE.md) for the identified upstream adaptations, visual-workflow
references, and the licenses retained with this distribution.

## Layout

- [skills/registry.yaml](skills/registry.yaml): the public capability registry.
- `skills/global/` and `skills/coding/`: canonical Skill instructions and resources.
- [skills/_shared](skills/_shared): common evidence and operational contracts.
- [plugins/research-skills](plugins/research-skills): one generated Skills plugin.
- [scripts/skills/plan_context.py](scripts/skills/plan_context.py): bounded resource
  plans for modes that declare them; it never executes workflow actions.

The public profile has no personal research direction or machine default. Domain
packages, project-memory governance, and historical archives are not included.
`literature-monitor` supports `snapshot`, `weekly`, `watchlist`, `baseline`,
`dataset`, and `daily_arxiv_email`. The Daily mode includes the transactional
runtime, checked Gmail bridge and arXiv priority wrapper, with an unconfigured
user-settings template. It includes no account, credential, installed external
MCP server, scheduled task, or permission to send email.

## Verify and package

Use Python 3.11 or later. Structural validation, routing/context checks and archive
construction use the Python standard library. The Daily runtime tests and actual
rendering need the external dependencies described below; a structural pass is not
evidence that Gmail or scheduled execution is configured:

```sh
python -m pip install reportlab pypdf tzdata jsonschema
python scripts/validate_public.py --test --build-check
python scripts/build_public.py --output dist/research-skills.zip
```

The offline tests also require Node.js. PDF regression tests use a ReportLab CID
test font and verify the generated document and extracted text; they do not attest
the production Windows font setup, Poppler rendering or a live Gmail connection.

The initial public release has no historical public baseline. This is reported as
not applicable; no private Git history or fabricated baseline score is required.
CI validates the actual checked-out public tree. Subsequent releases retain the
public repository's own commit history.

## Use

Open this repository in a compatible agent workspace and follow [AGENTS.md](AGENTS.md).
For example, supply a paper and ask `$paper-deep-read` to explain its method, or ask
`$research-experiment-design` for a minimal experiment plan with explicit controls.
Inspect the selected `SKILL.md` and pass the required input; unavailable services
or missing evidence must remain visible in the output.

The generated [plugin manifest](plugins/research-skills/.codex-plugin/plugin.json)
and ZIP provide a self-contained package for a compatible Skills plugin loader.
Installation support depends on the loader. Do not copy a single Skill directory
without also preserving its shared resources and relative paths.

External retrieval, Zotero, document renderers, plotting backends, and training
frameworks are supplied by the user as needed. No connector is configured by this
package. See [external services](docs/external-services.md).

## Daily arXiv email setup

Follow [Daily setup](docs/daily-arxiv-setup.md), then fill the
[configuration template](skills/global/literature-monitor/templates/daily-digest-config.example.json)
under your own private digest root. The included
[run prompt](skills/global/literature-monitor/references/daily-run-template.md)
binds your paths, categories, report category, interests, Python, MCP capabilities and actual authorization; it
requires the [complete transaction protocol](skills/global/literature-monitor/references/daily-arxiv-email.md).
Copying the prompt or setting `configured: true` is not authorization to send.

You supply these components:

- Python 3.11+, ReportLab, pypdf and working IANA timezone data.
- The external `arxiv-mcp-server==0.5.0` Python package and its MCP dependencies.
  The bundled priority wrapper imports that version; it is not the upstream server
  package itself. The [versioned upstream release](https://pypi.org/project/arxiv-mcp-server/0.5.0/)
  documents Python 3.11+ and Apache-2.0 licensing.
- Poppler's `pdftoppm` and `pdfinfo`, plus legally available Chinese fonts accepted
  by the delivery preflight. The current font lookup uses Windows DengXian or
  Microsoft YaHei regular/bold files; font files are not distributed here.
- A compatible execution host with PowerShell, PTY support and the checked Gmail
  connector operations. The current bridge targets `mcp__codex_apps__gmail_*` and
  bounded `functions.exec` phases; another Gmail MCP is not a drop-in substitute.
- Node.js for JavaScript bridge checks/tests. The bridge itself runs inside the
  compatible host with its `tools` bindings, not as an independent Node mailer.

The current Daily report is Chinese and covers every category in your configured
selection of 1–16 official specific arXiv categories. Choose one selected category
explicitly for the complete report; the template supplies no category defaults.
The offline validator uses a dated official taxonomy snapshot and rejects archive
groups, wildcards and aliases; see [configuration rules](docs/daily-arxiv-setup.md#2-填写私有配置).
Delivery is only to the authenticated Gmail account itself. Other recipients or report
languages require a separate implementation and validation. Scheduling is optional
and user-managed; installing the plugin does not create or authorize a schedule.

## Contributions and license

The canonical Skills are the maintained sources; plugin copies are generated.
Change the maintained source, regenerate the plugin, and run the validation suite.
[MIT](LICENSE) covers contributor-owned content except the files identified under
other terms in [NOTICE.md](NOTICE.md). Keep the applicable notices and the
[Apache-2.0 license](LICENSES/Apache-2.0.txt) with the included arXiv adapters.
