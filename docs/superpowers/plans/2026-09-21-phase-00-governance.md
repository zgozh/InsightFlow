# InsightFlow Phase 0 Governance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish a small, auditable project-governance layer on top of the byte-equivalent DeerFlow v2.1.0-rc0 baseline before product code changes begin.

**Architecture:** Preserve the tagged upstream tree as immutable provenance, then add only project identity, decision records, progress tracking, acceptance scenarios, and repository-size budgets. This phase changes no runtime code, dependencies, routes, database schema, or UI behavior.

**Tech Stack:** Git, Markdown, existing repository checks.

**Spec:** `docs/architecture/architecture-refactoring-report.md`

## Global Constraints

- Upstream source is fixed at `v2.1.0-rc0`, commit `769589e8daee14c2587a634b6b43bd96471a41a1`.
- The local baseline tag `upstream-v2.1.0-rc0` must remain unchanged.
- Preserve `LICENSE` and ByteDance/DeerFlow attribution.
- Do not rename the `deerflow.*` Python namespace.
- Do not modify runtime code, dependency manifests, lockfiles, Docker files, routes, or UI in Phase 0.
- Do not commit `text.md`; it is local product-discussion input.
- Do not run formatters over unrelated upstream files.

---

### Task 1: Pin provenance and local-only inputs

**Files:**
- Create: `UPSTREAM.md`
- Modify: `.gitignore`
- Test: Git metadata and ignore rules

**Interfaces:**
- Consumes: local tag `upstream-v2.1.0-rc0`
- Produces: a human-readable provenance contract and an ignored local discussion file

- [ ] **Step 1: Verify the immutable baseline before editing**

Run:

```powershell
git rev-parse upstream-v2.1.0-rc0
git rev-parse 'upstream-v2.1.0-rc0^{tree}'
git status --short
```

Expected: commit `609bfde...`, tree `2473c22e163a3879490848a7995eb2b7be7f6f50`, and only the architect-authored uncommitted design files plus `text.md` may be present.

- [ ] **Step 2: Create `UPSTREAM.md` with exact provenance**

Use this content:

```markdown
# Upstream provenance

InsightFlow is based on ByteDance DeerFlow under the MIT License.

- Upstream repository: https://github.com/bytedance/deer-flow
- Upstream release: `v2.1.0-rc0`
- Upstream commit: `769589e8daee14c2587a634b6b43bd96471a41a1`
- Imported tree: `2473c22e163a3879490848a7995eb2b7be7f6f50`
- Local immutable baseline tag: `upstream-v2.1.0-rc0`

The first InsightFlow commit contains exactly the upstream Git tree. Product changes are maintained as later commits so that `git diff upstream-v2.1.0-rc0..main` remains an auditable description of the secondary development.

The original `LICENSE` and applicable copyright notices must be preserved.
```

- [ ] **Step 3: Ignore local orchestration input**

Append exactly this documented block to `.gitignore`:

```gitignore
# Local architecture discussion; not a product source file.
/text.md

# Local implementation/review evidence; summarize accepted evidence in docs.
/.reviews/
```

- [ ] **Step 4: Verify provenance and ignore behavior**

Run:

```powershell
git check-ignore -v text.md
git diff --check
git diff -- .gitignore UPSTREAM.md
```

Expected: `text.md` and `.reviews/` are ignored by the new root rules; `git diff --check` exits 0.

- [ ] **Step 5: Do not commit yet**

Task 1 and Task 2 form one documentation-only governance commit because the decision record explains the provenance rule.

### Task 2: Record the approved architecture decision

**Files:**
- Create: `docs/decisions/0001-insightflow-hard-fork.md`
- Create: `docs/PROGRESS.md`
- Create: `docs/acceptance/acceptance-scenarios.md`
- Reference: `docs/architecture/architecture-refactoring-report.md`

**Interfaces:**
- Consumes: approved Route A and the architecture report
- Produces: durable decision, current-state ledger, and release-level acceptance contract

