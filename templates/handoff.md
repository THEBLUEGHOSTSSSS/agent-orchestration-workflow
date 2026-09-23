# Structured Handoff

> Optional companion to [structured handoff guidance](../docs/structured-handoff.md). Record observed evidence only; this template does not execute or enforce a contract.

## Identifiers

- Goal ID: `G-EXAMPLE`
- Goal revision: `1`
- Task ID: `T-01`
- Worker attempt: `1 of 2` (`2 of 2` if this is the single commander-requested rework)
- Baseline revision or artifact snapshot (required before dispatch): `[actual baseline]`
- Lineage / new-scope rationale: `none`

## Actual Files Changed

- `path/to/file`: [actual change]

## Criterion Evidence

| Criterion | Evidence | Observed outcome | Check status |
| --- | --- | --- | --- |
| `AC-1` | [artifact, location, or observation] | [what was actually observed] | `not-run` |

Use `not-run` with a reason when a relevant check was not performed. Select checks that address the stated criteria; this template does not impose a blanket all-tests requirement.

## Acceptance Review

| Review layer | Acceptance state | Basis |
| --- | --- | --- |
| Worker-reported | [reported complete / incomplete / blocked] | [worker evidence and limits; self-report and exit status are not acceptance] |
| Commander review for this submission | [accept / rework / takeover / blocked] | [reviewer, defects, current-artifact evidence, and checks; required not-run checks mean blocked] |

## Attempt Ledger

| Attempt | Launch/result | Evidence and defects | Commander decision |
| --- | --- | --- | --- |
| `1 of 2` | [launched / interrupted / reported] | [links and observed defects] | [accept / rework / takeover / blocked] |
| `2 of 2` | [not used / launched / interrupted / reported] | [links and observed defects] | [accept / takeover / blocked; no third Worker round] |

Waiting for the same running execution is not a new attempt. An interrupted or uncertain launch consumes its attempt conservatively. Renaming the task or changing worker, model, session, or goal revision does not reset unresolved work.

## Experience Record

- Record: [project-local path or ID; required for every delegated task, including failed or blocked work]
- Status / reviewer: [candidate / verified / deprecated; reviewer]
- Evidence linkage: [artifact, review, and attempt evidence]
- Novel lesson: [lesson, or explicitly `none observed`]

## Human Authority Remaining

[State decisions, budget, scope, or final acceptance retained by the human. Existing authorization remains effective within its stated bounds and does not require repeated approval for each ordinary step.]

## Conflicts

[List contract, workspace, evidence, or concurrent-edit conflicts; write `none observed` only when checked.]

## Next Action

[One concrete next action, owner, and any authorization or evidence it requires. If attempt 2 failed, assign commander repair, testing, and review rather than another Worker call.]
