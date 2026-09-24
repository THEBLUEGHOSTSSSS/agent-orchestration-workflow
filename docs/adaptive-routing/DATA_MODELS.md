# Core data contracts (schema version 1)

Executable validation lives in `routing/models.py`, `service.py`, `store.py`, and `validation.py`; these are deliberately stdlib contracts, not a claim of full JSON Schema implementation. The old task/review templates remain supported separately.

| Contract | Required fields / constraints |
| --- | --- |
| TaskSignature | domain, task_type, task_subtype, complexity, reasoning_intensity, tool_intensity, verification_strength, risk_level, scope, cross_module_scope, language, framework, environment, estimated_execution_volume; optional required_capabilities |
| WorkerDefinition | unique worker_id, provider, model, reasoning_effort, version, enabled, availability, adapter, capabilities, cost_profile, latency_profile, prior; manual_notes optional |
| RoutingDecision | selected_worker, reasoning_effort, selection_mode, routing_reason, historical_sample_count, historical_confidence, alternative_worker, historical_evidence_used, per-worker suitability |
| OutcomeDiagnosis | attribution, failure_type, severity, summary; accepted outcomes require NONE/NONE/none; rejected outcomes require attribution/type/severity/explanation |
| Task | task_id, logical_task_id, stable work_key, workspace, baseline, objective, scope, acceptance_criteria, task_signature, source_kind, status, worker_attempt_count, attempts; context/plan and new-scope rationale |
| Attempt | canonical logical_task_id, attempt_number, immutable worker snapshot, actual routing decision, timestamps, execution, review, experience_id; attempt 2 additionally full handoff |
| ExperienceRecord | experience_id, timestamp, logical_task_id, attempt_number, task_signature, worker, routing, execution, verification, outcome, diagnosis, retry, repair, source_kind, valid; invalid_reason optional |
| Review | reviewer, accepted, action, diagnosis, criteria, evidence, static_checker_result; optional final_quality, repair, invalid_task/reason, sourced execution_metrics; retry requires handoff |
| Takeover | reviewer, summary, all original criteria passed with observations, hashed evidence, checker disposition, nonnegative repair_burden |
| Ledger | schema_version, monotonic revision, canonical tasks, aliases, work_keys, experiences, events |

Scales: low/medium/high; verification weak/moderate/strong; scope single_file/multi_file/repository; environment local/ci/staging/production. Free semantic tags must be nonempty. Use consistent project vocabulary rather than embedding an entire prompt into a task_type.

`execution` records exit_code, error, duration_seconds, token_usage, estimated_cost, currency, tool_calls and log path/hash. Unknown values are null. CLI does not infer provider charges from token count; commander may record sourced metrics after inspection. Latency is wall time, repair_burden is minutes, cost comparison requires the configured currency. Raw token usage can retain provider-specific detail.

`verification` records tests/checks run, passed IDs, static checker result, actual reviewer and hashed evidence. `outcome` distinguishes FIRST_PASS_ACCEPTED, SECOND_PASS_ACCEPTED, ACCEPTED_WITH_MINOR_REVIEW, ACCEPTED_AFTER_MAJOR_REVISION, STRONG_MODEL_TAKEOVER_REQUIRED, FAILED and pending UNREVIEWED.

`retry` stores required, action, previous_worker and next_worker. Actions preserve A→A/A→B and takeover. `repair` stores required, scope, severity, burden, takeover and final task takeover context. A commander's successful repair updates final task status without changing failed worker acceptance to true.

Failure attribution enum: MODEL_RELATED, TASK_SPEC_RELATED, ENVIRONMENT_RELATED, TOOL_RELATED, DATA_RELATED, EXTERNAL_SERVICE_RELATED, UNKNOWN; successful work uses NONE. Common model failure types are LOCAL_IMPLEMENTATION_ERROR, REASONING_FAILURE, ARCHITECTURE_FAILURE, MISUNDERSTOOD_REQUIREMENT, INCOMPLETE_EXECUTION, LOOP_BEHAVIOR, CONTEXT_HANDLING_FAILURE. Additional reason tags are allowed, with an explicit default weight rather than silently becoming a new special route.

State progression: READY → RUNNING → AWAITING_REVIEW → ACCEPTED / RETRY_READY / BLOCKED / TAKEOVER_REQUIRED. RETRY_READY allows exactly one remaining worker round. A second rejection forces TAKEOVER_REQUIRED. Commander takeover validates to ACCEPTED with final_status=accepted_after_takeover.

The process writes a worker/version snapshot per attempt. An unknown API snapshot is `unspecified`; timestamp/model/effort remain recorded. Registry changes never rewrite historical worker snapshots. Version mismatch discounts evidence. Ledger aliases and registered work-key fingerprints are immutable budget lineage; intentionally undisclosed semantic equivalence remains a human/commander policy responsibility.
