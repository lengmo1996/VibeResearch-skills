# VibeResearch plugin

Load this directory with a compatible Skills plugin loader. Keep the complete
package: each Skill links to shared contracts under `skills/_shared/`.
External services are user-configured; see [setup](docs/external-services.md).

The package contains 31 generic Skills. Literature monitoring supports snapshot,
weekly, watchlist, baseline, dataset, and an optional daily arXiv digest mode.
Daily instructions and runtime are included; fill the disabled configuration
template and follow [daily setup](docs/daily-arxiv-setup.md) before use.
No scheduler, account connection, or sending permission is preconfigured.

For a declared resource plan, run Python on `<plugin-root>/scripts/skills/plan_context.py`
with `--skill <canonical-name> --mode <mode>`; add `--root <plugin-root>` when needed.
The bundled public registry uses paths local to this package.

Read [LICENSE](LICENSE) and [NOTICE.md](NOTICE.md) before redistribution.
