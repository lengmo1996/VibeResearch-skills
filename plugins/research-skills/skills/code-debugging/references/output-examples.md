# Code Debugging Output Examples

Shapes of a good answer, not templates. The code and logs are invented for
illustration.

<example>
User: 训练到第 3 个 epoch loss 突然变 NaN，日志和 train.py 在下面。

Answer:
原因是 `depth_loss` 里对预测深度直接取了 log（train.py 第 88 行），而解码器最后一层是
ReLU，会输出 0。第 3 个 epoch 开始学习率预热结束，第一次出现全 0 的预测块，log(0)
得到 -inf，反传后变成 NaN。

验证过：在第 88 行前打印 `pred.min()`，NaN 出现的前一步正好是 0；把输入换成
`pred.clamp_min(1e-6)` 后用同一个种子跑到第 5 个 epoch，没有再出现 NaN，loss 曲线和
之前前两个 epoch 一致。

建议的改法是把最后一层换成 softplus，或者保留 ReLU 并在取 log 前 clamp。前者改变了
输出分布，需要重新对比指标；后者改动最小。我还没改你的代码，确认后再动。
</example>

<example>
User: 这个 traceback 是什么意思？ RuntimeError: Expected all tensors to be on the same device, but found at least two devices, cuda:0 and cpu!

Answer:
有一个张量还在 CPU 上。从堆栈看是 `model.py` 第 41 行的 `self.scale`：它在 `__init__` 里
用 `torch.tensor(...)` 直接赋值，没有注册成 buffer，所以 `model.to("cuda")` 不会移动它。

改成 `self.register_buffer("scale", torch.tensor(...))` 就会跟着模型一起移动。这是根据
堆栈和代码的推断，我没有运行；改完跑一步前向即可确认。
</example>
