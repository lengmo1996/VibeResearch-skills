# Research Skill routing

- Use [skills/registry.yaml](skills/registry.yaml) as the capability authority and
  each `SKILL.md` frontmatter as its discovery surface.
- When a Skill matches the task, select one primary Skill, at most two supporting
  Skills, and the narrowest sufficient mode. Handle unmatched tasks directly without
  forcing a Skill. User-provided evidence and the current request take precedence.
- Shared contracts under [skills/_shared](skills/_shared) govern evidence, local
  files, authorization, and operational boundaries.
- External services are optional user-configured capabilities. A mode that requires
  retrieval must stop retrieval-dependent claims when that capability is missing.
- Do not persist project memory, ingest a knowledge base, or send messages merely
  because a Skill is installed. Follow the user's actual authorization.
- Keep canonical names and Chinese UI metadata consistent. Run
  `python scripts/validate_public.py --test --build-check` after modifying Skills.
- Keep descriptions concise about the triggering scenario and principal output;
  no fixed sentence template is required. Add adjacent-task exclusions only when
  they prevent likely misrouting; put detailed procedures in the body or references.

The public profile has no personal research defaults, domain packages, private
governance history, scheduled task, mail bridge, or bundled MCP credentials.
