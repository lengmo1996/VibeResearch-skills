# Daily arXiv invocation template

This is a reusable prompt, not an authorization or a replacement protocol. Fill the
bindings from the actual user's environment and explicit request. Do not publish the
filled copy. Missing values or send authorization must remain missing; never infer
them from an example, an installed plugin, or previous unrelated work.

The public runtime supports Chinese summaries, complete coverage of the user's
1–16 configured specific arXiv categories, and an explicitly selected complete-report
category from that same set. Delivery is to the authenticated Gmail account itself. It does not implement a
recipient list, arbitrary mailbox delivery, other report languages, or a standalone
Node/Gmail service.

## Bind before use

| Binding | Actual-user value |
|---|---|
| `SkillRoot` | Absolute path to the installed `literature-monitor` Skill |
| `DigestRoot` | Private absolute directory for config, state, reports and receipts |
| `ConfigPath` | `<DigestRoot>/daily-digest-config.json`, filled by the user and validated |
| `CandidatePython` | Explicit executable; runtime preflight resolves and freezes `DigestPython` |
| `InvocationDate` | Actual user's authorized arXiv listing-date upper bound `YYYY-MM-DD`; immutable backlog horizon, not local “today” |
| `ArxivDailyTools` | Actual callable names for the installed priority wrapper, normally under `arxiv_daily` |
| `GmailHost` | Host exposing the checked bridge's `mcp__codex_apps__gmail_*` operations and execution tools |
| `AuthorizedAccount` | Identity confirmed from the authenticated Gmail profile; delivery remains `me` only |
| `AuthorizationEvidence` | Actual user's explicit scope: this invocation or specified recurring task, dates/horizon, authenticated self, one attested HTML+PDF digest per date; otherwise `none` |

Categories, their complete priority permutation, the explicit `report_category`,
interest tiers, topic labels, optional exclusions, timezone, and local roots belong
in the validated configuration. Category IDs must be canonical entries in the
bundled official taxonomy snapshot; archives, wildcards and aliases are rejected.
A schedule is configured separately by the user;
the package creates no scheduled task. `configured: true` records configuration
readiness only and does not grant permission to send mail.

The configured timezone is a validated scheduling/reading convention only. It
does not alter the runtime's New York announcement cutoff or compute a horizon.
The user must supply the authorized listing-date upper bound before the invocation;
the existing runtime rules determine available dates within that fixed bound.

Initialization binds the root to the JSON file's byte hash, including whitespace.
Keep that configuration file unchanged
for every future invocation, even after a horizon is drained. A changed
configuration requires a new private root and separately authorized future scope;
do not migrate pending receipts/proofs/leases or replay already delivered dates.
Restore the original file bytes to recover the existing root after an edit.
For an existing transaction created by an older version, finish recovery using that
version and its original configuration before starting this version in a new root.
Adding `report_category` to a bound old JSON file is not a migration path.

## Copyable prompt

```text
Use $literature-monitor in daily_arxiv_email mode.

SkillRoot: <actual absolute installed Skill path>
DigestRoot: <actual private absolute state directory>
ConfigPath: <DigestRoot>/daily-digest-config.json
CandidatePython: <actual chosen Python executable>
InvocationDate: <actual user-authorized arXiv listing-date upper bound YYYY-MM-DD>
ArxivDailyTools: <actual exposed priority-wrapper tool names>
GmailHost: <actual compatible connector and execution host>
AuthorizedAccount: <actual authenticated Gmail identity, verify through profile>
AuthorizationEvidence: <actual user instruction and bounded send scope, or none>

Read SkillRoot/SKILL.md and the ENTIRE
SkillRoot/references/daily-arxiv-email.md before the first state operation.
That document is the sole detailed authority. Keep its Fixed contract,
Recovery and preflight, and Verified commit and backlog drain sections available
from the start. This prompt does not replace or shorten its phase contracts.

Validate ConfigPath using the bundled daily_digest_config.py --root DigestRoot
--check. Use the actual user's configured interests; do not reuse publisher
preferences. Resolve CandidatePython once, run runtime-preflight with
--public-config ConfigPath, and bind its returned absolute executable as
DigestPython. Require ready=true and timezone_ready=true. Use DigestPython for
all runtime/delivery commands, bridge pythonExe and commit-success. Commands with
--root load the same configuration; commands without --root require the explicit
--public-config argument before the subcommand. Never switch interpreters mid-run.

Treat InvocationDate as the immutable backlog horizon, fixed before the first
transaction-status call. Do not derive it from local today or the configured
timezone. Keep the runtime's original announcement-date availability rules.
Before retrieval, run
transaction-status and follow its canonical run_id and recovery action exactly.
For finish_commit, immediately use its verified message ID and original horizon
for commit-success before any other tool, then consume backlog_drain.next_transaction.
Do not insert configuration checks, interpreter resolution or preflights into
that immediate commit branch; their required initial context is already loaded.
For no_announcement_due, stop without network or mutation. State under DigestRoot
is the recovery authority; do not consult or write host automation memory.

Before any Gmail preparation or mutation, require actual-user authorization for
the specified invocation or recurring task and authenticated account. If absent,
stop and report the missing authorization; this template is not a grant.
Do not change the recipient from authenticated self. Loading credentials,
connecting Gmail or completing configuration does not authorize a send.

Follow the complete protocol for atomic coverage of EVERY configured category,
bounded review, translation of the configured report category, rendering,
independent Draft/SENT raw-MIME attestation, proof phases,
leases, monotonic send attempts, exact-SENT-first recovery and backlog commits.
Use the checked bridge; do not call a Gmail connector outside it. Preserve all
denial, ambiguous-send, legacy and reauthorization fences. A scheduled run must
never issue or rotate a reauthorization grant. Actively collect any yielded
execution cell; never treat it as a failed send or launch an overlapping retry.

Do not print full reports, MIME, attachments, base64 or connector payloads.
Do not retrieve full text, add enrichment, generate ad-hoc runtime scripts,
merge dates, discard receipts or advance a cursor before verified SENT.
Claim successful completion only under the complete protocol's terminal rule:
backlog_drain.status=complete, drain_complete=true and nested no_announcement_due.
Otherwise preserve state and report the exact blocked or failed step.
```

For ordinary monitoring without delivery, select `snapshot`, `weekly`, `watchlist`,
`baseline`, or `dataset` instead. Do not reinterpret an unconfigured Daily run as
successful email execution.
