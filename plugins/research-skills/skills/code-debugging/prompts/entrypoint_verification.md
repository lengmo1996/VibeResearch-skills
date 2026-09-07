# Training and Inference Entrypoint Verification

Reduce an existing training, validation, prediction, or batch-inference path to the
smallest run that exercises the changed contract. Assert input schema, device/dtype,
shapes, loss/output schema, checkpoint behavior when relevant, exit status, and
regression-sensitive side effects.

This is verification work. Do not redesign or migrate the entry point.

