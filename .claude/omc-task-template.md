# omo Task Delegation Template

Copy-paste this for each subagent delegation. Replace all `{...}` placeholders.

## Template

```text
TASK:
{One-sentence atomic goal. What is the agent doing?}

EXPECTED OUTCOME:
{Concrete deliverable. What file(s) does the agent produce, and what
contents? Include exact function signatures, class names, error codes
if known. A reviewer should be able to verify the deliverable matches
this description without re-reading the spec.}

REQUIRED TOOLS:
- {tool1}: {why}
- {tool2}: {why}
{Do NOT list tools the agent shouldn't use.}

MUST DO:
- {Exhaustive list of things to do, in order if sequential.}
- {Include: read these files first, run these commands, verify these
  conditions, commit with this format.}
- {"Actually write the code" — if a code-writing task, this MUST appear.}
- {"Run the test suite" — if verification needed.}
- {"Commit the changes" — if applicable.}

MUST NOT DO:
- {"Do not stop at the planning phase" — for code-writing tasks.}
- {"Do not modify {file/section}" — protected code.}
- {"Do not change {test/spec X} to make tests pass" — for impl tasks.}
- {"Do not add new dependencies" — usually true.}
- {"Do not commit without explicit user approval" — usually true.}

CONTEXT:
- Repo: /path/to/repo
- Spec file: {path} (read this FIRST to understand requirements)
- Test plan file: {path} (read this to understand test conventions)
- Interface file: {path} (read this to know the API shape)
- Existing patterns: {list 2-3 files that exemplify the expected style}
- Branch: {branch name}
- Tushare token: {env var name + how to load}

VERIFICATION:
{How the agent verifies success: run pytest, run script, check git diff, etc.}

REPORT BACK:
{What the agent should report when done: file paths, commit hash, test results, blockers.}
```

## Defaults

- `run_in_background=true` for tasks > 5 min expected runtime
- `model="sonnet"` for standard impl, `"opus"` for arch decisions
- Use `task_id` (resume) for follow-ups, not new task
- After delegation: continue with non-overlapping work, or end response
