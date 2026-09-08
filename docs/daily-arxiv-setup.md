# 配置自己的 Daily arXiv 运行环境

本文面向 Windows 上的 Codex App 用户。按第 0–6 节完成一次设置后，第 7 节的 prompt 可用于每天重复运行。需要你自行连接 Gmail、选择研究方向并确认发送范围；不需要手写抓取或发送脚本。当前发送桥依赖特定宿主工具，工具不可用时，安装本包本身不能使其可用。

## 0. 选择固定目录并加载 Skill

先下载并解压公开源码包，或使用公开仓库 checkout，保留整个目录。以下是一套可替换的布局，后文所有路径必须与实际布局一致：

| 用途 | 示例绝对路径 |
|---|---|
| 公开源码目录 | `C:\ResearchTools\VibeResearch-skills` |
| `SkillRoot` | `C:\ResearchTools\VibeResearch-skills\skills\global\literature-monitor` |
| 私有工作目录，供 App 打开 | `C:\ResearchDaily` |
| `DigestRoot` | `C:\ResearchDaily\digest` |
| 独立 Python 环境 | `C:\ResearchDaily\python-env` |
| `coordination_root` | `C:\ResearchDaily\arxiv-priority` |
| MCP 缓存 | `C:\ResearchDaily\arxiv-cache` |

在 App 中打开私有工作目录作为项目，采用本地运行。若已安装完整插件，`SkillRoot` 改为实际插件内的 `skills/literature-monitor` 目录，不要另装同名 Skill。若直接使用源码，在 prompt 中提供上述绝对路径并要求读取该处 `SKILL.md` 即可；未被自动发现时不要假装 `$literature-monitor` 已被加载。不要单独复制 Skill 文件夹，否则共享脚本的相对路径会失效。

