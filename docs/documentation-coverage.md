# Documentation Coverage and Evidence Matrix

**Purpose:** an inventory of what a new session needs before authoring the
full handover package (`start-here.md`, `product-vision.md`, `roadmap.md`,
`architecture.md`, `testing-map.md`, `database-map.md`,
`research-and-open-design.md`, `environment.md`, `glossary.md`,
`constraints.md`), where the supporting evidence for each topic already
exists, and what is missing. This document is itself an inventory, not the
handover package — none of the planned domain documents are authored here.

**Inspected HEAD:** `6db56ea1f7acbbf7dd2282717be8dcbdc89a391a` (branch
`main`), confirmed by `git -c safe.directory='*' --no-optional-locks
rev-parse HEAD` immediately before this round's edits — unchanged
throughout every prior documentation stage in `docs/work-log.md`.

**Relevant uncommitted state at inspection time** (`git -c
safe.directory='*' --no-optional-locks status --porcelain=v1`): `README.md`
modified-but-uncommitted; `CLAUDE.md`, `docs/development-workflow.md`,
`docs/project-status.md`, `docs/work-log.md`, and this file untracked
(created earlier this session, never committed). A number of pre-existing
untracked local scraper artifacts (`after_login*.html`, `cookies_*.txt`,
`dir_*.json`, `jar_*.txt`, `filepage.html`, `hcohen_root.html`) are
unrelated to documentation and unchanged. **Content approval (§1.1) does
not mean any of this is committed or pushed** — commit and push remain
separate, ungranted gates per `docs/development-workflow.md` §4 and
`docs/project-status.md` §4.

**A note on CLAUDE.md's provenance label:** this session's harness
describes `CLAUDE.md` to itself as "project instructions, checked into the
codebase." That label is the harness's generic description of any
`CLAUDE.md` file it finds on disk, not a git-verified claim — actual `git
status` shows `CLAUDE.md` as untracked (`??`), consistent with
`docs/work-log.md` WL-0004 ("`CLAUDE.md` — created" this session, never
committed). A new session should verify this kind of harness-label
against actual `git status` rather than trust the label; recorded as a gap
in §5 below.

---

## 1. Approval state and source availability

### 1.1 Approval state

**The five-file documentation checkpoint, as reviewed through WL-0021,
received content approval from GPT and Claude Chat, relayed through the
owner. Coverage-matrix work and subsequent edits beginning with WL-0022
require their own review. Commit and push remain separately
unauthorized.**

Restated in full:

- **Content approval covers the checkpoint's content as it stood through
  `docs/work-log.md` WL-0021** — i.e., every correction round up to and
  including the WL-0021 wording adjustments. This is **[relayed]**:
  reported to this session via Claude Chat's own direct check of its
  earlier closing verdict, confirmed this round (see `docs/work-log.md`
  WL-0026) — not independently re-verified by this session against
  anything outside what was relayed.
- **Owner commit authorization remains pending** — separate from content
  approval, per `docs/development-workflow.md` §4.
- **Owner push authorization remains separately pending** — separate
  again from commit authorization, per the same section.
- **This coverage matrix (WL-0022 onward), and every edit to it since —
  including this round's — require their own review.** Content approval
  through WL-0021 does not extend to WL-0022 or later.
- **The testing/database-map task has not started.** This is **not**
  because the earlier checkpoint's content approval was withheld — it was
  given, through WL-0021. Rather, task sequencing follows the agreed plan
  recorded in §7 below (review this matrix → prepare a small
  `start-here.md` → build technical maps in separately reviewed stages),
  and that sequence has not yet reached the maps stage.

**Correction to a prior mischaracterization in this document:** an
earlier version of this section stated that every correction round since
WL-0007 "still requires its own review" and had "not itself been reported
back as reviewed or approved." That was inaccurate for WL-0007 through
WL-0021 — those rounds are covered by the content approval above. The
accurate boundary is the one stated at the top of this subsection:
approved through WL-0021; not yet reviewed from WL-0022 onward. **This
correction does not itself approve the current coverage matrix or any
later edit** — that review remains pending, per the fourth bullet above.

### 1.2 Source availability

**Available to GPT** (reported; held outside Claude Code's current
context):

- Supplied product/project-history summaries.
- The improvement PDF (the "27-point improvement PDF").
- Product Identity/external-data review messages and subsequent
  responses.
- Explicit owner statements made in the GPT/Claude Chat conversation.

**Still missing or unlocated, even once the above is transferred:**

- The original approved roadmap text (a summary of the roadmap is not the
  roadmap itself).
- The original Product Identity requirements and their revisions.
- The original recon reports, datasets/examples, and execution evidence
  behind the Product Identity/external-data review.
- Precise external citations (e.g., specific GS1/Open Food Facts
  references — see row 10) not already present in the available
  material.

**This distinction matters and is kept explicit:** transferring GPT's
summaries or review messages is **not guaranteed** to supply every
original requirement, recon report, or dataset — a summary remains a
summary. This document does not assume the underlying originals will
necessarily surface once the summaries do, and does not treat a summary
as a substitute for the original approval/requirements record it
describes. See §6 for the transfer request built from this distinction.

