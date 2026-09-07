# Training Pipeline Compatibility

Adapt an existing training/validation entry point only as required by the target
environment or framework. Check launcher semantics, hook lifecycle, optimizer/scheduler
ownership, precision, distributed behavior, logging interfaces, Dataset/DataLoader
contracts, and checkpoint/resume integration.

Do not create a generic CLI from scratch and do not execute smoke or acceptance tests.

