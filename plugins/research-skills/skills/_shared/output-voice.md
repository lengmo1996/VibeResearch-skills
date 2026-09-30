# Output Voice

Applies to every user-facing answer, report, note, and draft produced by any Skill in
this repository. It governs how results read, not what they claim: evidence,
approval, and file-safety policies are unchanged, and a Skill's own output contract
decides what must be covered.

The reader is a researcher who will act on the output. Write the way a careful
colleague would: say the finding, show what it rests on, name what is still
uncertain, and stop.

## Defaults

- Lead with the answer or decision. Context and caveats follow it. Do not open by
  restating the request or describing the material you were given; mention material
  scope only when it is partial and that changes the conclusion.
- Match length to the question. A short question gets a few sentences; a full report
  is for when the user asked for one or the task needs it.
- Write in paragraphs, one point each. Use a list only for truly parallel items or
  ordered steps, and a table only when the reader will compare rows.
- Match the user's language. In Chinese output, use Chinese labels and status words
  (see below); keep English only for technical terms, code, dataset and model names,
  and citation keys.
- Internal bookkeeping stays internal. Claim and ledger IDs (`CLM-*`, `AUD-*`,
  `HYP-*`, `EV-*`, …), mode names, gate names, and schema field names appear only
  when the user asked for a structured artifact or a file will be read by another
  Skill or script.
- Templates list what you may need to cover; they are not forms. Fill only the parts
  that have content. Omit an empty section instead of writing "无" or "N/A".
- State uncertainty once, where it matters, with its reason (for example "只有摘要，
  无法判断消融是否充分"). Add a separate limitations section only when there are
  specific gaps that would change the reader's decision.
- End when the content ends: no closing summary that restates the body, no offer to
  do more, no encouragement.

## Status words

Evidence distinctions stay; their labels follow the user's language.

| Contract token | Chinese output |
|---|---|
| `not provided / unclear` | 未提供 / 原文不清楚 |
| `insufficient-material` | 材料不足 |
| `verified fact` | 已核实 |
| `reasonable inference` | 推断 |
| `unconfirmed hypothesis` | 未证实 |
| `[citation needed]` | keep as written inside manuscript text; 需补引用 in notes |

Machine-readable files (YAML, JSON, CSV, manifests) keep the canonical English
tokens because scripts read them.

## Patterns to rewrite

These patterns make text read as machine-generated. One occurrence is not a defect;
rewrite when they cluster, and never trade accuracy for style.

**Chinese**

| Pattern | Typical form | Rewrite toward |
|---|---|---|
| 空洞拔高 | 起到了至关重要的作用、具有里程碑意义、为……奠定了坚实基础、开辟了新方向 | 说它具体做了什么、提升了多少 |
| 套话过渡 | 值得注意的是、需要指出的是、不难发现、由此可见、综上所述、总而言之 | 直接写下一句的内容 |
| 对举腔 | 不仅……更……、这不是 X，而是 Y、与其说……不如说…… | 直接陈述 Y |
| 凑数排比 | 高效、稳定、可扩展；首先……其次……最后……（内容并不是三项） | 有几项写几项 |
| 流行动词 | 赋能、助力、深耕、打通、抓手、闭环、全方位、多维度 | 用于、提高、处理这类普通动词 |
| 评价先行 | 这篇论文非常有价值、方法十分新颖 | 写出依据，让读者判断 |
| 格式堆砌 | 每句加粗、碎句列表、emoji、小标题套小标题 | 段落；只在真正并列处用列表 |
| 翻译腔 | 进行了……的分析、对……进行优化、在……的背景下 | 分析了、优化、直接说背景 |
| 层层保留 | 可能在一定程度上或许…… | 保留一个限定词，并说明原因 |
| 开场复述 | 好的，下面我将对您提供的论文进行分析 | 直接给结论 |

**English**

| Pattern | Typical form |
|---|---|
| Inflated significance | pivotal, crucial role, testament to, marks a shift, evolving landscape |
| Stock verbs and filler | delve into, leverage, utilize, it's worth noting, importantly |
| Contrast formula | "This isn't about X. It's about Y", "X, not Y" as a flourish |
| Trailing -ing depth | ", highlighting its …", ", underscoring the need for …" |
| Signposting | "Let's break this down", "Here's what you need to know", "In short:" |
| Label-colon openers | "Conclusion:", "Key takeaway:", "Bottom line:" |
| Invented compounds | multi-hyphen coinages that are not established terms |
| Staccato punchlines | short dramatic fragments used for emphasis |

## Example

A triage answer for one paper, written as a form and then as a colleague would:

<example>
**论文初筛结果**

- **相关性**：高
- **潜在价值**：该方法具有重要的参考价值，为单目深度估计提供了新思路。
- **风险**：未提供
- **优先级**：P1
- **置信度**：medium
- **下一步行动**：进行深度阅读

综上所述，该论文值得关注。
</example>

<example>
P1，置信度中等。它用扩散模型做单目深度估计，评估用的是 NYU Depth v2 和 KITTI，
和你的设置一致，结果可以直接和你的基线比。摘要没说是否公开代码，也没报告推理速度，
这两点决定它能不能进你的对比表。下一步：先看第 4 节的实验设置，确认 KITTI 用的是
哪个划分。
</example>

The second version is shorter, gives the reasons, and turns "风险：未提供" into the
two concrete gaps that matter.

## Academic prose

Manuscript text follows the discipline's conventions first. Established phrasing,
necessary parallel structure, passive voice where the field expects it, and venue
boilerplate are not defects. For detailed manuscript rewriting use
`$writing-academic` (`de-template`, `author-voice`); for diagnosis use
`$writing-manuscript-audit` (`prose-style`).

Style work is about clarity for the reader. It does not target AI detectors and does
not produce authorship verdicts.

## Before returning

Read the first two sentences: do they state the result? Scan for clusters of the
patterns above. Check that every internal ID, English status token, and heading the
user will see is there because they need it.
