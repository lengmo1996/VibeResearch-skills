# Hugging Face Target Knowledge: Transformers 5.3 / Diffusers 0.37 / Accelerate 1.13

## Scope
Use this file when adapting code that imports or configures:

- `transformers==5.3.0`
- `diffusers==0.37.0`
- `datasets==4.7.0`
- `accelerate==1.13.0`
- `huggingface_hub==1.6.0`
- `tokenizers==0.22.2`
- `safetensors==0.7.0`
- `timm==1.0.25`

## Knowledge to inject

| Package | Inject these topics |
|---|---|
| Transformers 5.x | v4-to-v5 breaking changes, tokenizer backend behavior, generation config changes, `Auto*` loading behavior, cache format, PEFT/quantization interactions, attention implementation flags, dynamic weight loading. |
| Diffusers 0.37 | Pipeline/component loading, scheduler config compatibility, `from_pretrained` variants, memory/offload APIs, `torch.compile` compatibility, attention processor/xFormers/FlashAttention switches. |
| Accelerate 1.13 | device map semantics, mixed precision, FSDP/DeepSpeed config shape, launcher config, distributed state handling. |
| Datasets 4.7 + PyArrow 23 | dataset serialization, streaming, multiprocessing map behavior, Arrow schema/dtype compatibility. |
| huggingface_hub 1.6 | auth/token API, cache layout, Xet integration via `hf-xet`, snapshot/download behavior. |

## High-risk compatibility rules

### 1. Transformers v4 code in v5 environment

**Search:**

```bash
rg "transformers|AutoTokenizer|AutoModel|AutoConfig|GenerationConfig|Trainer\(|TrainingArguments|pipeline\(|from_pretrained"
```

**Policy:**

- Do not assume v4 behavior. Check v5 release notes for changed defaults before patching tokenizer/model/generation code.
- Be explicit about `trust_remote_code`, dtype, device map, attention implementation, and revision when loading models.
- Prefer `safetensors` when available.

### 2. Diffusers scheduler and pipeline compatibility

**Search:**

```bash
rg "DiffusionPipeline|StableDiffusion|UNet|AutoencoderKL|Scheduler|from_pretrained|enable_xformers|enable_model_cpu_offload|enable_sequential_cpu_offload"
```

**Policy:**

- Preserve scheduler config when replacing pipelines.
- Do not enable xFormers or FlashAttention unconditionally; check installed versions and fallback paths.
- When adapting old code, validate generated tensor shapes, dtype, and device after pipeline construction.

### 3. Accelerate / distributed overlap with Lightning

**Search:**

```bash
rg "Accelerator\(|accelerate|device_map|dispatch_model|prepare\(|DeepSpeed|FSDP"
```

**Policy:**

- Avoid combining Lightning `Trainer` distributed orchestration with Accelerate orchestration unless the project intentionally separates components.
- If both are present, identify the owner of device placement, mixed precision, gradient accumulation, and checkpointing.

### 4. Hub cache and downloads

**Search:**

```bash
rg "huggingface_hub|hf_hub_download|snapshot_download|HUGGINGFACE_HUB_CACHE|HF_HOME|HF_TOKEN|use_auth_token|token="
```

**Policy:**

- Prefer explicit `token=` over deprecated auth argument names when modernizing.
- Avoid hardcoding cache paths in reusable code.
- Account for `hf-xet` acceleration and corporate/offline environments.

## Validation commands

```bash
python - <<'PY'
import transformers, diffusers, datasets, accelerate, huggingface_hub, tokenizers, safetensors
print('transformers', transformers.__version__)
print('diffusers', diffusers.__version__)
print('datasets', datasets.__version__)
print('accelerate', accelerate.__version__)
print('huggingface_hub', huggingface_hub.__version__)
print('tokenizers', tokenizers.__version__)
print('safetensors', safetensors.__version__)
PY
```

## Source anchors

- Transformers docs: https://huggingface.co/docs/transformers/en/index
- Transformers releases: https://github.com/huggingface/transformers/releases
- Transformers v5 blog: https://huggingface.co/blog/transformers-v5
- Diffusers docs: https://huggingface.co/docs/diffusers/en/index
- Diffusers releases: https://github.com/huggingface/diffusers/releases
