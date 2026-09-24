# agent-orchestration-workflow

**Humans set direction. Strong models make delegated judgments. Replaceable workers do the bulk execution.**

A workflow designed for high cost-effectiveness: reserve expensive reasoning and context for architecture, decisions, and critical review; delegate substantial reading, implementation, rewriting, testing, and iteration to capable workers with suitable costs. Optimize accepted useful work per budget, with traceable evidence.

[中文](README.md) | [Policy](AGENTS.md) | [Workflow](docs/workflow.md) | [Review and learning](docs/review-and-learning.md) | [Economics](docs/economics.md) | [Worker contract](docs/worker-contract.md) | [Security](docs/security.md)

## Adaptive Worker Routing with Experience Feedback

An executable Python 3.11+ / POSIX layer now profiles tasks, retrieves reviewed conditional experience, selects registered workers, reserves attempts before launch, and records commander review and attribution. Model switches preserve the two-attempt budget. No background calls, automatic acceptance, or claimed universal savings.

[Usage](docs/adaptive-routing/README.md) · [Architecture and validation report](docs/adaptive-routing/IMPLEMENTATION_REPORT.md) · [Registry](routing/defaults.json). The private worker launcher is not distributed.

## Current workflow at a glance

**The strong commander both directs and reviews. Workers get at most two rounds. Acceptance and project learning are mandatory.**

1. The human sets goals, budget and authority, retaining ultimate control.
2. The commander defines scope, baseline, criteria and stop conditions.
3. The worker executes once, with at most one requested rework.
4. The commander reviews each result; after a second failure, it directly repairs and verifies the work.
5. Record technical acceptance and scoped project experience; consult applicable verified lessons before related future work.

Roles are independent of Astra, Sol or a particular vendor. See [changes](CHANGELOG.md), the [delegation template](templates/delegation.md), [handoff](templates/handoff.md), [experience record](templates/experience-record.md), and [global adoption and rollback](docs/global-adoption.md).

### Run the static acceptance checker

Python 3.9+ with the standard library is sufficient. From the repository root:

```sh
mkdir -p records
cp docs/review-record.example.json records/my-task-review.json
# Fill actual attempts, commander review, criteria, evidence paths and SHA-256 hashes first.
python3 scripts/validate_review.py records/my-task-review.json --root .
```

The unexecuted example deliberately returns `NOT ACCEPTED` and exit code 1. A complete, consistent record returns 0; this is not proof of semantic correctness or enforcement against bypass calls. Run checker tests with `python3 -m unittest discover -s tests -v`. Historical records in `records/` bind to their original file versions: inspect them at the corresponding commit, and create a new acceptance record for new work. See [details and limits](docs/review-and-learning.md).

## The human-led pyramid

![Human at the apex, commander in the middle, replaceable workers at the base](assets/orchestration-pyramid.svg)

The human owns objectives, priorities, constraints, authorization, and ultimate acceptance. The current primary session acts as commander: it defines tasks, makes architecture and dispatch decisions, reviews critical evidence, and grants technical acceptance within that authority. The role is not hardcoded to Astra, Sol, or any vendor. If its capability is insufficient, it must disclose and escalate rather than pretend a model switch occurred. Workers complete bounded tasks and return artifacts and evidence.

Human control does not mean approval for every step. Existing authorization remains valid; ordinary implementation proceeds autonomously. Decisions that change goals, authority, or agreed budgets return to the human.

## Why this can be cost-effective

Move bulk execution to economical, capable workers; return compressed evidence packs; let a worker complete a bounded fix/test loop before reporting; require commander review in proportion to risk. This concentrates primary-model capacity on work where judgment adds the most value.

Compare **primary-model quota**, **money spent**, and **aggregate tokens** separately. Aggregate tokens can increase while primary-model consumption falls. Include coordination, retries, integration, technical review, and human time when comparing accepted results. Small tasks or unreliable workers can make delegation more expensive. This project has not published a controlled savings benchmark; see [the cost framework](docs/economics.md).

## Replace the model, retain the workflow

Worker is a role; `codex-worker` is the example invocation interface. A suitable adapter can connect a different provider or a local model with the required tools. The commander is also a role, not a fixed vendor requirement.

Preserve workspace boundaries, task input, artifacts, evidence, reporting, and exit-status expectations. Trial a replacement on the same representative tasks and acceptance criteria, checking tool use, quality, report accuracy, latency, and total cost. API compatibility alone does not establish execution compatibility. This repository distributes policies and templates, not a worker runtime or universal adapter. See [the worker contract](docs/worker-contract.md).

## Similar community practice

Artforartsake99's [Astra + 8 Deepseek 4.1 subagents. Insanely cheap tokens.](https://www.reddit.com/r/vibecoding/comments/1wg5ogw/astra_8_deepseek_41_subagents_insanely_cheap/) describes Astra coordinating DeepSeek workers. Our workflow had already been independently put into practice before that post. During this documentation update, we drew on its clear presentation of role separation. We cite it as a similar community practice, not as the origin of our workflow, which emphasizes human authority, replaceable execution models, and evidence-based acceptance. That anecdote is not our benchmark or a requirement to use those models or eight workers.

This is an independent community project under the MIT License, not an official vendor product.

## Mandatory review, two-round limit, and learning

Before every dispatch, record a stable task ID, acceptance criteria, allowed scope, baseline, attempt number, and relevant verified project experience. After every submission, the commander records evidence, defects, and an `accept`, `rework`, `takeover`, or `blocked` decision. Each logical task permits at most two Worker execution rounds: the initial round and one commander-requested correction. A second failed submission requires commander takeover; renaming the task, changing worker/model/session, or revising the goal does not reset unresolved work.