**Update — Product Identity Requirements Freeze relayed (narrows, does
not close, the second bullet above):** a Product Identity Requirements
Freeze and its supporting evidence/recon pass are now recorded as
**[relayed]** owner-authorized reviewed state in `docs/work-log.md`
WL-0028/WL-0029 and `docs/project-status.md` §3. This is the Freeze's
*conclusions* — not the original requirements discussion, the original
recon reports/datasets, full GPT/Claude Chat review transcripts, or
original external-source evidence/logs (e.g. the underlying GS1/Open Food
Facts material), none of which has been transferred to this session. The
second and third "still missing" bullets above are accordingly narrowed
in scope (the freeze's conclusions are no longer missing) but **not
closed** (the originals behind them remain missing/unlocated).

---

## 2. Mandatory reading order

A new session (or a new reviewer) must read, in this order, before relying
on anything else in this repository:

1. **`start-here.md`** — once it exists (currently planned only; see the
   matrix row below and the agreed/proposed authoring sequence in §7).
2. **`docs/development-workflow.md`** and any other applicable agent
   instructions. As of this inspection, the only agent-instructions file
   in this repository is `CLAUDE.md` at the repository root — a
   directory-by-directory search (`.claude/**`) found no additional
   scoped agent-instructions files. Tiering by document does not exempt
   reading whichever of these actually applies to the task at hand.
3. **`docs/project-status.md`** — current facts, open questions, and the
   stopping point.
4. **The latest handover/review entries `docs/project-status.md`
   references** — currently the tail of `docs/work-log.md` (through the
   latest entry recorded in this round; see §3 row 11 and the
   completeness checklist in §5).

Task-specific documents (the testing map, database map, research record,
etc.) are read afterward, as the task requires — but the four items above
are read regardless of task, because they establish what is actually known
versus assumed before any task-specific document is trusted.

---

## 3. Coverage matrix

Evidence-type key used in the "Approval/verification status" column:
**[source]** = this session (or an earlier stage of it) read the cited
code/config directly; **[exec]** = an actual command was run and its
result recorded in `docs/work-log.md`; **[approved]** = an explicit,
recorded owner/GPT+Claude Chat decision; **[relayed]** = reported to this
session as having happened elsewhere, not independently witnessed;
**[hypothesis]** = a stated possibility, explicitly not confirmed;
**[unknown]** = not established either way by anything available to this
session. A committed file is not, by itself, in this key — commit status
is tracked separately (see the inspected-state note at the top of this
document) and never substitutes for one of these.

| # | Topic | Owning document/section (planned unless noted existing) | Available evidence | Approval/verification status | Missing information | Update trigger |
|---|---|---|---|---|---|---|
| 1 | Start-here / handover checklist | **`start-here.md`** (planned; does not exist — `docs/*.md` inspected, only `development-workflow.md`, `project-status.md`, `work-log.md`, and this file present) | The mandatory-reading order in §2 above, and the completeness checklist in §5, are the material a `start-here.md` would need to summarize. | Not yet authored. Per §7, it is next in the agreed sequence after this matrix is reviewed/approved. | The document itself; agreement on its exact contents/length. | Any change to the mandatory reading order (§2) or to which documents exist. |
| 2 | Product vision, intended UX, feature/requirement statuses | **`product-vision.md`** (planned; does not exist) | `README.md` lines 5-10 give one paragraph of product goal (household tradeoff between price, missing items, and travel time). `docs/project-status.md` §2 records the owner-confirmed Android/iOS + WhatsApp direction **[relayed]**, explicitly "not implemented code." No feature-by-feature requirement list or UX flow exists anywhere in the repository (confirmed by `docs/*.md` and root `*.md` glob — no wireframe/flow file). Product-vision/feature-landscape summaries and the 27-point improvement PDF are reported to exist outside this session (§1.2) and have not been transferred. | The one-paragraph goal and the platform direction are **[relayed]**/committed-intent facts, not independently verified against any external requirements document (none is present in this repository to check against, and the reported summaries/PDF have not been transferred here). No feature has a recorded "approved requirement" vs. "open idea" status beyond what ADRs happen to cover. | A structured requirement/feature list with statuses (approved / open / rejected); any UX flow or wireframe (`docs/project-status.md` §1 confirms none exists); the reported product-vision summaries and 27-point PDF content (§6). | Any owner-confirmed product decision; any ADR that newly scopes a feature; transfer of the materials in §1.2/§6. |
| 3 | Roadmap, dependencies, sequencing | **`roadmap.md`** (planned; does not exist) | ADR list (`docs/adr/0001`–`0011`, all `Status: Accepted` per `docs/project-status.md` §1) is the closest thing in this repository to a sequence, but ADRs record accepted architectural decisions, not a forward roadmap with dependencies. `docs/project-status.md` §4 "Next proposed action: none is authorized yet" remains true of this repository's own documents. | **The owner reports an existing roadmap; its original approved text and latest sequencing have not yet been transferred or reconciled in this session.** This is **[relayed]** — the roadmap's existence is reported, not independently verified from anything in this repository, and its content has not been reviewed here. This corrects the prior wording ("No roadmap has been agreed"), which overstated the negative: a roadmap's absence from this repository's own files is not the same as a roadmap's absence from the project. | The roadmap's actual approved text and current sequencing (§6); whether/how it addresses Product Identity, which is relayed as resumed (`docs/project-status.md` §3; `docs/work-log.md` WL-0028/WL-0029) rather than paused as this row previously described it. | Any GPT/Claude Chat-agreed sequencing decision explicitly relayed to this session, or transfer of the reported roadmap's text (§6). |
| 4 | Implemented architecture vs. approved-but-unbuilt design | **`architecture.md`** (planned; does not exist) | `docs/project-status.md` §1 tables (implemented/tested, integrated-not-orchestrated, experimental spikes, not-implemented) are **[source]**-cited against `src/smartcart/**` (confirmed present this stage: `collectors/{shufersal,rami_levy}`, `normalize/{contract,shufersal,rami_levy,promotion,promotion_contract}.py`, `integration/occurrence_activation.py`, `db_spike/*`, `durability_spike/*`) and ADRs 0002/0004/0008/0009/0010/0011. | Implemented-and-tested components are **[source]**-verified. The distinction the task asks for — implemented architecture **separately labeled from** approved-but-unbuilt design — was checked and **no item fits "approved-but-unbuilt design"** cleanly: ADR 0011 §1 (partial/item-level activation acceptance) and §2 (legacy backfill) are recorded as **deliberately deferred decisions**, not approved designs awaiting implementation — a different category than "approved, not yet built." This distinction is not yet stated anywhere as such. | An explicit `architecture.md` that separates (a) implemented and tested, (b) integrated but not orchestrated, (c) experimental spikes, (d) deliberately deferred by ADR, and (e) any true "approved but not yet built" item — category (e) currently appears to be empty, but this was not exhaustively re-verified against every ADR's full text (only ADR 0003/0005 were read in full this round, for row 10; the others rely on already-recorded summaries in `docs/project-status.md`). | Any new module under `src/smartcart`; any new or amended ADR. |
| 5 | Testing map: assertions, fixtures, execution conditions, coverage limits | **`testing-map.md`** (planned; does not exist) | `docs/work-log.md` WL-0009 (direct-import evidence: no test file imports both a real `normalize.*` function and `smartcart.integration.occurrence_activation`), WL-0016 (open question: an indirect helper/fixture path is not ruled out), WL-0019/WL-0021 (evidence-scoped wording now in `README.md` and `docs/project-status.md`). Test inventory: `tests/collectors/{shufersal,rami_levy}/`, `tests/normalize/`, `tests/db_spike/`, `tests/durability_spike/` (full listing obtained via `Glob`, not opened file-by-file). | The prior "testing map" task (`SMARTCART — TESTING AND DATABASE MAPS`) has **not started**. **Corrected:** this is not because the five-file checkpoint's content approval was withheld — that approval was given (§1.1). Rather, task sequencing follows the agreed plan in §7 (review this matrix → `start-here.md` → technical maps), and that sequence has not yet reached the maps stage. Owner commit/push authorization for the checkpoint documents remain pending independently of this sequencing question (§1.1). | The actual `testing-map.md` content (per-test assertions, fixture provenance, real-vs-mocked boundaries, skip/opt-in markers) — explicitly **not** re-investigated this round, per this task's own instruction not to re-investigate the full test-path question now. The helper/fixture question from WL-0016 remains open. | Any test added/deleted/changed in ways affecting mapped behavior, coverage, or execution conditions (rule to carry into `docs/development-workflow.md` once the map exists — see §4 below); any resolution of the WL-0016 open question; reaching the maps stage of the §7 sequence. |
| 6 | Database map: schema, migrations, persistence behavior | **`database-map.md`** (planned; does not exist) | Migrations present: `src/smartcart/db_spike/migrations/0001_initial_schema.sql` through `0004_normalized_current_state_facts.sql` (four files, confirmed via `Glob`, not opened line-by-line beyond what `docs/project-status.md` §3 already cites: `chain_product` PK `(chain_id, item_code_raw)` at lines 140-143 of `0001_initial_schema.sql`; `store_product_current_state`/`price_history` at lines 153-188). ADRs 0009 (DB spike scope), 0010 (durability spike scope), 0011 (seam failure handling, legacy backfill, provenance). | **Corrected, same as row 5:** this task is separate from, and does not substitute for, the dedicated database-map task; its non-start reflects the §7 sequencing, not withheld content approval (§1.1). | Full migration-by-migration schema map; write/activation flow and transaction ownership; ordering/concurrency/retry/idempotency behavior — `docs/project-status.md` explicitly notes concurrency/crash-recovery tests exist (`tests/db_spike/test_activation_concurrency.py`, `tests/durability_spike/test_crash_durability.py`) but **"this document does not claim these tests currently pass; no test run is recorded for this checkpoint."** That remains true — no execution evidence was produced here. | Any new/changed migration; any change to `db_spike/{activation,catalog,content,occurrence}` or `integration/occurrence_activation.py`; reaching the maps stage of the §7 sequence. |
| 7 | Research/open design — Product Identity, external data | **`research-and-open-design.md`** (planned; does not exist) | `docs/project-status.md` §3 separates: what is implemented (a raw `(chain_id, item_code_raw)` tracking key, `store`/`store_source_alias` for Store identity, `smartcart_product`/`create_product()`, `chain_product_current_assignment`/`assign_chain_product()`/`product_assignment()`, `set_product_display_name()`, and — as of `docs/work-log.md` WL-0035 — `chain_product_assignment_history`/`correct_chain_product_assignment()`, all **[source]**-verified against repository source), the Requirements Freeze conclusions and evidence/recon pass (**[relayed]**, `docs/work-log.md` WL-0028), the Slice A (Batch A/B/C) and Slice B execution state (mixed provenance, `docs/work-log.md` WL-0029 through WL-0035), and a list of open questions (within-retailer continuity, same-retailer many→one — explicitly **UNKNOWN**, identifier-change semantics per ADR 0011 §6, and the concurrency-semantics-for-assignment-writes limitation recorded as a future concern in WL-0031, unaffected by Slice B). **Status is relayed as resumed, with Slice A (Batch A, Batch B, Batch C) and Slice B both COMPLETE** (`docs/project-status.md` §3). Slice B (`docs/work-log.md` WL-0034/WL-0035): the architecture freeze was approved first; an exact 9-item test contract (plus two migration-test modifications) was then frozen and independently reviewed as RED before any implementation began; minimal implementation was authorized only after that RED review. Final GREEN verification: all 24 Product Identity tests passed, 3 migration tests passed, full `tests/db_spike` regression 96 passed/3 skipped, ruff/mypy pass; both atomicity cases were independently confirmed **non-vacuous** (real mutations executed, injected failure fired at the intended point, real rollback observed) via a temporary trace outside the repository; independent completion review: "APPROVE SLICE-B COMPLETE — PROCEED TO DOCUMENTATION CHECKPOINT." No new schema beyond the frozen history table; no resolver/candidate/confidence/naming/concurrency-locking behavior, no target-product-not-found contract, and no public correction-history read API were introduced. | **Product Identity is relayed as resumed (owner-authorized; see `docs/project-status.md` §3 and `docs/work-log.md` WL-0028/WL-0029) — this session has not independently witnessed the resumption or the Requirements Freeze it reports, and records both as `[relayed]`.** The implemented-key and Slice-A/Slice-B code facts, and every final GREEN verification (including the non-vacuous atomicity trace), are **[source]**/**[exec]**-verified, labeled per fact in WL-0029/WL-0031/WL-0033/WL-0035; the Requirements Freeze conclusions, evidence/recon pass, and the Batch-B/Batch-C/Slice-B completion-review verdicts are all **[relayed]**, not verbatim transcripts of the original discussion or review. This correction does not itself supply the original requirements discussion, the original recon reports/datasets, full GPT/Claude Chat review transcripts, or original external-source evidence/logs — see the narrowed-but-not-closed gap in §1.2 above, which **neither Batch B's, Batch C's, nor Slice B's code completion closes**. | Explicitly, four categories still not present anywhere in this repository, now narrowed by the relayed Freeze conclusions but not closed: **(1)** the original Product Identity requirements text and its revisions (the Freeze's *conclusions* are relayed; the original discussion is not); **(2)** the original recon reports, datasets/examples, and execution evidence behind the relayed evidence/recon pass; **(3)** GPT's and Claude Chat's respective positions, objections, agreements, and unresolved disagreements on Product Identity, as full transcripts rather than conclusions; **(4)** precise external-source citations (e.g. the specific GS1/Open Food Facts references attempted) and their verification limits — GS1 evidence itself is relayed as **UNKNOWN** (0 successful per-identifier queries). None of these is a Batch or Slice code-completion matter, and no batch's or slice's completion closes any of them. Separately, `tests/db_spike/test_activation_normalized.py`'s module docstring is stale (claims `NormalizedActivationItem`/`normalized_items` are unimplemented; they are not) — tracked as non-blocking documentation/test-comment debt in `docs/work-log.md` WL-0033/WL-0035, not fixed here. See §6 for the transfer request covering the four categories above. | Any further evidenced decision resolving one of the open questions listed in `docs/project-status.md` §3 (e.g. same-retailer many→one, or a chosen concurrency-handling design for assignment writes); transfer of any of the four missing categories above; eventual cleanup of the stale `test_activation_normalized.py` docstring. |
| 8 | Environment/setup, evidenced operational lessons | **`environment.md`** (planned; does not exist — currently split across `README.md` "Requirements"/"Setup"/"Running tests"/"Linting"/"Type checking" sections and scattered work-log notes) | `README.md` lines 83-123 (Python 3.12, `uv sync`, `uv run pytest`/`ruff`/`mypy`). Separately, this session's own git commands throughout `docs/work-log.md` (e.g. WL-0002, WL-0011, WL-0017) needed a one-off `git -c safe.directory='*'` override because this repository is accessed over a `\\wsl.localhost\...` UNC path that Git treats as having dubious ownership. | The `README.md` setup steps are **[source]**-present but this session has not executed them (`uv sync`, `pytest`, etc. — out of scope for every documentation-only stage so far, and out of scope for this one). The `safe.directory` workaround is a **[exec]**-observed, repeated fact of this session's own environment, specific to accessing this repository over this particular UNC path in this particular session's tooling. | An `environment.md` consolidating the README setup steps with this operational note. **This note about the UNC/`safe.directory` workaround is not generalized into a universal rule about `/mnt/c`** or WSL paths in general — it is recorded narrowly, as what this session's own tooling needed, not as a claim about how Git or WSL behaves generally. | Any change to `README.md`'s Requirements/Setup sections; any newly observed environment-specific workaround needed by a future session. |
| 9 | Glossary | **`glossary.md`** (planned; does not exist) | No glossary or terms section was found anywhere in the repository (heading search across all `docs/*.md` and `README.md` found no "Glossary" heading). Domain terms in current use are scattered and self-defined at first use (e.g. "chain_product," "occurrence," "activation," "Round 1/Round 2 persistence" in `docs/project-status.md` §1/§3 and `docs/work-log.md` WL-0009). | Not authored. **[unknown]** whether a glossary was discussed in the GPT/Claude Chat conversation — not relayed to this session if so. | The glossary itself; agreement on which terms warrant a canonical definition. | Any new domain term introduced in an approved document. |
| 10 | Licensing/access constraints, unresolved verification needs | **`constraints.md`** (planned; does not exist) | **ADR 0003** ("No third-party supermarket scraper/parser code," `docs/adr/0003-no-third-party-scraper-code.md`, read in full this round): *Decision* — collectors/parsers "must be independently implemented, working only from" official/public data sources and publicly available format specifications; contributors and any automated coding assistance "must not inspect, copy, translate, port, rewrite, adapt, or otherwise derive implementation code from third-party Israeli supermarket scraper/parser repositories," including reading one "for reference" and reproducing its approach from memory; such repositories "must not be added as dependencies of this project unless that decision is explicitly approved later, after a licensing and legal review." *Consequences* accept slower, from-scratch collector development and state that an ambiguous spec is resolved by inspecting real published data/output, not a third-party implementation. **ADR 0005** ("Dependency licensing policy," `docs/adr/0005-dependency-licensing-policy.md`, read in full this round): *Decision* — before any meaningful new dependency, its license "must be identified and reviewed for compatibility with commercial, proprietary use"; permissive licenses (MIT/BSD/Apache-2.0) are "generally low-risk"; copyleft/ambiguous licenses "require explicit discussion and sign-off before adoption"; an undeterminable license means "work must stop and the question must be raised rather than guessing." It explicitly states it "is an engineering process policy, not legal advice" and "does not substitute for a legal/licensing review by qualified counsel before the product ships commercially." | Both ADRs are **[source]**-confirmed `Accepted` and read directly, in full, this round (correcting the prior version of this row, which explicitly declined to re-open them). This is **repository inspection of recorded project policy**, not new legal research or a fresh legal conclusion — none is offered here, per this task's explicit exclusion of legal/licensing verification. **GS1 and Open Food Facts** (or similar external-source terms potentially relevant to Product Identity or data provenance) are **discussed in the relayed Product Identity/external-data review; detailed source material has not yet been transferred or independently checked in this session.** The fact of discussion is **[relayed]**; their precise claims, access, licensing, coverage, and current terms are each kept separate and are **[unknown]/unverified** — no such reference was found in `src/`, `docs/adr/`, or the currently readable documentation itself, no external research was conducted, and nothing here implies any such integration has been decided or approved. | Whether ADR 0003/0005's policy content is still current against the underlying legal/licensing landscape (out of scope for this task, per its explicit instruction — recorded as a gap, not resolved). The precise GS1/Open Food Facts (or similar) citations actually referenced in that relayed review, and their access/licensing/coverage/current-terms status — none of this is transferred or verified yet; see §6. | Any dependency change; any ADR amendment; a separately authorized licensing/legal review; transfer of the specific citations/material referenced in the relayed review (§6). |
| 11 | Existing workflow, status, history, agent instructions | `docs/development-workflow.md`, `docs/project-status.md`, `docs/work-log.md`, `CLAUDE.md` — **all already exist** (the one topic in this list that is not a planned/future document) | Read in full: `docs/development-workflow.md` (8 sections, collaboration protocol through git save-state discipline), `docs/project-status.md` (current, through this round's §4 update), `docs/work-log.md` (through the latest entry appended this round), `CLAUDE.md` (already in this session's context, unchanged on disk). | These four documents are **[source]**-current as of the `git status`/`rev-parse` run this round. None is committed (see inspected-state note above). Their own content is internally cross-referenced and largely self-auditing (append-only work log, "neither document overrides the other" framing in `docs/project-status.md`'s opening per WL-0014). | Nothing missing about these four documents' own content; the gap is external — no `start-here.md` yet ties them together for a first-time reader (see row 1 and §5). | Every stage already logs here per `docs/development-workflow.md` §5 — this row's own trigger is procedural, not a new one. |

---

## 4. Maintenance plan

Which events update which owning document, and why the work log records
the reason while project-status reflects only the continuation point:

- **`testing-map.md`** (once authored): update in the **same stage/diff**
  whenever tests are added, deleted, or changed in ways that affect the
  mapped behavior, coverage, or execution conditions. Concretely (carried
  forward from the agreement already recorded for this repository, not
  newly invented here):
  - A changed expected exception or error contract.
  - A fixture change that introduces a new edge case, changes input
    provenance, or changes real-versus-mocked dependencies.
  - A changed skip marker, DB/network requirement, or parametrized
    scenario.
  - A rename/move/split/merge/delete of a test function or file — repair
    the map's references and keep the coverage description accurate.
  - Formatting-only edits do **not** require a map rewrite. An
    error-message wording change is **not** automatically cosmetic —
    update the map if it changes the tested contract the map describes.
  - Every diff that changes tests states, in the stage report, how the
    test map was updated or why its existing description remains
    accurate — flagging uncertainty rather than silently skipping it.
- **`database-map.md`** (once authored): update whenever a migration is
  added/changed, or `db_spike`/`durability_spike`/`integration` code
  changes persistence, transaction, ordering, concurrency, or
  retry/idempotency behavior the map describes. A schema or persistence
  change is the trigger; a database-map update check is run whenever one
  occurs, mirroring the testing-map obligation above.
- **`docs/work-log.md`**: updated at every stage (already the case, per
  `docs/development-workflow.md` §5) — records what happened and why,
  including the reason for any documentation update, not only that one
  occurred.
- **`docs/project-status.md`**: updated to reflect the current
  continuation point and to link to whichever maps/documents exist —
  it does not duplicate the work log's reasoning, only the current
  snapshot (per its own opening framing, corrected in WL-0014).
- **`research-and-open-design.md`** (once authored) and any accepted
  decision or `architecture.md` location it eventually resolves into:
  use **bidirectional links** — the research record links to where the
  accepted decision/current architecture lives once resolved, and that
  location links back to the research record's history. Disagreements,
  separate positions, and authorization state are preserved in the
  research record even after resolution; no speculative log-splitting
  scheme is introduced now, and none of the above is executed in this
  task — it is captured here only as the plan.
- This maintenance plan itself is **not** authorization to edit any test,
  schema, or additional instruction file now — it records the rule for
  when those files' owning maps are authored and maintained later.

---

## 5. Gap list and completeness checklist

### Gap list, classified

Each gap is classified as: **(A)** answerable by later targeted repository
inspection; **(B)** requires a specific existing artifact from the owner
(or from GPT, where GPT is the reported holder); **(C)** not yet decided;
**(D)** requires separately authorized research.

1. No `start-here.md` exists to orient a new reviewer. **(A)** — the
   mandatory reading order in §2 and the checklist below are enough to
   draft one once authoring is authorized (next in the §7 sequence).
2. No structured feature/requirement list with approved/open/rejected
   status exists (row 2). **(B)** — the reported product-vision summaries
   and 27-point PDF (§1.2/§6) are the specific artifacts this depends on;
   it is not resolvable by repository inspection alone.
3. The roadmap's original approved text and current sequencing have not
   been transferred into this repository/session (row 3). **(B)** — the
   owner reports an existing roadmap; this requires that specific
   artifact (§6), not repository inspection.
4. `architecture.md`'s "approved-but-unbuilt design" category could not
   be confirmed empty without a full re-read of every ADR's exact text
   (row 4) — only ADR 0003/0005 were read in full this round (for row
   10); the rest still rely on already-recorded summaries. **(A)**.
5. The testing-map and database-map tasks have not started (rows 5-6).
   **Corrected classification:** **(C)**, but not for the reason
   previously stated — this is a scheduling/sequencing matter per the
   agreed plan in §7, not a withheld-approval matter. Content approval
   for the five-file checkpoint was given (§1.1); the maps are simply not
   yet reached in that sequence, and owner commit/push authorization for
   the checkpoint remains separately pending.
6. The WL-0016 open question (an indirect collector→normalize→persistence
   test path via a helper/fixture) remains unresolved, and this task was
   explicitly instructed not to re-investigate it. **(A)**, deferred to
   the dedicated testing-map task.
7. No glossary exists (row 9). **(A)** for compiling already-used terms;
   **(C)** for which terms warrant canonical definitions.
8. ADR 0005/0003's current licensing/legal accuracy against the outside
   legal landscape is unverified (row 10), by this task's own explicit
   exclusion of legal research. **(D)**.
9. The harness's "checked into the codebase" label for `CLAUDE.md` does
   not match actual `git status` (untracked). **(A)** — worth a one-line
   caution in `start-here.md` once authored, so a new reviewer checks
   `git status` rather than trusting a harness label.
10. The four categories of missing Product Identity research material
    (row 7: original requirements/revisions, recon reports, GPT/Claude
    Chat positions and disagreements, external-source references) are not
    present anywhere in this repository. **Corrected, split by
    availability (§1.2/§6):** GPT/Claude Chat's positions/objections/
    agreements/disagreements are reported held by GPT as review messages
    — **(B)**, a specific transfer. The original requirements/revisions
    and the original recon reports/datasets/examples are **still missing
    or unlocated even from GPT** per §1.2 — a summary or review message
    about them is not the same as the original, so this remains **(B)**
    only if the originals can actually be located, and otherwise **(C)**
    (not yet decided/known whether they still exist in retrievable form).
    This task does not attempt to reconstruct any of them from memory or
    synthesize the missing agreement. **Further narrowed, not closed
    (`docs/work-log.md` WL-0028/WL-0029; `docs/project-status.md` §3):**
    the Requirements Freeze's own conclusions, and the fact that an
    evidence/recon pass (46-identifier sample, Open Food Facts pass, GS1
    accessibility attempt) occurred, are now relayed and recorded — but
    this is the Freeze's conclusions and the fact of the recon pass, not
    the original requirements discussion or the original recon
    reports/datasets themselves, which remain **(B)**/**(C)** exactly as
    above.
11. GS1/Open Food Facts (or similar external product-identifier sources)
    are **known to have been discussed** in the relayed Product
    Identity/external-data review (row 10) — this is no longer an open
    "was it discussed" question. What remains open is the precise claims
    made, and the access/licensing/coverage/current-terms verification of
    any such source — none of which has been transferred or independently
    checked in this session. **(B)** — requires the specific citations/
    material from that review (§6); this task performs no external
    verification itself, and nothing here implies any integration was
    approved.

### Completeness checklist — could a new reviewer explain, from committed
(or currently pending-review) documentation alone:

**Corrected:** the prior version of this checklist asserted "three of six
are fully satisfied" without the aggregate matching its own six bullet
points (only two, not three, were marked affirmatively) — an unsupported
count. Replaced below with an explicit status per item and a short,
evidence-based reason for it.

1. **Product purpose and approved vs. open requirements — Partial.**
   `README.md`'s one paragraph plus `docs/project-status.md` §2's relayed
   platform direction exist; no structured requirement-status list exists
   (gap 2), and the reported product-vision summaries/27-point PDF have
   not been transferred (gap 2, §6).
2. **What exists and how components connect — Partial.**
   `docs/project-status.md` §1 covers this well for implemented
   components, source-cited; no dedicated `architecture.md` exists yet,
   and the approved-vs-unbuilt distinction has not been exhaustively
   re-verified against every ADR's full text (gap 4).
3. **Test coverage and execution-evidence limits — Partial.** The work
   log (WL-0009/WL-0016/WL-0019/WL-0021) documents this well for the one
   specific collector→normalize→persistence question; no general
   `testing-map.md` exists yet (gap 5/6 sequencing), and no test suite has
   been executed by any session recorded in this log.
4. **Roadmap and current stopping point — Partial.** The stopping point
   is well-documented (`docs/project-status.md` §4); the roadmap itself
   has not been transferred into this repository (gap 3).
5. **Collaboration protocol and approvals — Satisfied.**
   `docs/development-workflow.md` §1 and §4 fully cover the protocol, and
   §1.1 above now records the checkpoint's actual approval state
   explicitly (content approved; commit and push separately pending)
   rather than leaving it implicit.
6. **Where to find deeper supporting evidence — Partial.** Satisfied for
   what has been inspected: every claim in `docs/project-status.md` and
   `docs/work-log.md` cites a specific file/line or test path. Missing
   for what has not yet been mapped or transferred: the testing/database
   maps (gaps 5-6) and the four Product Identity research categories
   (gap 10).

**Corrected count:** one item (5) is fully Satisfied; the remaining five
(1, 2, 3, 4, 6) are Partial. No item is assessed as wholly Missing at the
checklist-topic level, though several of their underlying gaps are.

---

## 6. Concrete source transfer list

A targeted request, built from the gaps above — not a request to resend
the full project history or recreate everything indiscriminately. Rows
are split into material reported **available to GPT** (§1.2) and
material **still missing or unlocated** even once that is transferred —
a summary is not the same as the original it summarizes.

**Available to GPT — request is to relay, not to locate:**

| Artifact/topic | Reported holder/location | Why needed | Available / not yet transferred | Specific request |
|---|---|---|---|---|
| Supplied product/project-history summaries | Available to GPT (reported), outside this session's context | Supports `start-here.md`/`roadmap.md` historical framing and `product-vision.md` feature framing (gaps 1, 2, 3) | Available to GPT; not yet transferred to this session | Relay the summary text (or its source) explicitly — this session has no other access route. |
| The improvement PDF (27-point) | Available to GPT (reported), as an attachment | Contents unknown to this session; could bear on `product-vision.md`, `roadmap.md`, and/or `research-and-open-design.md` | Available to GPT; not yet transferred; format unresolved (a PDF cannot be relayed as plain chat text without loss) | Clarify whether the file itself can be supplied to this repository/session directly, or whether GPT will convey its substantive content in text — do not assume either route without the owner's confirmation. |
| Product Identity/external-data review messages and subsequent responses | Available to GPT (reported), from the GPT/Claude Chat conversation | Closes part of gap 10/row 7 — GPT's and Claude Chat's respective positions/objections/agreements/disagreements | Available to GPT; not yet transferred | Relay the substantive content — not a conclusion or summary of who agreed — specifically preserving disagreements and open points. **This is a discussion/summary record, not necessarily the original requirements or recon reports themselves** — see the "still missing" rows below for those. |
| Explicit owner statements made in the conversation | Available to GPT (reported) | Ensures the work log's provenance entries are complete | Available to GPT; not yet transferred | Relay any such statement/decision this session's work log does not already record. |

**Still missing or unlocated — request is to locate the originals, not
just relay a summary of them:**

| Artifact/topic | Reported holder/location | Why needed | Available / not yet transferred / unlocated | Specific request |
|---|---|---|---|---|
| Original approved roadmap text and latest sequencing | Reported by the owner as existing; not established whether GPT holds the original text or only a summary of it | Closes gap 3 — needed to author `roadmap.md` with real content, not a placeholder | Still missing/unlocated in this session | The roadmap's actual approved text and current sequencing — not a summary of it — so it can be reconciled against this repository's ADRs and `docs/project-status.md`. |
| Original Product Identity requirements and their revisions | Reported to exist historically; not established whether GPT holds the originals or only messages discussing them | Closes part of gap 10/row 7 — the original requirement text, not a restated conclusion about it | Still missing/unlocated | The original requirement text and its revision history, if recoverable. Transferring the review messages above is not expected to supply this by itself. |
| Original recon reports, datasets/examples, and execution evidence | Reported to exist historically (recon work is also referenced generally in ADR 0006/0007); not established whether GPT holds the originals | Closes part of gap 10/row 7 — the actual recon findings/limitations, not a conclusion about them | Still missing/unlocated | The original recon report content, datasets/examples, and execution evidence, if recoverable. |
| Precise external citations for GS1/Open Food Facts (or similar) | Discussed in the relayed Product Identity/external-data review (row 10); detailed source material not yet transferred or independently checked | Needed to assess exactly what was proposed and its verification limits (row 10/gap 11) | Discussed, but detailed material not yet transferred/checked — distinct from "unknown whether discussed" | The specific citation(s) actually referenced in that review, and whatever access/licensing/coverage/current-terms information accompanies them, if any. This task performs no fresh external verification itself, and nothing here implies any such integration was approved. |

---

## 7. Agreed sequence and this session's proposed elaboration

**Agreed sequence** (relayed via the owner, this round):

1. Review and approve this evidence matrix.
2. Prepare a small `start-here.md` guide grounded in this matrix, clearly
   marking every still-planned document as planned.
3. Build technical maps (`testing-map.md`, `database-map.md`) and
   product/research documentation (`product-vision.md`, `roadmap.md`,
   `research-and-open-design.md`, etc.) in separately reviewed stages.

**This task does not execute any part of this sequence** — no
`start-here.md` and no domain map is authored here.

**This session's proposed elaboration of step 3 only** (offered for
review; it does not reorder or compete with steps 1-2 above, and is not
itself independently agreed at this level of detail):
- Author `testing-map.md` and `database-map.md` together, since they
  cross-reference each other's evidence (per this repository's already-
  agreed document-ownership split).
