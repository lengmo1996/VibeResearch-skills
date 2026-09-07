# CUDA 12.6 Extension Stack Knowledge

## Scope
Use this file when code touches CUDA extensions, fused attention, Triton kernels, distributed training, or performance features.

Installed packages include:

- `torch==2.10.0+cu126`
- NVIDIA CUDA 12.6 component wheels, including runtime, nvrtc, cupti, cuDNN 9.10, cuBLAS 12.6, cuSPARSE, cuSOLVER, NCCL 2.27.5, NVTX
- `triton==3.6.0`
- `flash_attn==2.8.3`
- `xformers==0.0.35`
- `ninja==1.13.0`

## Knowledge to inject

1. CUDA wheel matrix compatibility for PyTorch 2.10 `cu126`.
2. Minimum NVIDIA driver requirements for CUDA 12.6 class environments.
3. FlashAttention 2.8.x build/runtime constraints.
4. xFormers 0.0.35 attention backend constraints.
5. Triton 3.6 compatibility with `torch.compile` and custom kernels.
6. NCCL 2.27 distributed caveats and environment variables.

## High-risk rules

### 1. Never reuse stale extension artifacts

**Search:**

```bash
rg "setup\.py|CUDAExtension|cpp_extension|load_inline|flash_attn|xformers|triton\.jit"
```

**Policy:**

- Rebuild custom CUDA/C++ extensions in the active environment.
- Remove stale `build/`, `*.so`, and cached extension artifacts only when safe and scoped.
- Record compiler, CUDA, PyTorch, and GPU details in experiment logs.

### 2. Attention backend must be optional

**Search:**

```bash
rg "flash_attn|xformers|scaled_dot_product_attention|enable_xformers_memory_efficient_attention|attn_implementation"
```

**Policy:**

- Guard optional imports.
- Provide a PyTorch SDPA/eager fallback.
- Do not silently change numerical behavior without validation.

### 3. CUDA family consistency

**Policy:**

- Keep torch/torchvision/torchaudio CUDA suffixes aligned.
- Avoid installing `cu128`/`cu130` domain wheels into this `cu126` environment unless the entire stack is migrated.
- For deployment, verify host driver supports the CUDA runtime used by the wheel stack.

## Validation commands

```bash
python - <<'PY'
import torch
print('torch', torch.__version__)
print('torch cuda', torch.version.cuda)
print('cuda available', torch.cuda.is_available())
if torch.cuda.is_available():
    print('gpu', torch.cuda.get_device_name(0))
PY
```

```bash
python - <<'PY'
mods = ['triton', 'flash_attn', 'xformers']
for name in mods:
    try:
        mod = __import__(name)
        print(name, getattr(mod, '__version__', 'unknown'))
    except Exception as exc:
        print(name, 'IMPORT_ERROR', repr(exc))
PY
```

## Source anchors

- PyTorch releases: https://github.com/pytorch/pytorch/releases
- PyTorch 2.10 release blog: https://pytorch.org/blog/pytorch-2-10-release-blog/
- NVIDIA CUDA 12.6 reference: https://docs.nvidia.com/deeplearning/frameworks/pytorch-release-notes/rel-24-10.html