Every delegated task, including failed or blocked work, requires a project-local experience record. Small direct work may use one brief existing project log entry. Formats are optional; duties are mandatory. See [review and learning](docs/review-and-learning.md) and [structured handoff](docs/structured-handoff.md). An optional [static review checker](scripts/validate_review.py) checks the round limit, takeover records, acceptance evidence and experience files. It cannot prevent bypass calls and is not an automatic scheduler or runtime model switcher; cost savings remain unmeasured.

## Lifecycle

The six stages are Understand, Decide, Explore, Execute, Verify, and Finalize. The commander normally owns the first two and the last; the worker is preferred for substantial exploration and execution; verification is shared, with worker breadth and commander scrutiny proportional to risk.

Delegation is a semantic decision, not a line-count rule. Ask whether commander attention would create meaningfully more value than worker execution. Small, obvious, interactive, or judgment-heavy tasks often remain with the commander. Large searches, multi-file changes, bulk transformations, and repeated fix/test loops are stronger delegation candidates.

Six domain modes define responsibility boundaries:

| Mode | Commander owns | Worker handles |
| --- | --- | --- |
| SOFTWARE | Requirements, architecture, APIs, data and security decisions | Exploration, implementation, debugging, tests, migrations |
| PAPER | Thesis, novelty, claim strength, evidence meaning, final rhetoric | Evidence extraction, number and consistency checks, local editing |
| RESEARCH | Research question, synthesis, implications, recommendations | Collection, comparison, contradictions, uncertainty mapping |
| DOCUMENT | Audience, structure, conclusions, final quality | Extraction, drafting, tables, repetitive edits, normalization |
| LEARNING | Explanation, intuition, misconception diagnosis, interaction | Bulk calculations, exercises, answer checking, examples |
| DECISION | Trade-offs, personalized implications, final recommendation | Facts, specifications, comparisons, evidence gathering |

For large inputs, use progressive disclosure: the worker reads broadly and returns a traceable context pack; the commander inspects the pack and requests only the raw evidence needed for critical decisions. Within each bounded execution round, a worker may run `inspect -> execute -> verify -> diagnose -> fix -> reverify -> report` under explicit stop conditions. Internal self-checks do not create extra rounds.

Completion must be evidence-based. A dispatch consumes a round when launched; interrupted or uncertain execution counts conservatively, while waiting on the same running execution does not. Required checks marked not-run make the task blocked, not accepted. Worker self-report, exit status `0`, or `APPROVE` text is never commander acceptance. Final delivery requires commander acceptance against the criteria on the current artifacts and the experience record; human ultimate acceptance remains separate.

## Runtime prerequisite

Provide your own `codex-worker` executable on `PATH`. It must accept the workspace as its first argument, read the prompt from standard input, write its report to standard output, and return a non-zero status on failure.

```sh
command -v codex-worker >/dev/null 2>&1 || {
  echo "codex-worker is required but was not found on PATH" >&2
  exit 1
}
```

```sh
cat <<'WORKER_PROMPT' | codex-worker "$PWD"
MODE:
SOFTWARE

TASK ID / ATTEMPT:
[stable task ID] / [1 or 2; two total Worker rounds maximum]

BASELINE / EXPERIENCE / STOP CONDITIONS:
[actual revision or artifact baseline] / [verified lessons or none] / [time limit and blockers]

OBJECTIVE:
Complete a bounded, locally verifiable task.

TASK:
Inspect relevant files, implement the scoped change, and verify it.

REQUIREMENTS:
- Preserve unrelated content and behavior.
- Do not expand authority or publish externally.

ACCEPTANCE CRITERIA:
- The requested behavior is implemented.
- Checks actually pass, or missing verification is reported accurately.

AUTONOMY:
Perform bounded inspect -> execute -> verify -> fix -> reverify self-checks.
Set a stop condition before launch; stop on external blockers or the time limit.

OUTPUT:
Return a compact, evidence-backed report for commander review and project-local experience capture.
WORKER_PROMPT
```

Without a compatible executable, use [the delegation template](templates/delegation.md) manually in a clean dedicated workspace: remove sensitive and irrelevant material, submit only reviewed content to your chosen execution system, then inspect the result yourself. Do not auto-trust arbitrary directories or create an unreviewed compatibility shim.

## Security and adoption

For use across projects, see [global adoption and rollback](docs/global-adoption.md).

Instructions are not a sandbox. A third-party provider may process submitted prompts and accessible material. Review outbound content and the provider's retention, training, logging, location, and tool-access terms. Never ask the worker to inspect API keys, alter credentials or authentication, alter Codex configuration, alter private worker configuration, recursively launch another worker, or delegate again.

Review and merge this policy with an existing project's instructions. Do not overwrite an existing `AGENTS.md` or install this as a user's global policy by default. Prefer a clean, least-privilege workspace.

Acceptance of local work is separate from authorization to push, open a pull request, publish, message others, or make a repository public. Existing authorization remains valid without repeated confirmation. Ordinary local edits, checks, and commits proceed within task scope. If attempt two fails, the commander directly repairs, tests, and reviews; it may take over earlier. A genuinely independent scope gets a new task ID only with a recorded rationale and lineage.

See [security guidance](docs/security.md), [templates](templates/delegation.md), and the explicitly illustrative [software](examples/software-task.md) and [paper](examples/paper-task.md) examples. Contributions follow [CONTRIBUTING.md](CONTRIBUTING.md). Licensed under the [MIT License](LICENSE).
