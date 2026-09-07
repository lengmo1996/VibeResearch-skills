# 配置自己的 Daily arXiv 运行环境

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
py -3 -m venv $DailyEnvironment
if ($LASTEXITCODE -ne 0) { throw '环境创建失败' }
$CandidatePython = Join-Path $DailyEnvironment 'Scripts/python.exe'
& $CandidatePython -m pip install 'arxiv-mcp-server==0.5.0' reportlab pypdf tzdata
if ($LASTEXITCODE -ne 0) { throw '依赖安装失败' }
```

当前发送桥使用 PowerShell 和 Windows PTY 交互约定；在其他宿主上，需先适配并验证完整回执/MIME 协议，不能只把 shell 名称换掉就声称可用。下面不提供未经验证的跨平台发送命令。

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

首次 `transaction-status` 前固定本轮公告日期上限，后续调用不改变它。这个日期不是任意时区的“本地今天”；配置中的 `timezone` 只作为用户调度/阅读约定并接受有效性检查，不改变 runtime 的纽约公告 cutoff，也不会自动生成 horizon。实际可用公告日期仍按原 runtime 规则确定，并受用户已固定的上限约束。

## 5. 使用运行模板

读取并填写 [daily-run-template.md](../skills/global/literature-monitor/references/daily-run-template.md)，把研究配置、安装路径、解释器、实际工具名、授权公告日期上限、账号身份和真实授权依据交给执行宿主。模板要求启动前读取 [完整协议](../skills/global/literature-monitor/references/daily-arxiv-email.md)，包括最初预读 commit 规则。

完整协议负责所有配置分类的完整覆盖、主报告类别的分页摘要、分页审阅、Draft/SENT raw-MIME 核验、独立 proof/send 阶段、模糊发送结果恢复和 backlog drain。不要从安装文档自行拼装发送脚本；不要因预检通过就宣称已连接 MCP、已发送或已提交成功。本次公开候选的离线检查不包含真实 Gmail/arXiv 连接或真实计划任务验收。