- [ ] **Step 1: Create ADR 0001**

The ADR must contain `Status: Accepted`, `Date: 2026-09-21`, context, the three evaluated routes, the Route A decision, consequences, dependency direction `app -> harness`, the no-global-namespace-rename decision, and links to `UPSTREAM.md` and the architecture report. Do not introduce decisions absent from the report.

- [ ] **Step 2: Create the progress ledger**

Start with this table and keep it factual:

```markdown
| Phase | Status | Evidence | Next gate |
| --- | --- | --- | --- |
| 0 Baseline and governance | In progress | `upstream-v2.1.0-rc0`; architecture report | Phase 0 review |
| 1 Analytics boundary | Not started | — | Approved Phase 1 prompt |
| 2 Safe data access | Not started | — | Approved Phase 2 prompt |
| 3 Agent workflow | Not started | — | Approved Phase 3 prompt |
| 4 Product UI | Not started | — | Approved Phase 4 prompt |
| 5 Capability removal | Not started | — | Approved deletion manifests |
| 6 Deployment and acceptance | Not started | — | Full acceptance evidence |
```

Below it add the repository budget: target 850–1050 tracked files, hard ceiling 1200, 450–650 production-source files, 250–350 test files, and four default containers. State that security coverage overrides file-count reduction.

- [ ] **Step 3: Create release-level acceptance scenarios**

Write Given/When/Then scenarios for exactly these behaviors: authentication; MySQL datasource; PostgreSQL datasource; datasource/table/column denial; DDL/DML/multi-statement blocking; timeout and result caps; Lead-to-reviewer analysis flow; failed subagent recovery; structured SSE trace without chain-of-thought; report artifact; scheduled analysis; PostgreSQL restart recovery; secrets/PII absent from logs and events; MCP cannot bypass query policy; four-service default Compose startup.

- [ ] **Step 4: Validate cross-document consistency**

Run:

```powershell
rg -n "v2\.1\.0-rc0|769589e8|2473c22e" UPSTREAM.md docs/decisions docs/architecture
rg -n "850.1050|1200|450.650|250.350" docs/PROGRESS.md docs/architecture
git diff --check
```

Expected: provenance appears consistently; all four size budgets are present; diff check exits 0.

- [ ] **Step 5: Commit the governance layer**

```powershell
git add .gitignore UPSTREAM.md docs/architecture/architecture-refactoring-report.md docs/decisions/0001-insightflow-hard-fork.md docs/PROGRESS.md docs/acceptance/acceptance-scenarios.md docs/superpowers/plans/2026-09-21-phase-00-governance.md docs/prompts/phase-00-governance.md
git commit -m "docs: establish InsightFlow architecture governance"
```

Expected: one documentation-only commit after the immutable baseline.

### Task 3: Produce the review evidence package

**Files:**
- Create locally, but do not commit: `.reviews/phase-00-implementation-report.md`
- Test: Git diff and history inspection

**Interfaces:**
- Consumes: completed Phase 0 diff and command output
- Produces: a review packet for the architecture reviewer

- [ ] **Step 1: Capture final evidence**

Run:

```powershell
git status --short --branch
git log --oneline --decorate -3
git diff --stat upstream-v2.1.0-rc0..HEAD
git diff --check upstream-v2.1.0-rc0..HEAD
git ls-files | Measure-Object
```

- [ ] **Step 2: Write the implementation report**

The report must include: resulting commit hash; files created/modified; exact commands and exit codes; tracked-file count; deviations (write `None` if absent); and confirmation that runtime code, manifests, lockfiles, Docker and UI were untouched.

- [ ] **Step 3: Stop for architecture review**

Do not start Phase 1, rebrand code, delete modules, update dependencies, or amend the baseline tag.

## Plan self-review

- Spec coverage: Phase 0 provenance, scope, budget, acceptance and rollback evidence are covered.
- Placeholder scan: no unresolved placeholder markers are permitted in deliverables.
- Boundary check: the phase is documentation-only and cannot change runtime behavior.
