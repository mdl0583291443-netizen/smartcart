# Development Workflow

The agreed process for how work on this repository is selected, reviewed,
and landed. This document describes process; current facts and open
questions live in [`docs/project-status.md`](project-status.md); the
stage-by-stage history of applying this process lives in
[`docs/work-log.md`](work-log.md).

This document is itself a documentation-only artifact and its own creation
did not require the RED/GREEN sequence described in §3 below — that
sequence applies to implementation tasks, not to writing process
documentation.

## 1. Collaboration protocol

- **The owner has final authority** over task selection, scope, and any
  disputed decision.
- **GPT acts as team lead:** proposes the task and approach, explains its
  position and reasoning, and prepares the handoff message for whichever
  agent is meant to act on it next.
- **Claude Chat independently reviews and challenges GPT's position.**
  Agreement is expected to come from reasoning and evidence, not automatic
  acceptance of what GPT proposed.
- **GPT compares both positions.** Task selection, scope, planning, and
  stage transitions all require agreement between GPT and Claude Chat.
  Unresolved substantive disagreement goes to the owner for a decision.
- **Claude Code executes only the authorized stage and scope** that this
  agreement has actually produced — not what a task description might
  imply, and not whatever would be reasonable to also do while in the area
  (see §2).
- **Decisions reached in a GPT/Claude Chat conversation must be explicitly
  relayed to Claude Code** in the instruction it receives. Claude Code must
  never assume it has seen, or has access to, that conversation — only what
  is explicitly relayed in its instruction, plus this repository's own
  committed documentation, is treated as known to it.
- Instructions received, decisions made, completed logical changes, actual
  test/check results, review findings, and stopping points are documented
  at each stage (see §5).
- **Commit and push remain separately approval-gated** (see §4),
  independent of every other approval in this protocol.
- When GPT hands off a stage, it provides **one consolidated handoff
  message** and clearly identifies which agent — Claude Chat or Claude
  Code — that message is intended for.

## 2. Scope discipline

- Claude Code executes only the authorized stage and scope for a given
  task. Encountering a related but unauthorized change while working (a
  stale doc, a missing test, a tempting refactor) is reported, not silently
  done.
- A scope change — including one that looks like a small extension —
  returns to the agreement step (§1) rather than being decided
  unilaterally mid-task.
- If a documentation update that this workflow would otherwise require
  falls outside a task's currently authorized file scope, that is reported
  as a gap and scope agreement is requested for it — the update is not
  made anyway, and it is not silently skipped either.

## 3. Development sequence

For any task that changes code or defined behavior (not a documentation-only
task):

1. Agree on the task/topic and its scope.
2. Plan intended behavior, architecture/interfaces, and edge cases, and
   reach agreement on that plan **before** designing any test.
3. From the agreed plan, define and get approval for the test matrix and
   acceptance criteria.
4. Write tests before implementation. They must demonstrate a meaningful
   behavioral RED — failing for the right reason against the agreed
   criteria — then stop for independent review.
5. Implement only after that review's approval.
6. The implementation must satisfy all required tests, including
   applicable regression tests. Code is made to pass the agreed tests; the
   agreed tests are not adjusted to match whatever the code happens to do.
7. Review the diff and the actual test evidence — not only an
   implementation summary — before approving completion.

**Tests express the agreed requirements.** Do not weaken an assertion,
delete or skip a failing test, or change an expected result merely to make
an implementation pass. If a test is demonstrably wrong, or a requirement
genuinely needs revision, that is handled explicitly, never unilaterally:
present the evidence that it is wrong or needs revision, obtain explicit
agreement to change it, and record both the reason and the approval in
`docs/work-log.md`.

A documentation-only task does not require inventing a RED/GREEN pair to
satisfy this section — this section applies when there is behavior to
test.

## 4. Commit and push

Two gates, not three — staging is not an independently gated step:

- **Commit authorization**, given after diff review, covers both staging
  the approved files and committing them; the same authorization does
  both, and only files within the agreed/authorized scope are ever staged
  under it.
- **Push requires a separate, explicit authorization**, given after
  commit.
- Task closure includes commit and push, but only once their respective
  approvals have actually been given — reaching the end of a task's work
  does not itself imply either approval.

## 5. Per-stage documentation obligations

At each stage of a task — not only at completion — within whatever
documentation file scope that task actually authorizes:

- Log the stage in `docs/work-log.md`: new or revised instructions
  received; decisions and their approval/rejection and source; scope
  changes; completed logical changes and the files they touched; the
  actual check/test commands run and their actual results; review
  findings, disagreements, and failures; the stopping point, next action,
  and what approval is still needed.
- Before reporting an authorized implementation task as ready for final
  review, check whether `docs/project-status.md` or `README.md` needs
  updating — including whether their existing description still matches
  the cumulative implementation state — and update them in the same review
  diff if so, within the authorized file scope, using implemented facts
  and explicitly approved decisions only. Keep open questions explicitly
  open: adding a module does not establish that its architecture was
  approved, and an existing open-question note is not closed just because
  related work occurred — closing it requires an explicit approved
  decision.
- In the completion report, state which documentation was updated, or why
  none was needed. If uncertain whether a change warrants a status update,
  flag that uncertainty rather than silently skipping it.
- A **read-only** task that reveals a documentation gap reports it (with a
  proposed log entry, in chat) without editing any file — read-only means
  read-only.
- Do not log every keystroke or restate the same fact across entries; log
  what changed, decided, or was found at each stage.
- Never record a check as passed (or failed) unless it was actually run in
  that stage.

## 6. Read-only tasks

When a task authorizes no documentation writes at all, documentation gaps
found during it are reported in chat, along with a proposed log entry text
— nothing is written to any file. A future task may explicitly authorize
code inspection plus writes to specified documentation files; that
authorization is scoped to documentation and never extends to code
changes, commit, or push unless separately and explicitly granted.

## 7. Interruption recovery

If a prior session's logging may have been interrupted or left incomplete,
the first step on resumption is to inspect the actual last `docs/work-log.md`
entry and the actual working tree — not to assume the previous session's
logging succeeded, and not to promise a perfect reconstruction of what an
abrupt interruption may have lost. Any uncertainty about whether a record
is complete is reported explicitly, in the affected work-log entry or a
new one, rather than smoothed over.

## 8. Git save-state discipline

- Commit or push is recorded as successful only after it has actually been
  confirmed executed — not in anticipation of running it.
- A commit's own hash is never embedded inside that same commit's content;
  a work-log entry may reference a commit's hash only after that commit
  exists.
- An entry describing a completed commit/push may still be sitting only
  locally (not yet committed itself) pending its own authorized checkpoint
  — this is disclosed explicitly in that entry rather than implied.
- A new commit is never created solely to record a preceding commit in the
  log; the log entry documenting a commit can itself land in the next
  natural commit rather than forcing a recursive one.
- Local files, committed content, and confirmed-pushed content are three
  distinct states and are described as such — "written" does not mean
  "committed," and "committed" does not mean "pushed."
