# Adaptive routing — commander acceptance and experience

Task: ADAPTIVE-ROUTING-20260924. Baseline: 02d975a. Scope: public portable routing runtime, tests, documentation, local commander integration; no credentials, research contents or private launcher implementation published.

## Acceptance

Accepted after commander integration and verification. Required capabilities delivered: task-aware worker selection, historical experience retrieval, outcome attribution and experience updates, attempt-aware model switching. Full A–P report: [IMPLEMENTATION_REPORT.md](../docs/adaptive-routing/IMPLEMENTATION_REPORT.md).

Evidence: 46 tests passed; bytecode compilation and whitespace checks passed; both isolated live adapter probes produced exact requested artifacts and passed commander review; probe ledger static validation passed. [Evidence inventory](2026-09-24-adaptive-routing-evidence.json) contains source hashes, scoped results and probe metadata. Synthetic/probe records are excluded from real suitability learning. No measured cost-saving percentage or backend identity attestation is claimed.

## Delegation ledger

| Logical task | Round / baseline / acceptance | Result and commander decision |
| --- | --- | --- |
| AUDIT-CONTRACTS | 1 / 02d975a / trace actual lifecycle and distinguish policy/static/runtime | Read-only audit accepted after source spot checks; informed pre-edit assessment |
| ROUTING-CORE-20260924 | 1 / 02d975a + DESIGN / models, registry, retrieval, router and scenario tests | Produced artifacts/tests, did not return final report before 780s bound; connection failures visible. Commander took over, corrected integration/scoring/config issues and verified; no second or third execution |
| REVIEW-RUNTIME | 1 / new runtime / independent read-only acceptance, lineage and process review | Found alias fingerprint hole, lingering descendant and weak static validation. Commander repaired; review round 2 confirmed corrections |
| REVIEW-RUNTIME | 2 / integrated core / verify fixes plus explicitly added routing-architecture review scope | Found zero-weight division and inappropriate low-assurance transfer. Commander repaired and ran new targeted regressions; no further worker execution |
| PROBE-gpt6_sol_xhigh | 1 / isolated empty repository / exact output file | Artifact passed, reviewed, stored as probe; no ability-learning credit |
| PROBE-gpt56_sol_high | 1 / isolated empty repository / exact output file | Artifact passed, reviewed, stored as probe; no ability-learning credit |

Commander repair and verification are not described as independent third-party approval. All review findings are resolved in this snapshot. Human retains final acceptance/override.

## Experience and applicability

1. **Identity mapping:** when a fix/parent alias is declared, register its work-key fingerprint as well as its name. Otherwise a later rename can acquire fresh budget using already-known identity. Evidence: reproduced supported-API hole and test_L regression. Applicable to ledger-backed retries; invalidated if identity architecture changes. Status: verified.
2. **Process termination:** parent exit does not establish child termination. Kill surviving process-group members on bounded timeout even if the leader already exited. Evidence: independent reproduction and descendant-marker regression. Applicable to POSIX same-group children; does not cover adversarial detached sessions. Status: verified.
3. **Acceptance integrity:** check original criteria, checker disposition and current final artifact hashes, not only a boolean accepted flag. Preserve historical failed evidence as historical, since legitimate repairs change artifacts. Evidence: mutation regressions. Applicable to file-based acceptance; semantic correctness still requires review. Status: verified.
4. **Weighted retrieval:** skip zero-weight records and do not turn weak local verification into high-risk production confidence. Evidence: zero-version discount and low-assurance transfer regressions. Applicable to structured similarity routing; thresholds need future real outcomes. Status: verified implementation rule, empirical benefit unmeasured.
5. **Worker completion:** successful intermediate tests are useful artifacts, but bounded timeout plus service errors cannot establish completed worker delivery or causal model failure. Evidence: core execution state and actual files. Next dispatch improvement: narrow core implementation packages, retain bounded stop and independently inspect partial artifacts. Cause of missing final report remains uncertain; do not reduce model suitability from this event. Status: reviewed, no universal model conclusion.
6. **Adapter probes:** per-call model/effort overrides preserve the default provider configuration and can be tested in isolated directories. Evidence: two exact-file probes. Applicability: current local launcher and gateway; invalidated by CLI/provider/version changes. Status: connectivity verified, comparative quality/cost unknown.

These are project-local engineering lessons. No user-level memory or personal preferences were written. Future routing uses reviewed real task records; these notes do not fabricate historical performance samples.
