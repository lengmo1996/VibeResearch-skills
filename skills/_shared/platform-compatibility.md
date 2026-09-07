# Platform and External-Tool Compatibility

Apply this contract to every repository Skill and to standalone distributions.

## Capability classes

- **Instruction-only:** Complete the workflow from user-supplied material and platform-native tools. Do not assume a local shell, filesystem, or network service exists.
- **Optional MCP:** Check once whether the declared MCP capability is available. If unavailable, continue from user files, links, current context, or ordinary authoritative web sources when the task permits. State that the fallback path was used and do not retry an absent server repeatedly.
- **Required MCP:** Check before retrieval-dependent work. If unavailable, stop only the dependent claims, name the missing server, and point to [external-service setup](../../docs/external-services.md). Never substitute a similarly named tool or describe another source as MCP output.

The current library treats KnowledgeHub as optional at the Skill level. A selected mode can make it required when the user explicitly asks for private-library, historical, or citation-verification evidence. Supplied documents still support independent, source-bounded work.

## Platform rules

- **Codex local:** Local files, commands, and local/private MCP may be used only when present and authorized.
- **Codex Cloud:** Do not assume access to the user's machine, LAN, tailnet, credentials, or absolute paths. Require uploaded or repository-contained inputs and separately configured remote tools.
- **ChatGPT Web:** Workspace Skills and Plugins have separate lifecycle and permissions from local Codex Skills. Do not claim they synchronize automatically. Private MCP requires an approved supported connection such as Secure MCP Tunnel; loopback, LAN, and tailnet endpoints are not direct ChatGPT Web endpoints.
- **Public distribution:** Package no credentials, personal paths, private endpoints, user data, or internal-only evidence. Keep install-time configuration external to the archive.

## Skill-root command resolution

Before running a bundled script, resolve `<skill-root>` to the directory containing the
selected Skill's `SKILL.md`; do not assume the process working directory is the Skill
directory. Invoke bundled scripts as `<skill-root>/scripts/<script>` and quote the resolved
path when it contains spaces. Resolve Python from an explicitly configured interpreter or
the first working platform command (`py -3` on Windows, then `python3`, then `python`), and
smoke-test it with `--version`. Never invent an absolute interpreter or repository path.

## Side effects and stopping

Require explicit user authorization before writing, deleting, publishing, uploading, sending, changing credentials, or mutating external systems. Stop when required inputs or tools are unavailable, when the selected output contract is satisfied, or when proceeding would exceed the granted scope. Report the exact incomplete items without fabricating completion.
