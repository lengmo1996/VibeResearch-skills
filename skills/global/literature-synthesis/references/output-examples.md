# Literature Synthesis Output Examples

Shape of a good answer, not a template. Papers and numbers are invented for
illustration. Claim IDs appear in the matrix's evidence column, where the reader can
trace them; running prose uses paper names.

<example>
User: 结合我的文献库，比较单目深度估计里三种引入尺度信息的方式。

Answer:
先说结论：库里 9 篇相关论文里，用相机内参做条件是主流（5 篇），但三种方式之间没法
直接比结果，因为只有 2 篇在同一数据集和同一指标下做过对比。

**范围**
问题是单目深度估计如何获得绝对尺度。检索了你的 KnowledgeHub，两轮，第二轮没有新增
论文；时间限定 2022 年以后。

**对比表**

| 方式 | 论文 | 数据集 / 指标 | 主要发现 | 证据 |
|---|---|---|---|---|
| 相机内参作条件 | IntrinsicDepth 等 5 篇 | KITTI / AbsRel，NYU / AbsRel | 多数只报告整体误差，没有针对内参输入的消融 | CLM-02, 05, 11 |
| 稀疏点云监督 | SparseScale、LidarPrompt | KITTI / AbsRel, RMSE | LidarPrompt 在同设置下比内参条件低 0.004 AbsRel | CLM-08 |
| 语义先验估尺度 | SemScale、ObjectRuler | 自建数据集 | 数据集不公开，无法对齐 | CLM-13 |

唯一可比的一组是 LidarPrompt 的消融：同一主干、同一数据集，点云监督略好。但这是一篇
论文里的单次实验，没有方差，不足以说明它普遍更好。

**证据台账**（见附带的 claim-evidence 表）

**覆盖局限**
SemScale 和 ObjectRuler 只有摘要在库里。2 篇重复条目已合并。库外的工作没有检索，
所以这不是这个方向的完整综述。
</example>
