# Lightning Target Knowledge: lightning 2.6.1 / pytorch-lightning 2.6.1

## Scope
Use this file when adapting Lightning code in the current environment:

- `lightning==2.6.1`
- `pytorch-lightning==2.6.1`
- `torchmetrics==1.8.2`
- `lightning-utilities==0.15.3`

Both `lightning` and `pytorch-lightning` are installed, so compatibility work must be explicit about import namespace and target package expectations.

## Release-note ranges to inject

| Source repo era | Required knowledge to load |
|---|---|
| PyTorch Lightning 1.x | Namespace migration, Trainer argument migration, accelerator/devices/strategy changes, checkpoint resume changes, callback/logger import paths, hook signature changes. |
| Lightning 2.0-2.5 | Fabric integration, strategy/precision behavior, checkpoint/consolidation behavior, Trainer API refinements. |
| Lightning 2.6.1 | Current stable target for this environment; include release notes and changelog entries up to 2.6.1. |
| Lightning 2.6.2/2.6.3 | Inject security knowledge: avoid these compromised PyPI versions when advising upgrades. |

## High-risk compatibility rules

### 1. Namespace choice

**Search:**

```bash
rg "pytorch_lightning|lightning\.pytorch|from lightning import"
```

**Target policy:**

- Prefer a single namespace within a repo.
- For new code targeting Lightning 2.x, prefer:

```python
import lightning.pytorch as pl
```

- If the repo is old and imports many `pytorch_lightning.*` paths, migrate consistently or keep legacy namespace only if tests confirm it works with installed `pytorch-lightning==2.6.1`.

### 2. Trainer arguments

**Search:**

```bash
rg "Trainer\(|gpus=|tpu_cores=|resume_from_checkpoint|accelerator=|devices=|strategy=|precision="
```

**Migration policy:**

- Prefer `accelerator`, `devices`, and `strategy` over old device-count arguments.
- Do not translate distributed behavior mechanically; preserve single-GPU, multi-GPU, node count, and precision semantics.
- For resume behavior, prefer explicit checkpoint path in `trainer.fit(..., ckpt_path=...)` when applicable.

### 3. Checkpoint compatibility

**Search:**

```bash
rg "load_from_checkpoint|save_checkpoint|ckpt_path|resume_from_checkpoint|ModelCheckpoint"
```

**Policy:**

- For pure PyTorch `torch.load` calls in Lightning code, also apply PyTorch 2.6+ `weights_only` rules.
- For Lightning `.ckpt` files, avoid assuming they are plain `state_dict`s. They often contain callbacks, hyperparameters, optimizer states, and trainer metadata.

### 4. Precision and AMP

**Search:**

```bash
rg "precision=|amp_backend|amp_level|GradScaler|autocast"
```

**Policy:**

- Prefer Trainer precision settings for standard Lightning loops.
- Avoid mixing manual scaler code with Lightning precision plugins unless the module uses a custom optimization loop.

### 5. Hooks and logging

**Search:**

```bash
rg "training_step|validation_step|test_step|predict_step|configure_optimizers|on_train_|on_validation_|self\.log"
```

**Policy:**

- Preserve return contracts for `training_step`, `validation_step`, and `configure_optimizers`.
- Validate logging flags (`on_step`, `on_epoch`, `sync_dist`) under distributed settings.
- Check TorchMetrics device placement and reset behavior.

### 6. Avoid unsafe Lightning versions

When suggesting upgrades, do not recommend Lightning or PyTorch Lightning `2.6.2` or `2.6.3` because public advisories identified those PyPI versions as compromised. Prefer the installed `2.6.1` or a later verified safe release after checking the current official package history.

## Validation commands

```bash
python - <<'PY'
import lightning, pytorch_lightning, torchmetrics
print('lightning', lightning.__version__)
print('pytorch_lightning', pytorch_lightning.__version__)
print('torchmetrics', torchmetrics.__version__)
PY
```

```bash
python - <<'PY'
import lightning.pytorch as pl
from lightning.pytorch import Trainer
print(pl.__version__, Trainer)
PY
```

## Source anchors

- Lightning changelog: https://lightning.ai/docs/pytorch/stable/generated/CHANGELOG.html
- Lightning GitHub releases: https://github.com/Lightning-AI/pytorch-lightning/releases
- PyPI release history: https://pypi.org/project/pytorch-lightning/
