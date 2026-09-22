# InsightFlow Progress

Baseline: DeerFlow `v2.1.0-rc0` (`769589e8daee14c2587a634b6b43bd96471a41a1`), immutable local tag `upstream-v2.1.0-rc0`. See [UPSTREAM.md](../UPSTREAM.md).

## Phase ledger

| Phase | Status | Evidence | Next gate |
| --- | --- | --- | --- |
| 0 Baseline and governance | Complete | `936758c`, `aa516bd`; architecture report; ADR 0001 | Phase 1 implementation |
| 1 Analytics boundary | Complete | `53ed1f4`; focused/guidance/Ruff review PASS | Phase 2A implementation |
| 2 Safe data access | Complete | 2A `8a11d0e`, `f2d35d3`; 2B1 `44f62c3` + Fix 01; 2B2 `3a65865` + Fix 01; 2C1 `eda8878` + Fix 01 `0fc32bd`; 2C2 `568a3d6` + Fix 01 `c450c8c`，各切片均已复验 | Phase 3 implementation |
| 3 Agent workflow | Complete | `7bd21d7`：受控查询 Agent 工具、确定性 evidence、经营分析 skill、operator-owned 加法式 subagent denylist；schema 层排除多余参数的 V1 裁决已记录 | Phase 4 implementation |
| 4 Product UI | In progress | `ae89805`：报告索引、Analytics 管理页、安全 trace 投影与 InsightFlow 产品工作台；等待可见品牌与 diff 清洁修复 | Phase 4 Fix 01 GPT review |
| 5 Capability removal | Not started | — | Approved deletion manifests |
| 6 Deployment and acceptance | Not started | — | Full acceptance evidence |

Phase 2 is delivered in four independently reviewed slices: **2A** deterministic SQL policy core, **2B1** semantic authorization core, **2B2** governed datasource execution, and **2C** persistence and delivery. A slice is not complete until its own gates and review pass.

Only one primary commit per phase; fixes use later small commits. A phase is never marked complete without its test commands, exit codes and key output recorded in the phase review artifact.

## Repository size budget

Size is governed by budget, not by a single file-count target. The upstream baseline is 2917 tracked files.

| Metric | Upstream baseline | Target | Hard limit / note |
| --- | ---: | ---: | --- |
| Git tracked files | 2917 | 850–1050 | 1200; never delete required security tests to hit the target |
| Production source files | ~1300 | 450–650 | excludes tests, migrations, generated files and lockfiles |
| Test files | ~1020 | 250–350 | prioritise runtime, SQL safety and key E2E |
| Effective text lines of code | ~820k | 140k–220k | excludes lockfiles, generated files and large fixtures |
| Default containers | 4+ optional components | 4 | nginx, frontend, gateway, postgres |
| Optional containers | many provider/provisioner variants | 2 | redis, AIO sandbox |

**Security coverage overrides file-count reduction.** The coverage matrix takes priority over the file-count budget: a reduction that removes runtime, SQL-safety or key E2E regression coverage is not an acceptable way to reach the target. A "minimal" repository below roughly 650 tracked files would require removing Scheduler, MCP, Memory or a large part of the runtime test suite, and is out of scope for the current enterprise-grade goal.

## Delivery and rollback

- Every phase ships one commit with a single clear responsibility, plus later small fix commits; never one unreviewable commit mixing deletions and new features.
- Rollback is per phase: revert the phase commit, or fall back to `upstream-v2.1.0-rc0` for the baseline.
- Acceptance is release-level: see [docs/acceptance/acceptance-scenarios.md](acceptance/acceptance-scenarios.md).