先在 PowerShell 确认 `py -3 --version` 为 Python 3.11 或更高；没有 Python 时先从 [Python 官方下载页](https://www.python.org/downloads/windows/)安装。每节代码在同一个 PowerShell 窗口依次执行；换窗口后重新设置 `SkillRoot`、`DigestRoot`、`CandidatePython`、`ConfigPath`，并重新运行预检来取得 `DigestPython`。

公开包带有事务运行脚本、邮件核验桥和 arXiv 优先级 wrapper；它没有替你安装外部 MCP、连接 Gmail 或创建计划任务。先完成下面的本地配置和能力检查，再使用运行模板。安装和配置完成都不代表你已授权发信。

当前版本输出中文摘要，由你选择 1–16 个 arXiv 具体分类，并从中明确指定一个主报告类别 `report_category`。每次必须完整取得所有已配置分类的公告；兴趣词和排序只影响后续筛选，不能缩小覆盖范围。主报告为指定类别生成完整的合格论文摘要。收件人只支持当前已认证 Gmail 账号本人，即 `me`；不支持改成另一个邮箱、Cc 或 Bcc。

## 1. 准备外部依赖

选择一个你管理的 Python 3.11+ 环境，避免替换已有项目的依赖。该环境需要：

- `arxiv-mcp-server==0.5.0` 及其依赖；bundled wrapper 会检查这个确切版本。
- `reportlab`、`pypdf`，以及能成功构造 `ZoneInfo("America/New_York")` 的系统时区数据或 `tzdata`。
- `pdftoppm`、`pdfinfo` 在执行环境的 PATH 中。它们来自你单独安装的 Poppler 工具。
- 可合法使用的中文字体。当前代码查找 Windows 的 DengXian 或 Microsoft YaHei 常规/粗体文件；本包不提供字体，不支持在 JSON 中虚构一个尚未实现的字体字段。
- 兼容的 PowerShell/PTY 与 `functions.exec` 执行宿主，以及下文说明的 Gmail connector。Node.js 可用于桥接脚本检查和测试；单独运行 Node 不会提供 Gmail 和宿主工具。

上游 [0.5.0 发布页](https://pypi.org/project/arxiv-mcp-server/0.5.0/) 声明 Python 3.11+ 和 Apache-2.0；这里固定版本是因为本包 wrapper 的实际导入接口，不表示最新版本已通过兼容验证。本工作流只抓取公告元数据与摘要，不要求开启上游全文/PDF、语义索引等扩展能力。

如果你选择新建独立环境，可在替换下面所有占位值后运行；这是安装示例，本包不会执行它：

```powershell
$DailyEnvironment = '<你选定的独立 Python 环境绝对目录>'
if (Test-Path -LiteralPath $DailyEnvironment) { throw '目录已存在；请使用已验证的环境或选择新目录，不要覆盖' }
py -3 -m venv $DailyEnvironment
if ($LASTEXITCODE -ne 0) { throw '环境创建失败' }
$CandidatePython = Join-Path $DailyEnvironment 'Scripts/python.exe'
& $CandidatePython -m pip install 'arxiv-mcp-server==0.5.0' reportlab pypdf tzdata
if ($LASTEXITCODE -ne 0) { throw '依赖安装失败' }
```

当前发送桥使用 PowerShell 和 Windows PTY 交互约定；在其他宿主上，需先适配并验证完整回执/MIME 协议，不能只把 shell 名称换掉就声称可用。下面不提供未经验证的跨平台发送命令。

安装 Poppler 后，把包含 `pdftoppm.exe` 和 `pdfinfo.exe` 的目录加入 Windows 用户 PATH，并重新打开 PowerShell 与 App。可从 [Poppler 项目页](https://poppler.freedesktop.org/)了解项目及发行来源；选择你信任的 Windows 构建。运行以下命令应分别显示程序路径与版本，失败时先修复 PATH：

```powershell
Get-Command pdftoppm, pdfinfo
pdftoppm -v
pdfinfo -v
```

中文字体由后面的 delivery preflight 检查；缺失时安装有使用权的等线或微软雅黑常规/粗体字体，再重跑预检。不要从本仓库寻找字体附件。

## 2. 填写私有配置

以实际安装路径为 `SkillRoot`，以你自己选择的私有状态目录为 `DigestRoot`。目录必须在公开 checkout 之外。首次复制模板时不要覆盖已有配置：

```powershell
$SkillRoot = '<已安装 literature-monitor 的绝对目录>'
$DigestRoot = '<你自己的私有日报状态绝对目录>'
$CandidatePython = '<上述环境的真实 python.exe 路径>'
$ConfigPath = Join-Path $DigestRoot 'daily-digest-config.json'
if (Test-Path -LiteralPath $ConfigPath) { throw '已有配置，请检查；初始化后必须保持原文件字节，不要覆盖或重新格式化' }
New-Item -ItemType Directory -Path $DigestRoot -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $SkillRoot 'templates/daily-digest-config.example.json') -Destination $ConfigPath
```

用编辑器打开 `ConfigPath` 并填写真实设置：

```powershell
notepad.exe $ConfigPath
```

例如，一位选择机器学习方向的用户可以填写下列完整 JSON。**这只是填法示例，请将路径、分类、主报告类别及兴趣词替换为你自己的选择，再初始化。** JSON 中用 `/` 表示 Windows 路径可避免反斜杠转义问题：

```json
{
  "schema_version": 1,
  "configured": true,
  "digest_root": "C:/ResearchDaily/digest",
  "coordination_root": "C:/ResearchDaily/arxiv-priority",
  "recipient": "me",
  "timezone": "Asia/Shanghai",
  "categories": ["cs.LG", "stat.ML"],
  "category_order": ["cs.LG", "stat.ML"],
  "report_category": "cs.LG",
  "topic_tiers": {"A": ["representation learning"], "B": ["self-supervised"], "C": []},
  "topic_labels": {
    "direct_interest": "直接关注主题",
    "method_interest": "方法主题",
    "transfer_interest": "可迁移主题",
    "other_relevant": "其他相关主题"
  },
  "architecture_terms": [],
  "context_terms": [],
  "exclusions": {"primary": [], "secondary": []}
}
```

| 字段 | 规则 |
|---|---|
| `schema_version` | 保留 `1` |
| `configured` | 完成全部配置后设为 `true`；它不是发送授权 |
| `digest_root` | 与本次 `DigestRoot` 相同的绝对路径 |
| `coordination_root` | 本机所有相关 arXiv wrapper 共用的私有优先级协调目录 |
| `recipient` | 保留 `me`；实际账号由 Gmail profile 与每次 MIME 核验绑定 |
| `timezone` | 用于用户调度/阅读约定并校验有效性的 IANA 时区；不改变纽约公告截止规则，也不自动计算 horizon |
| `categories` | 由你选择 1–16 个不重复的官方具体分类 ID，必须存在于本包的离线分类目录中；不预填研究方向 |
| `category_order` | `categories` 的完整排列，不能缺项、重复或增加分类；定义本地候选审阅排序的类别优先级，不减少完整覆盖 |
| `report_category` | 必须明确填写且属于 `categories`，用于完整摘要报告；不隐式取列表首项 |
| `topic_tiers.A` | 至少一个你自己的主要关注词；不使用发布者研究方向 |
| `topic_tiers.B`、`topic_tiers.C` | 你的次级与可迁移关注词，可为空 |
| `topic_labels` | 四个固定 ID `direct_interest`、`method_interest`、`transfer_interest`、`other_relevant` 的用户可读标签 |
| `architecture_terms`、`context_terms` | 你选择的匹配词数组，可为空 |
| `exclusions.primary`、`exclusions.secondary` | 你明确选择的排除词数组，可为空 |

`configured: false`、空分类列表、未指定主报告类别、空主要兴趣或未填写的根目录会使校验失败。不要添加用户名、密码、token、实际 Gmail 地址或计划任务凭据；这些不属于该 JSON 的配置字段。仅有研究关键词会影响本地筛选，不能替代摘要证据。

分类 ID 依据 [arXiv 官方分类目录](https://arxiv.org/category_taxonomy)。本包的 [离线目录](../skills/global/literature-monitor/scripts/daily_digest_categories.py) 固定于 2026-09-07，收录 149 个 canonical 具体分类及六个别名映射。填写时使用大小写准确的 canonical ID；`math`、`physics` 等父级 archive、通配符和未知 ID 不接受。六个别名也会被拒绝，并提示对应的 canonical ID，防止同一类别重复配置或公告身份不一致。合法具体 ID 不一定含点，例如 `gr-qc` 和 `quant-ph`；这些只是语法说明，不是预选方向。若官方新增分类，应先审查并更新目录和实现，再使用新版；不要绕过校验或把未知 ID 改成任意字符串匹配。

离线目录只验证配置输入，不证明某日公告完整。实际运行仍逐类校验官方 listing 的来源、公告日期、数量、完整清单和 hash。[arXiv API 手册](https://info.arxiv.org/help/api/user-manual.html) 中的 `cat` 是搜索分类字段，`submittedDate` 是 GMT 提交时间；搜索结果不能替代本协议要求的单日官方公告批次。

初始化会将状态根目录绑定到原 JSON 文件字节的摘要，连空格和格式变化也会触发不匹配。初始化前可编辑，并应在私有位置保留原文件备份；初始化后始终保持原文件字节，完成一次日报或排空 horizon 后也不能原地修改分类、主报告类别、兴趣、根目录、排除词或时区。需要新配置时，使用新的私有 root、重新校验，并明确新的未来运行范围；不要复制尚未结束的 receipt/proof/lease，不借换 root 重送已送达的公告。原 root 因配置被改而拒绝恢复时，应还原原 JSON 文件字节；未结束的事务仍用原 root 和原配置恢复。

升级前若有旧版事务，先用创建它的脚本版本和原配置完成恢复，再在新 root 启用新版和未来授权范围。不要给已绑定的旧 JSON 补写 `report_category`，也不要用复制状态或修改 hash 的方式升级。运行时保留 `cv_*`、`cs_cv_report` 和相关 CLI 名称作为兼容接口；它们现在处理配置指定的主报告类别，不固定到某个研究领域。

先执行只读校验：

```powershell
& $CandidatePython (Join-Path $SkillRoot 'scripts/daily_digest_config.py') --root $DigestRoot --check
if ($LASTEXITCODE -ne 0) { throw '请先完成配置，不进入运行阶段' }
```

配置正确后，执行运行环境预检并冻结解释器。以下调用不进行公告抓取或邮件发送：

```powershell
$RuntimeScript = Join-Path $SkillRoot 'scripts/daily_digest_runtime.py'
$DeliveryScript = Join-Path $SkillRoot 'scripts/daily_digest_delivery.py'
$RuntimeResult = & $CandidatePython $RuntimeScript --public-config $ConfigPath runtime-preflight
if ($LASTEXITCODE -ne 0) { throw '运行环境预检失败' }
$RuntimeCheck = $RuntimeResult | ConvertFrom-Json
if (-not $RuntimeCheck.ready -or -not $RuntimeCheck.timezone_ready) { throw '运行环境不完整' }
$DigestPython = $RuntimeCheck.python_executable
$DeliveryResult = & $DigestPython $DeliveryScript --public-config $ConfigPath preflight
if ($LASTEXITCODE -ne 0) { throw '邮件渲染预检失败' }
$DeliveryCheck = $DeliveryResult | ConvertFrom-Json
if (-not $DeliveryCheck.ready -or $DeliveryCheck.python_executable -ne $DigestPython -or $DeliveryCheck.runtime_fingerprint -ne $RuntimeCheck.runtime_fingerprint) { throw '渲染能力或解释器绑定不一致' }
$DeliveryCheck | ConvertTo-Json -Depth 4
```

阅读预检结果，要求 delivery 的 `ready: true`、`python_executable` 和 `runtime_fingerprint` 与 runtime 一致。随后整个调用都使用同一个 `DigestPython`；没有 `--root` 的命令要在子命令前传 `--public-config $ConfigPath`，有 `--root` 的命令自动加载该 root 的同一配置。不要在运行中切换环境。

首次初始化会在私有根目录生成状态文件；只在上述配置与预检通过、且你允许在该目录创建状态后执行：

```powershell
& $DigestPython $RuntimeScript init --root $DigestRoot
```

已有运行状态无需重复初始化。恢复调用以 `transaction-status` 返回的动作和 canonical `run_id` 为准；安装说明不能替代完整恢复协议。

配置和解释器检查只在调用的初始阶段执行。`transaction-status` 一旦返回 `finish_commit`，必须使用预先绑定的解释器立即提交它给出的已核验消息 ID；不得在中间再插入配置检查、delivery preflight 或其他工具。

## 3. 配置 arXiv MCP 实例

### Codex App 配置

Codex 的 MCP 使用 TOML。打开 App 的设置 → MCP servers，添加名为 `arxiv_daily` 的 STDIO 服务并填写下面的 command/args；也可将以下段落合并进用户的 `~/.codex/config.toml`。先备份原文件，只新增这一段；已有同名服务时检查并更新原段，不要重复定义或覆盖整个配置。替换示例路径后保存并重启 MCP 服务，必要时重启 App、新开对话。

```toml
[mcp_servers.arxiv_daily]
command = 'C:\ResearchDaily\python-env\Scripts\python.exe'
args = [
  'C:\ResearchTools\VibeResearch-skills\skills\global\literature-monitor\scripts\arxiv_priority_mcp_server.py',
  '--role', 'digest',
  '--coordination-root', 'C:\ResearchDaily\arxiv-priority',
  '--storage-path', 'C:\ResearchDaily\arxiv-cache',
  '--digest-root', 'C:\ResearchDaily\digest'
]
```

这里使用 TOML 单引号，因此 Windows 反斜杠无需双写。`command` 必须是通过预检的同一 Python。App、CLI 与 IDE 可共享用户 MCP 配置；配置格式与设置入口参见 [OpenAI 官方 MCP 文档](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)。不要把下面其他客户端的 JSON 直接粘进 TOML 文件。

### 其他兼容客户端配置

这是一个通用 MCP `mcpServers` 启动配置示例，不会自动写入任何客户端配置文件。替换全部路径，并按实际宿主格式配置；`arxiv_daily` 只是本例的别名。wrapper 使用 stdio，并从所选解释器导入外部 `arxiv-mcp-server==0.5.0`：

```json
{
  "mcpServers": {
    "arxiv_daily": {
      "command": "/ABSOLUTE/PATH/TO/daily-python.exe",
      "args": [
        "/ABSOLUTE/PATH/TO/literature-monitor/scripts/arxiv_priority_mcp_server.py",
        "--role", "digest",
        "--coordination-root", "/ABSOLUTE/PATH/TO/private-priority-gate",
        "--storage-path", "/ABSOLUTE/PATH/TO/private-arxiv-cache",
        "--digest-root", "/ABSOLUTE/PATH/TO/private-digest-root"
      ]
    }
  }
}
```

`--digest-root` 必须等于配置中的 `digest_root`，`--coordination-root` 必须等于配置中的 `coordination_root`。如果你还运行普通 arXiv wrapper，其协调目录必须相同，才能实现互斥和优先级。不要另起一个无共享 gate 的并行抓取流程。

通过宿主的工具发现确认实际暴露的 `fetch_announcement_phase` 等操作及参数 schema。普通上游 `search_papers` 不等于本包原子公告阶段；缺少 wrapper 能力就报告未配置，不用搜索 API 冒充完整公告批次。此配置示例不执行服务部署或联网自测。

## 4. 连接 Gmail 并单独授权

当前 checked bridge 需要实际宿主提供 `mcp__codex_apps__gmail_*`，包括 `get_profile`、`list_drafts`、`read_email`、`read_email_thread`、`search_email_ids`、`search_emails`、`create_draft`、`update_draft`、`send_draft` 的受支持输入输出形式。raw MIME、Draft 与 underlying message 的身份以及账号 profile 必须可核验。仅仅具有一个 Gmail token 或名字相似的 MCP 不能证明兼容。

桥还依赖 `tools.exec_command`、`tools.write_stdin`、PowerShell/PTY 和可分阶段执行的 `functions.exec`。用户通过宿主正常连接自己的 Gmail 账号；不要把认证信息放进 Skill、MCP 示例或日报 JSON。任何工具缺失都停止相关动作，不绕过 checked bridge。

用户需要另外明确：允许哪个调用或哪个定时任务、授权的 arXiv listing 公告日期上限（`YYYY-MM-DD`，即本轮 backlog horizon）、仅向当前认证账号本人发送、每个公告日恰好一封经过核验的 HTML+PDF 日报。没有这项实际授权时，模板必须停止在 Gmail 准备/变更之前。若想定期发送，授权要覆盖该具体任务的重复运行；本包既不创建计划任务，也不填写替用户授权的话。

在 App 的应用/连接器管理入口连接自己的 Gmail，并在准备运行的对话中启用。入口名称可能随 App 版本变化；以实际连接器为准。连接后执行第 6 节的只读检查来确认兼容性；只有名称叫 Gmail、但没有上述工具或 raw MIME 读取能力的连接，不能通过此检查。

首次 `transaction-status` 前固定本轮公告日期上限，后续调用不改变它。这个日期不是任意时区的“本地今天”；配置中的 `timezone` 只作为用户调度/阅读约定并接受有效性检查，不改变 runtime 的纽约公告 cutoff，也不会自动生成 horizon。实际可用公告日期仍按原 runtime 规则确定，并受用户已固定的上限约束。

对重复任务，你可以明确选择运行模板中的 `runtime_expected_listing_date` 规则：每次开始时用已安装 runtime 的 `expected_announcement_date()` 计算一次日期，作为本轮上限并保持不变。该规则只有经你选择并提交为任务指令后才属于实际授权，不因文档中存在示例而生效。

## 5. 使用运行模板

读取并填写 [daily-run-template.md](../skills/global/literature-monitor/references/daily-run-template.md)，把研究配置、安装路径、解释器、实际工具名、授权公告日期上限、账号身份和真实授权依据交给执行宿主。模板要求启动前读取 [完整协议](../skills/global/literature-monitor/references/daily-arxiv-email.md)，包括最初预读 commit 规则。

完整协议负责所有配置分类的完整覆盖、主报告类别的分页摘要、分页审阅、Draft/SENT raw-MIME 核验、独立 proof/send 阶段、模糊发送结果恢复和 backlog drain。不要从安装文档自行拼装发送脚本；不要因预检通过就宣称已连接 MCP、已发送或已提交成功。本次公开候选的离线检查不包含真实 Gmail/arXiv 连接或真实计划任务验收。

## 6. 先手动检查，再试运行一次

在私有工作目录的新对话中粘贴以下内容，替换三个路径。此步骤不发信：

```text
请检查 Daily arXiv 的安装是否可运行，只做读取和预检。
SkillRoot: <实际 literature-monitor 绝对目录>
DigestRoot: <实际私有 digest 绝对目录>
CandidatePython: <第 1 节选定的 python.exe 绝对路径>
读取 SkillRoot/SKILL.md 与 references/daily-arxiv-email.md。
核对配置、我指定的 Python 环境及 runtime/delivery preflight。
通过工具发现核对 arxiv_daily 的 fetch_announcement_phase 能力与参数 schema，
以及 checked bridge 要求的 Gmail/执行工具。不要抓取公告或修改邮件。
账号检查仅通过 checked bridge 的 getProfile 核对；工具不可用时报告未验证。
不创建/更新/发送 Draft，不初始化或修改事务状态，不创建计划任务。
请返回：配置、Python、字体/Poppler、arXiv 工具、Gmail 工具/账号分别是否就绪；
实际 SkillRoot、CandidatePython、ArxivDailyTools、GmailHost 和缺失项。
工具名必须来自当前发现结果，不能根据示例猜测；不要输出凭据或完整连接器响应。
```

将输出的真实路径和工具名填入[运行模板](../skills/global/literature-monitor/references/daily-run-template.md)。确认第 2 节已初始化后，在普通对话中提交填好的单次 prompt，并明确本次公告日期与本人发信授权。首次新 root 处理选定日期，不自动补齐使用本工具之前的全部历史；以后从已提交游标补齐遗漏公告，可能一次收到多天的邮件，每个公告日一封。

收到邮件后检查 HTML 正文和 PDF 附件都可阅读，并核对任务结果：已验证 SENT、已 commit，且 `backlog_drain.status=complete`、`drain_complete=true`、嵌套 `no_announcement_due`。若本来没有待处理公告，无需发送邮件，这是正常空运行。仅有“生成完成”或“草稿已创建”不算发送成功。

## 7. 在 Codex App「已安排」创建每日任务

1. 打开「已安排 / Scheduled」，创建独立的重复任务；如果当前版本从对话创建，就在私有项目对话中请求创建任务，并在保存前核对下面各项。
2. 名称填 `Daily arXiv Digest`，项目选择第 0 节的私有工作目录；使用本地目录，不为每次运行创建新的状态 root 或 Git worktree。
3. 频率选每天，时间与时区明确设置。例如在 `Asia/Shanghai` 每天 11:30 运行；这是阅读时间示例，公告日期仍由 runtime 规则决定。核对 App 显示的下次运行时间。
4. 粘贴运行模板中的 **Codex App 每日任务 prompt**，替换所有 `<…>`。明确勾选/提交其中你接受的重复发送范围；若不接受，先修改或不要创建任务。
5. 确认任务能读取 Skill、运行同一 Python、写入私有工作目录并使用已检查的 MCP/Gmail 工具。按宿主支持的最小权限配置；不要用关闭所有审批或修改 receipt 来解决失败。
6. 保存后检查前几次运行记录。需要本地文件的任务运行时，电脑须开机且 App 保持运行；网络、凭据或工具失效会使任务停止。恢复后继续使用原 root。

官方说明支持在计划 prompt 中显式调用 `$skill-name`，并建议先手动测试再安排运行。界面入口可能随版本变化，参见 [OpenAI Scheduled 文档](https://learn.chatgpt.com/docs/automations?surface=app)。本教程没有替你创建任务。

## 8. 常见问题与恢复

| 现象 | 下一步 |
|---|---|
| 找不到 Skill 或共享脚本 | 核对完整源码/插件目录和 prompt 的绝对路径，重新开对话 |
| `public_digest_not_configured` 或配置校验失败 | 初始化前补齐字段并校验；已绑定 root 则恢复原配置字节，不改 hash |
| Python、时区、字体或 Poppler 预检失败 | 修复所选环境与 PATH，重启 App，再用同一解释器预检 |
| `arxiv_daily_capability_missing` | 检查 TOML、MCP 服务启动与真实工具发现；普通 search_papers 不能替代它 |
| Gmail/执行工具不兼容 | 使用暴露所需工具的宿主；不要换一个同名 MCP 后直接发信 |
| `no_announcement_due` | 正常无新公告；不创建空邮件，不重置状态 |
| 草稿存在、发送结果模糊或等待重新授权 | 暂停计划任务，在普通对话按原 root 的完整恢复协议处理；先查 exact SENT，不自行重发。计划任务不能签发重新授权 |
| 想改分类、兴趣或换 Gmail 账号 | 先暂停任务并完成旧事务；使用新 root、新配置及明确的未来范围，重新预检与试运行，避免重送已送达日期 |

报错时提供简短错误码、失败阶段、运行 ID 与预检摘要即可；不要公开私有配置、收件账号、MIME 或凭据。