- Author `architecture.md` using a full-text (not summary-only) re-check
  of every ADR for the approved-vs-unbuilt distinction (gap 4).
- `product-vision.md`, `roadmap.md`, `research-and-open-design.md`,
  `glossary.md`, `environment.md`, and `constraints.md` each depend on an
  owner- or GPT-held artifact this session does not yet have (§6) —
  request those specifically before drafting, rather than authoring
  placeholder content.

---

## 8. Validation

**Performed in the prior stage** (reproduced here for continuity, not
re-run this round): `git status --porcelain=v1` clean read; `git diff
--check`/`diff --no-index --check` on the then-current files, informational
LF→CRLF warning only, no error lines; `git rev-parse HEAD` confirmed
unchanged; a manual relative-link check on this document's own links.

**Performed this round** (this session's own **labeled summary** of real
command output just run, not a verbatim-transcript claim, per the
standard set in `docs/work-log.md` WL-0015):
- `git -c safe.directory='*' --no-optional-locks status --porcelain=v1` —
  same file set as before this round, no new untracked files beyond the
  three this task authorizes writing to.
- `git -c safe.directory='*' --no-optional-locks diff --check -- README.md`
  and `git -c safe.directory='*' --no-optional-locks diff --no-index
  --check /dev/null <file>` for `docs/project-status.md`,
  `docs/work-log.md`, and this file — each produced only the expected
  LF→CRLF informational warning, no error lines.
- `git -c safe.directory='*' --no-optional-locks rev-parse HEAD` —
  confirmed unchanged.
- A manual relative-link and cross-section-reference check across this
  document (the `§`-numbered references were updated to match this
  round's restructuring — two pre-existing cross-reference errors, found
  during this pass, are corrected: the mandatory-reading-order item that
  pointed to "§6" for the authoring sequence now correctly points to §7,
  and the evidence-key legend's "(§0 above)" reference, which pointed to
  a section that never existed, now reads as a plain reference to the
  inspected-state note at the top of the document).
- No project code, tests, builds, migrations, collectors, external APIs,
  or database operations were run this round.
