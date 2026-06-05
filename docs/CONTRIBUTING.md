# Contributing and Agent Safety

RINGKAS follows a task-based workflow. Keep changes small, scoped, and traceable.

## Source Of Truth

Follow these docs in order:

1. `docs/RINGKAS_PROJECT_BRIEF.md`
2. `docs/RINGKAS_PRD.md`
3. `docs/RINGKAS_SRD.md`
4. `docs/RINGKAS_TECHNICAL_SPEC.md`
5. `docs/RINGKAS_TASKS.md`
6. `docs/RINGKAS_AGENTS.md`

If documents conflict, do not guess. Report the conflict to the supervisor.

## Workflow

- Work from an assigned Task ID.
- Read the task, dependencies, and relevant spec sections first.
- Change only the files allowed by that task.
- Keep architecture decisions aligned with the Technical Spec.
- Run available validation when relevant.

## Safety Rules

- Do not add out-of-scope features.
- Do not introduce OCR, Docling production parsing, or architecture changes without approval.
- Do not commit secrets or production `.env` files.
- Do not commit or push unless explicitly instructed.
- Preserve citation and evidence guardrails for answer generation.
- Keep Python worker internal only; ASP.NET Core remains the public backend.

## Reporting Completion

When a task is done, report:

- Task ID
- status
- files changed
- summary
- acceptance criteria checked
- tests/build run
- risks or follow-up
- blocked items

## Reporting Blockers

If work is blocked, stop and report the blocker clearly. Include:

- evidence
- attempted fix
- suggested options
- files affected
- decision needed
