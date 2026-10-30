# Internship Radar — Codex guidance

Prefer Serena for symbol discovery, references, dependency navigation, and targeted reads. Avoid full-repository scans and large-file reads when symbol-level inspection answers the question.

## Multi-Agent Strategy

Use subagents only when they materially improve speed, context isolation, or quality. Route discovery/verification to Scout; metadata and normalization to Data; targeted checks to Test; normal implementation to Code; difficult bugs to Debug; architecture to Architect; and independent final review to Reviewer. Prefer Luna-class agents for repetitive/read-heavy work, Terra for normal implementation/debugging, and escalate to Astra only for architecture or unresolved high-complexity work. The project Codex configuration caps concurrent subagents at three.

For parallel work, keep research tasks independent and read-only. Then proceed sequentially through implementation, tests, and review. Do not have multiple write-capable agents edit the same files concurrently. Preserve candidate isolation and existing state in all work.
