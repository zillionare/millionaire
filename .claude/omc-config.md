# omo (oh-my-claudecode) Configuration Notes

## Default behavior for long tasks (2026-06-18 added)

When delegating implementation/development tasks to subagents, use:

1. **`run_in_background=true`** for tasks expected to take > 5 minutes.
   - The sync 30-min window is for total session, not per-task.
   - Background tasks notify via `<system-reminder>` when done.
   - Do NOT poll with `background_output` before notification.

2. **Full 6-section prompt** for every delegation:
   - TASK: atomic, specific goal
   - EXPECTED_OUTCOME: concrete deliverables + success criteria
   - REQUIRED_TOOLS: explicit whitelist (prevents sprawl)
   - MUST DO: exhaustive requirements — nothing implicit
   - MUST NOT DO: forbidden actions — anticipate rogue behavior
   - CONTEXT: file paths, patterns, constraints

3. **Pair coding pattern** (validated 2026-06-17):
   - Test agent: `run_in_background=true`, writes test code based on spec
   - Impl agent: `run_in_background=true`, writes impl based on spec
   - Both run in parallel, no shared context
   - Main agent does static review + integration

4. **Agent selection** for v0.2-001:
   - Implementation: `oh-my-claudecode:executor` (sonnet)
   - Test writing: `oh-my-claudecode:test-engineer` (sonnet)
   - Code review: `oh-my-claudecode:code-reviewer` (opus)
   - Long debug: `oh-my-claudecode:debugger` (sonnet)

## Known issue: 2026-06-17 dev agent

The impl agent bg_bc6c54e5 ran 12 minutes writing only a plan, no code.
Root cause: insufficient MUST DO section (didn't say "actually write files").
Fix: explicit "MUST DO: write the code, run the tests, commit the changes" +
     "MUST NOT DO: do not stop at plan".

This file is informational. The rules above are passed to subagents in
their prompt directly; this is the reference for what to include.
