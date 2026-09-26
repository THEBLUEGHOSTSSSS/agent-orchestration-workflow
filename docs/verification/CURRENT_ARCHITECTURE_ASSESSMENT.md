# Current architecture assessment — 2026-09-26

Baseline HEAD 0c249b2 plus preserved local Jev feature/experiments. Existing modules inspected before implementation: models/config, selection, service lifecycle, store, validation, adapters, CLI and test fixtures. VERIFY-AUDIT-01 independent read-only audit accepted by Commander.

Human scope → structured task signature → Worker registry/heuristic+reviewed conditional history → reserve attempt → external tool-capable worker → reported artifact → Commander review/attribution → retry, accepted, blocked or takeover → Worker experience. Jev is optional advisory and stays OFF.

| Capability | Current enforcement |
|---|---|
| Two Worker attempts, aliases, required second-round handoff, atomic ledger | HARD_ENFORCED through intact controlled runtime |
| Evidence file hashes and original criterion coverage | HARD_ENFORCED at review/takeover; STATIC_CHECKED later |
| Truth of checks, strong-model capability, semantic task identity | POLICY_ENFORCED; not an authenticated security boundary |
| Scope obedience, no outside-launch retries, real human identity | NOT_CURRENTLY_ENFORCEABLE by this local process |
| Reviewer independence/routing/risk-tier policy/judge/human state | Missing before this change |
| Reviewer cost/token budgets | Missing before this change; existing worker subprocess timeout only |
| Worker suitability experience | Present; must not mix Reviewer records into execution-only collection |

Integration decisions: optional frozen per-task policy; attach verification session to each reported attempt. Preserve legacy states and workers. Gate BOTH review() and takeover(). Critical tier belongs to verification assessment, not old Worker risk enums. Reviewer history separate, conditional, and Commander-adjudicated; never infer correctness from agreement. Reserve bounded reviewer resources before launch. Blindness is packet-level; generic local subprocess is not OS isolation. Migration is additive for old ledgers/tasks.
