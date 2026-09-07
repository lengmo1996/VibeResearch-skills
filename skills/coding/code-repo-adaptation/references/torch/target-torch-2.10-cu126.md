# PyTorch Target Knowledge: torch 2.10.0+cu126 / torchvision 0.25.0+cu126 / torchaudio 2.10.0+cu126

## Scope
Use this file when adapting code to the current environment:

- `torch==2.10.0+cu126`
- `torchvision==0.25.0+cu126`
- `torchaudio==2.10.0+cu126`
- CUDA wheel family: `cu126`
- `triton==3.6.0`

This file intentionally covers the target environment rather than every historical PyTorch release. For older source repositories, first infer the source version, then apply the migration rules below.

## Release-note ranges to inject

| Source repo era | Required knowledge to load |
|---|---|
| PyTorch 1.0-1.13 | Tensor constructor/device/dtype cleanup, `Variable` removal assumptions, old distributed launchers, old AMP/apex code, old torchvision transforms/model weights APIs, old checkpoint pickling assumptions. |
| PyTorch 2.0-2.5 | `torch.compile`/Dynamo caveats, `torch.export`, SDPA attention backend changes, AMP namespace migration, serialization hardening preparation. |
| PyTorch 2.6 | `torch.load` default `weights_only` behavior change; this is the most important compatibility rule for checkpoints from older repos. |
| PyTorch 2.7-2.10 | Compiler-stack, numerical code-debugging, performance, distributed/RL workflow, and CUDA wheel matrix deltas; check release notes before changing compile/distributed behavior. |

## High-risk compatibility rules

### 1. `torch.load` checkpoint compatibility

**Risk:** PyTorch 2.6 changed the default value of `weights_only` in `torch.load` as a security hardening measure. Older research repos often load arbitrary Python objects from checkpoints, which may now fail or require explicit trust decisions.

**Search:**

```bash
rg "torch\.load\("
```

**Migration policy:**

- For model weights from trusted local training runs, be explicit:

```python
state = torch.load(path, map_location="cpu", weights_only=False)
```

- For untrusted checkpoints, prefer safe loading and avoid arbitrary object deserialization:

```python
state_dict = torch.load(path, map_location="cpu", weights_only=True)
```

- For Lightning checkpoints, inspect whether the file contains trainer/module metadata beyond tensors before setting `weights_only=True`.

### 2. AMP namespace and precision handling

**Search:**

```bash
rg "torch\.cuda\.amp|from torch\.cuda\.amp|autocast\(|GradScaler"
```

**Preferred target style:**

```python
with torch.amp.autocast("cuda", enabled=use_amp):
    loss = model(batch)
```

Keep old code only if the project must remain compatible with older PyTorch. For Lightning tasks, prefer Lightning `precision` configuration over manual scaler code unless the training loop is custom.

### 3. `torch.compile` / Dynamo / graph capture

**Search:**

```bash
rg "torch\.compile|torch\._dynamo|torch\.jit|script\(|trace\("
```

**Policy:**

- Do not blindly wrap models in `torch.compile` during repo adaptation.
- If code uses dynamic Python control flow, custom autograd, nonstandard CUDA extensions, `flash_attn`, or `xformers`, validate eager mode first.
- Add a config flag such as `compile: false` by default for research reproducibility.

### 4. CUDA 12.6 wheel family

**Environment fact:** Installed PyTorch and domain wheels are `+cu126` while the package list contains NVIDIA CUDA 12.6 component wheels.

**Policy:**

- Do not mix PyTorch wheels from a different CUDA family unless rebuilding the whole environment.
- For custom extensions, rebuild against this environment instead of reusing old `.so` artifacts.
- Always log `torch.__version__`, `torch.version.cuda`, and `torch.cuda.get_device_name()` in reproducibility reports.

### 5. Distributed and launcher compatibility

**Search:**

```bash
rg "torch\.distributed|DistributedDataParallel|torchrun|launch\.py|LOCAL_RANK|RANK|WORLD_SIZE"
```

**Policy:**

- Prefer `torchrun` semantics over legacy `torch.distributed.launch`.
- Preserve explicit rank/device assignment.
- For Lightning projects, avoid mixing manual DDP setup with `Trainer(strategy=...)` unless intentionally using a custom loop.

### 6. torchvision model weights and transforms

**Search:**

```bash
rg "torchvision\.models|pretrained=True|weights=|transforms\."
```

**Policy:**

- Replace old `pretrained=True` patterns with explicit weights enums when adapting old repos.
- Validate preprocessing transforms against the selected weights.

## Validation commands

```bash
python - <<'PY'
import torch, torchvision, torchaudio
print(torch.__version__, torch.version.cuda)
print(torchvision.__version__)
print(torchaudio.__version__)
print('cuda available:', torch.cuda.is_available())
PY
```

```bash
python - <<'PY'
import torch, tempfile
path = tempfile.NamedTemporaryFile(suffix='.pt').name
torch.save({'x': torch.ones(1)}, path)
print(torch.load(path, map_location='cpu', weights_only=True))
PY
```

## Source anchors

- PyTorch release list: https://github.com/pytorch/pytorch/releases
- PyTorch 2.10 release blog: https://pytorch.org/blog/pytorch-2-10-release-blog/
- PyTorch 2.6 release blog: https://pytorch.org/blog/pytorch2-6/
