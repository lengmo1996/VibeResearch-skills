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
The user must supply the authorized listing-date upper bound before the invocation,
or explicitly select the recurring date rule below, resolved once before status;
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

## Codex App 每日任务 prompt

完成公开源码包的 `docs/daily-arxiv-setup.md` 配置指南并手动试运行成功后使用。
下面是供用户主动选择的授权文本，只有用户填写并提交为该任务的指令后才生效。
阅读本文件的代理不能替用户采用它。替换全部 `<…>`，保留填好的副本在私有目录。
`TaskName` 必须与 App 中的名称相同；`AuthorizedAccount` 填手动验证的账号身份，
仅用于核对，发送目标仍为 `me`。不支持自动切换到另一个已登录账号。

```text
使用 $literature-monitor 的 daily_arxiv_email 模式执行每日 arXiv 日报。

TaskName: Daily arXiv Digest
SkillRoot: <实际安装的 literature-monitor 绝对目录>
DigestRoot: <实际私有状态绝对目录>
ConfigPath: <与上面相同的 DigestRoot>/daily-digest-config.json
CandidatePython: <通过预检的 python.exe 绝对路径>
ArxivDailyTools: <手动检查发现的 priority wrapper 实际工具名>
GmailHost: <手动检查确认兼容的 Gmail connector 与执行宿主>
AuthorizedAccount: <手动验证的当前 Gmail 账号身份>
HorizonPolicy: runtime_expected_listing_date

这是我为上述 TaskName 提交的重复运行指令。我授权该任务从启用起至我暂停或撤销，
在上述私有目录按既定协议维护状态、生成报告，并仅向上述已认证 Gmail 本人发送日报。
每次以已安装 runtime 的 expected_announcement_date() 在启动时计算的日期为公告上限；
首次处理该日期，后续允许补齐原 root 已提交游标之后至本轮上限的未完成公告。
每个公告日恰好一封经过核验的 HTML 正文加 PDF 邮件，不合并多日、不重复发送。
这不授权更换账号、修改已绑定配置、删除状态或越过模糊发送/重新授权限制。

先读取 SkillRoot/SKILL.md、本文件 daily-run-template.md 和完整
SkillRoot/references/daily-arxiv-email.md。若 Skill 未自动发现，按这里的实际路径加载。
完整协议是详细执行依据，预先加载 Fixed contract、Recovery and preflight、
Verified commit and backlog drain；不得在 finish_commit 分支中间才补读。

在任何事务操作前校验 ConfigPath，以 CandidatePython 运行 runtime-preflight，
显式传 --public-config ConfigPath，要求 ready=true 与 timezone_ready=true，
冻结返回的绝对解释器为 DigestPython。运行协议要求的 delivery preflight，核对
解释器与 fingerprint。全程使用同一 DigestPython；带 --root 的命令加载原配置，
不带 --root 的命令在子命令前传 --public-config ConfigPath。

按本文件“日期计算命令”，用 DigestPython 仅调用官方 runtime 的
expected_announcement_date() 一次，取得 YYYY-MM-DD，绑定为 InvocationDate。
此调用只求日期，不抓取、发信或修改状态；不创建临时运行脚本。
若计算失败则停止。不得用本地今天、配置时区日期或固定示例日期代替。
本轮首次 transaction-status 之后，即使跨日或补发多天，也不再计算或扩大此上限。

将上述重复运行指令作为 AuthorizationEvidence；发现占位符、授权缺失或账号不匹配则停止。
先运行 transaction-status，严格使用返回的 canonical run_id 与恢复动作，
InvocationDate 仅作为不变的 backlog horizon，不替换旧事务的日期或 run_id。
finish_commit 时立即用已绑定解释器、返回的已核验 message ID 和原 horizon
执行 commit-success，中间不插入其他工具；随后消费 backlog_drain.next_transaction。
no_announcement_due 时正常结束，不联网、不修改状态。

其余阶段完整执行协议：所有配置分类的原子公告覆盖、分页审阅、指定主报告类别
摘要、HTML/PDF 渲染、独立 Draft/SENT raw-MIME 核验、proof/lease/发送及提交。
所有 Gmail 操作只能通过 checked bridge；工具不存在则报告缺失，不另写发送脚本。
恢复时先核对 exact SENT；保留模糊发送、拒绝、legacy 与重新授权限制。
本计划任务绝不能签发或轮换 reauthorization grant；需用户处理时保留状态并报告。
主动收集尚在运行的执行 cell，不并行重试。DigestRoot 是唯一恢复依据，
不读写宿主 automation memory，不换 root、不删 receipt、不抓全文、不加额外检索。

不输出完整日报、MIME、base64、附件内容或连接器响应。
完成邮件处理须证明 verified SENT、commit-success，以及
backlog_drain.status=complete、drain_complete=true 和嵌套 no_announcement_due。
初始 no_announcement_due 单独报告“无待处理公告”，不声称新邮件已发送。
最终简要报告公告日期、发送/提交状态、剩余 backlog；失败时报告具体阻塞阶段。
```

### 日期计算命令

在前述初始预检完成后、首次 `transaction-status` 之前执行。
`RuntimeScript` 指向 `SkillRoot/scripts/daily_digest_runtime.py`。
这是对现有日期函数的只读调用，不修改 runtime，不替代公告完整性核验。

```powershell
$RuntimeScript = Join-Path $SkillRoot 'scripts/daily_digest_runtime.py'
$InvocationDate = & $DigestPython -c "import runpy, sys; from pathlib import Path; p = Path(sys.argv[1]); sys.path.insert(0, str(p.parent)); ns = runpy.run_path(str(p)); print(ns['expected_announcement_date']())" $RuntimeScript
if ($LASTEXITCODE -ne 0 -or $InvocationDate -notmatch '^\d{4}-\d{2}-\d{2}$') { throw '公告日期计算失败；停止本轮' }
```

函数按 `America/New_York` 的运行时时区规则处理夏令时和周末，返回预期最新
listing 日期；它不证明该日 listing 已经成功获取。真实公告仍由原协议校验。
不要在 App 的每日 prompt 中填一个永久不变的 `InvocationDate`，否则未来日期不会推进。
单次重跑使用本文件前面的 `Copyable prompt` 并固定原 horizon；不要为重试重算日期。

For ordinary monitoring without delivery, select `snapshot`, `weekly`, `watchlist`,
`baseline`, or `dataset` instead. Do not reinterpret an unconfigured Daily run as
successful email execution.
