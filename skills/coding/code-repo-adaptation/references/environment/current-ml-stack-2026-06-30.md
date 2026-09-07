# Current ML Stack Snapshot (2026-06-30)

## Purpose
Use this file as the entry point for compatibility work in this environment. It
identifies the packages whose release notes, migration guides, and known breaking
changes inform `code-repo-adaptation` before modifying training, inference,
checkpoint, or dataset compatibility code.

## High-priority compatibility targets

| Area | Installed versions | Why knowledge injection is needed | Read next |
|---|---:|---|---|
| PyTorch core + domain libraries | `torch==2.10.0+cu126`, `torchvision==0.25.0+cu126`, `torchaudio==2.10.0+cu126` | Central runtime for tensor semantics, compilation, serialization, distributed training, AMP, CUDA wheels, and domain API compatibility. The environment is newer than the earlier fixed target `2.6`, so knowledge should cover both migrations *to 2.6* and deltas *from 2.6 to 2.10*. | `../torch/target-torch-2.10-cu126.md` |
| Lightning | `lightning==2.6.1`, `pytorch-lightning==2.6.1`, `torchmetrics==1.8.2`, `lightning-utilities==0.15.3` | Both namespace packages are installed. Knowledge should cover `pytorch_lightning` vs `lightning.pytorch`, Trainer argument changes, checkpointing, strategies, Fabric, TorchMetrics interactions, and the known unsafe 2.6.2/2.6.3 window. | `../lightning/target-lightning-2.6.1.md` |
| Hugging Face training/inference stack | `transformers==5.3.0`, `diffusers==0.37.0`, `datasets==4.7.0`, `accelerate==1.13.0`, `huggingface_hub==1.6.0`, `tokenizers==0.22.2`, `safetensors==0.7.0` | This is a modern HF stack with Transformers v5. Code written for Transformers v4, older Diffusers schedulers/pipelines, or older Accelerate device APIs may need targeted migrations. | `../huggingface/target-hf-stack-2026-06.md` |
| CUDA / fused attention / performance extensions | CUDA 12.6 wheel stack, `triton==3.6.0`, `flash_attn==2.8.3`, `xformers==0.0.35`, `nvidia-nccl-cu12==2.27.5` | Binary compatibility and optional acceleration paths are fragile. Knowledge should capture wheel CUDA version, driver constraints, fallback behavior, attention backend selection, compile interactions, and NCCL/distributed caveats. | `../cuda/cu126-extension-stack.md` |
| Numeric / data ecosystem | `numpy==2.4.1`, `pandas==3.0.1`, `scipy==1.17.1`, `pyarrow==23.0.1`, `pillow==12.0.0` | Many research repos pin old NumPy/Pandas/Pillow APIs. Inject migration notes for removed aliases, dtype behavior, IO changes, and dataset serialization. | `../migration-rules/python-data-ecosystem.yaml` |

## Injection priority

1. Inject PyTorch 2.6 through 2.10 release/migration knowledge first because it controls runtime behavior, serialization, `torch.compile`, AMP, distributed, and CUDA binary compatibility.
2. Inject Lightning 2.6.1 knowledge second because this environment contains both `lightning` and `pytorch-lightning` packages at the same version.
3. Inject Hugging Face stack knowledge third because `transformers==5.3.0` is a major-version environment and many repos still target v4.
4. Inject CUDA extension knowledge for any task that touches attention kernels, `torch.compile`, distributed training, or custom CUDA/C++ extensions.
5. Inject NumPy/Pandas/Pillow rules when adapting older repositories or dataset pipelines.

## Default compatibility workflow

```bash
python - <<'PY'
import torch
print('torch', torch.__version__)
print('cuda runtime', torch.version.cuda)
print('cuda available', torch.cuda.is_available())
try:
    import lightning, pytorch_lightning
    print('lightning', lightning.__version__)
    print('pytorch_lightning', pytorch_lightning.__version__)
except Exception as exc:
    print('lightning import issue:', repr(exc))
PY
```

Then search the target repository for high-risk API surfaces:

```bash
rg "torch\.load\(|torch\.save\(|torch\.compile|torch\.jit|torch\.cuda\.amp|torch\.amp|DistributedDataParallel|torch\.distributed|pytorch_lightning|lightning\.pytorch|Trainer\(|accelerate|diffusers|transformers|AutoTokenizer|AutoModel|from_pretrained|xformers|flash_attn"
```

## Source anchors used for this knowledge set

- PyTorch releases and 2.10 release blog: https://github.com/pytorch/pytorch/releases and https://pytorch.org/blog/pytorch-2-10-release-blog/
- PyTorch 2.6 release blog for the `torch.load(weights_only)` compatibility break: https://pytorch.org/blog/pytorch2-6/
- Lightning changelog and releases: https://lightning.ai/docs/pytorch/stable/generated/CHANGELOG.html and https://github.com/Lightning-AI/pytorch-lightning/releases
- Lightning PyPI release history / current latest context: https://pypi.org/project/pytorch-lightning/
- Hugging Face Transformers docs/releases/blog: https://huggingface.co/docs/transformers/en/index, https://github.com/huggingface/transformers/releases, https://huggingface.co/blog/transformers-v5
- Hugging Face Diffusers docs/releases: https://huggingface.co/docs/diffusers/en/index and https://github.com/huggingface/diffusers/releases
- NVIDIA CUDA 12.6 driver reference point: https://docs.nvidia.com/deeplearning/frameworks/pytorch-release-notes/rel-24-10.html
