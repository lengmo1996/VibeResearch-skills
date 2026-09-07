# Inference Compatibility

Adapt an existing predict/evaluate/export/batch-inference entry point to the target
framework, device, data layout, or serialization contract. Preserve preprocessing,
batch semantics, output ordering, and postprocessing unless the target contract says
otherwise.

Document expected outputs for downstream verification; do not claim they passed.

