# CLAUDE.md

Continuity instructions for Claude Code sessions in this repository. This
file is deliberately minimal. Process detail lives in
[`docs/development-workflow.md`](docs/development-workflow.md); current
facts and open items live in [`docs/project-status.md`](docs/project-status.md);
stage-by-stage history lives in [`docs/work-log.md`](docs/work-log.md).
Open proposals recorded in those documents are context, not execution
instructions — they do not authorize a task on their own.

For any task that changes code or defined behavior: plan intended
behavior, architecture/interfaces, and edge cases first, and reach
agreement on that plan before any test is designed. The agreed tests then
express the requirement — implementation is made to satisfy them, never
the reverse (tests are not weakened, skipped, or changed to accommodate
what the code happens to do). Full sequence and the collaboration protocol
behind it: `docs/development-workflow.md` §1 and §3.

Before starting work:

- Read `docs/development-workflow.md` for the process, scope discipline,
  and review/commit/push gates that apply to the task at hand.
- Read the latest entries in `docs/work-log.md` and the current
  `docs/project-status.md` to pick up from where the last session actually
  left off, rather than relying on conversational recollection alone —
  recollection and repository state have already diverged once (see
  `docs/work-log.md`, WL-0002/WL-0003).

During and at the end of a task, within whatever file scope that task
actually authorizes:

- Log the events `docs/development-workflow.md` §5 defines, at each stage,
  not only at completion.
- Before reporting an authorized implementation task ready for final
  review, check whether `docs/project-status.md` or `README.md` need
  updating, including whether their existing description still matches the
  cumulative implementation state, and update them in the same review diff
  if so — using implemented facts and explicitly approved decisions only.
  Keep open questions explicitly open: adding a module does not establish
  that its architecture was approved.
- Report what documentation was updated, or why none was needed.
- If uncertain whether something warrants a documentation update, flag the
  uncertainty rather than silently skipping it.
- If a task is read-only, report any documentation gap and a proposed log
  entry in chat only — do not write files.
- If a needed documentation change falls outside the current task's
  authorized file scope, report it and request scope agreement rather than
  writing it anyway.

Preserve scope and every review/commit/push gate `docs/development-workflow.md`
describes. Writing permission for documentation files never implies
authorization to commit, push, or touch source, tests, CI, dependencies,
migrations, or Git configuration.
