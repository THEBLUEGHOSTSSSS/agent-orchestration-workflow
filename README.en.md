# agent-orchestration-workflow

A portable policy for orchestrating a high-value commander and a high-throughput external execution worker. The commander owns judgment, architecture, risk, critical review, and final acceptance. The worker handles bounded reading, implementation, rewriting, testing, verification, and iteration.

This is an independent community project, not an official product of any vendor. It does **not** distribute the `codex-worker` implementation and makes no measured cost, speed, or performance guarantee.

[中文](README.md) | [Policy](AGENTS.md) | [Workflow](docs/workflow.md) | [Worker contract](docs/worker-contract.md) | [Security](docs/security.md)

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

For large inputs, use progressive disclosure: the worker reads broadly and returns a traceable context pack; the commander inspects the pack and requests only the raw evidence needed for critical decisions. A bounded worker task should run `inspect -> execute -> verify -> diagnose -> fix -> reverify -> report` before returning.

Completion must be evidence-based. Reports list files changed, checks actually run, important outputs, checks not run, residual risks, and decisions left to the commander. Never treat a planned check or an unverified worker claim as proof.

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
Perform reasonable inspect -> execute -> verify -> fix -> reverify loops.

OUTPUT:
Return a compact, evidence-backed report.
WORKER_PROMPT
```

Without a compatible executable, use [the delegation template](templates/delegation.md) manually in a clean dedicated workspace: remove sensitive and irrelevant material, submit only reviewed content to your chosen execution system, then inspect the result yourself. Do not auto-trust arbitrary directories or create an unreviewed compatibility shim.

## Security and adoption

Instructions are not a sandbox. A third-party provider may process submitted prompts and accessible material. Review outbound content and the provider's retention, training, logging, location, and tool-access terms. Never ask the worker to inspect API keys, alter credentials or authentication, alter Codex configuration, alter private worker configuration, recursively launch another worker, or delegate again.

Review and merge this policy with an existing project's instructions. Do not overwrite an existing `AGENTS.md` or install this as a user's global policy by default. Prefer a clean, least-privilege workspace.

Acceptance of local work is separate from authorization to push, open a pull request, publish, message others, or make a repository public. Existing authorization remains valid without repeated confirmation. Ordinary local edits, checks, and commits proceed within task scope.

See [security guidance](docs/security.md), [templates](templates/delegation.md), and the explicitly illustrative [software](examples/software-task.md) and [paper](examples/paper-task.md) examples. Contributions follow [CONTRIBUTING.md](CONTRIBUTING.md). Licensed under the [MIT License](LICENSE).
