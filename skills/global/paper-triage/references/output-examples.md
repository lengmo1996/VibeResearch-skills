# Paper Triage Output Examples

Three shapes of a good answer. They show tone, length, and what goes where; they are
not templates to copy. Paper titles are invented for illustration.

<example>
User: 帮我看看这篇值不值得读。我在做单目深度估计，主要看室外场景。
Title: Example Diffusion Prior for Monocular Depth. Abstract: …

Answer:
P1，置信度中等。它把预训练扩散模型当作深度估计的先验，评估用了 KITTI 和 NYU Depth
v2，室外部分和你的设置一致，结果可以直接放进你的对比。摘要没提代码是否公开，也没
报告推理速度，扩散类方法在这两点上差别很大，决定它能不能当基线。下一步：读第 4 节，
确认 KITTI 用的是 Eigen 划分还是官方划分。
</example>

<example>
User: 这 5 篇今天下午只有两小时，帮我排个顺序。（给出 5 篇标题和摘要）

Answer:
| 论文 | 优先级 | 置信度 | 理由 | 下一步 |
|---|---|---|---|---|
| Example Metric Depth Transformer | P0 | 高 | 你正在选基线，它在 KITTI Eigen 划分上报告了同设置的误差 | 读实验和消融（约 40 分钟） |
| Example Self-Supervised Stereo Depth | P1 | 中 | 训练方式接近你的方案，但只在室内数据上评估 | 读方法部分 |
| Example Survey of Depth Estimation | P2 | 高 | 综述，写相关工作时有用，今天用不上 | 留着 |
| Example Indoor Scene Segmentation | P3 | 高 | 任务是分割，和深度估计无关 | 跳过 |
| Example Unified Geometry Net | 材料不足 | 低 | 只有标题 | 先找摘要 |

两小时够读前两篇。第五篇只有标题，拿到摘要后再排。
</example>

<example>
User: 这篇怎么样？Title: Example Unified Geometry Foundation Model

Answer:
只有标题，没法判断它和你的方向有多相关，也看不出方法和实验。先找到摘要或 arXiv
页面再排优先级。
</example>
