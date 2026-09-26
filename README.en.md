# agent-orchestration-workflow

**Human → Commander → Worker: the human owns the goals and final decision; the commander directs and reviews; replaceable workers execute bounded tasks.**

This is a host- and model-neutral collaboration policy with an optional adaptive routing implementation. A commander can operate in Codex, Claude Code, or another capable environment; its host and the worker backend are independent choices. Keep architecture, judgment, and critical review with the commander; delegate substantial reading, implementation, rewriting, testing, and self-checks when useful. Do not delegate trivial work by default.

[中文](README.md) · [Policy](AGENTS.md) · [Hosts and adapters](docs/host-adapters.md) · [Review and learning](docs/review-and-learning.md)

## The workflow

1. The human sets goals, budget, authorization, and ultimate acceptance. The commander defines scope, baseline, acceptance criteria, stop conditions, and eligible workers.
2. The router suggests explainable candidates using task characteristics and **reviewed, applicable** project experience; the commander reviews or overrides the choice. An attempt is reserved before execution starts.
3. A worker returns artifacts, checks, and uncertainties within its authority. The commander inspects actual evidence **after every attempt** and records defects and a decision; exit status or a worker report alone is not acceptance.
4. Each logical task has **at most two worker attempts**: an initial run and at most one commander-requested correction. Changing the model, host, or task name does not reset the limit. After a failed second attempt, the commander repairs and verifies directly or records a truthful blocker.
5. Technical acceptance **and** a project-local experience entry are required before successful delivery. Attribute failures to model, task specification, environment, tools, data, or external service as appropriate; only reviewed, applicable experience informs later routing.

The aim is more **accepted useful work per total cost**, not automatic savings. Track primary-model quota, spending, aggregate tokens, review, and repair separately. No universal saving percentage or cross-provider quality guarantee is claimed. A static record checker is neither a security boundary nor a substitute for commander review.

## Configure and run

The router uses Python 3.11+ and a POSIX environment (macOS/Linux). The default [`routing/defaults.json`](routing/defaults.json) contains only a **disabled, neutral `worker_template`**. Before dispatch, the human or commander must register a real `provider`, `model`, `reasoning_effort`, tool capability, command, and availability in a user-maintained configuration. `available` is an operator assertion, not a live health check; the repository does not manage credentials or private launchers.

[`examples/registry.portable.json`](examples/registry.portable.json) contains disabled Codex CLI, Claude Code, and custom-command examples. **Copy the whole JSON file** to a configuration you manage, then configure and enable only the entries you intend to use. Do not copy just its `workers` array and drop the policy settings. Pass the **same `--config PATH`** and project `--state PATH` to each routing operation (global flags precede the subcommand):

```sh
cp examples/registry.portable.json ./my-routing.json
# Edit your copy: real provider/model/effort, command, capabilities, enabled/availability.
python3 scripts/route_worker.py --config ./my-routing.json --state .work/worker-routing/state.json create TASK.json
python3 scripts/route_worker.py --config ./my-routing.json --state .work/worker-routing/state.json route TASK_ID
python3 scripts/route_worker.py --config ./my-routing.json --state .work/worker-routing/state.json run TASK_ID
# The commander checks real artifacts and fills in REVIEW.json; never auto-accept.
python3 scripts/route_worker.py --config ./my-routing.json --state .work/worker-routing/state.json review TASK_ID REVIEW.json
```

Fill `TASK.json` from [`templates/adaptive-task.example.json`](templates/adaptive-task.example.json) with a real workspace, baseline, scope, and criteria. `route` previews without consuming an attempt; `run` recalculates and reserves before launch. Keep one ledger per project, and pass the same `--config` and `--state` to `inspect`, `recover`, `takeover`, and later operations. Examples do not supply model authorization; do not launch a billable run from an unreviewed example.

Adapter kinds are `codex_cli`, `claude_code`, generic `command`, and legacy `codex_worker`. Validate local CLI versions, model permissions, and behavior yourself; registering a text-only API does not grant it tools. [Hosts and adapters](docs/host-adapters.md) describes input, defaults, and argv conventions. [`examples/registry.original.json`](examples/registry.original.json) preserves the earlier two-GPT preset as an optional historical example, **not** the primary configuration. The older [implementation report](docs/adaptive-routing/IMPLEMENTATION_REPORT.md) is a historical snapshot, not the source of current setup instructions.

## Safety and review

Prompts, logs, and ledgers may contain sensitive project material: send only authorized context to the selected backend. Workers must not change authentication, credentials, private configuration, or delegate recursively. Role markers, scoped instructions, and static checks are not OS isolation. The commander retains architectural, security, and data-strategy decisions within human authorization. See [review and learning](docs/review-and-learning.md), the [worker contract](docs/worker-contract.md), and [security guidance](docs/security.md).

## Optional Jev screening

An opt-in `screen` stage can annotate reported Worker evidence before Commander review. It defaults OFF, preserves every item, and cannot accept work, change attempt counts, or update Worker suitability. See [usage and boundaries](docs/jev-screening.md) and the [repository pilot with limitations](experiments/jev-pilot-20260925/REPORT.md).

## Risk-based independent verification

The optional Verification & Deliberation Layer runs deterministic checks first, then 0/1/2 reviewers by risk; CRITICAL adds adversarial review and a human approval state. GPT and Claude reviewers use blind packets and a separate experience store. The existing Worker Router and two-execution limit remain intact; Judge decisions never use majority voting or replace Commander acceptance.

[Guide](docs/verification/README.md) · [Implementation and test report](docs/verification/IMPLEMENTATION_REPORT.md) · [Disabled registry example](examples/registry.verification.json)
