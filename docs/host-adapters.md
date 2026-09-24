# Hosts and worker adapters

The **human** authorizes goals and budgets; the **commander** scopes, dispatches, reviews and technically accepts work; a **worker** executes only its bounded task. A commander may use Codex, Claude Code, or another capable host. Its host does **not** determine the worker backend. [`AGENTS.md`](../AGENTS.md) is the shared policy; [`CLAUDE.md`](../CLAUDE.md) imports it for Claude Code. Follow the same acceptance and learning rules in every host, without treating instruction files as a sandbox.

## Choose a registry

Requires Python 3.11+ and a POSIX environment (macOS/Linux). The built-in [`routing/defaults.json`](../routing/defaults.json) is deliberately neutral: its only entry, `worker_template`, is disabled and unavailable. There is no usable model until a human or commander configures a tool-capable worker, sets `provider`, `model`, `reasoning_effort`, capabilities and executable argv, then enables the entry and marks it available. Never put credentials in the registry or task prompt; use the tool's authorized external authentication. Availability is an operator declaration, not a connectivity test.

Copy the **entire** [`examples/registry.portable.json`](../examples/registry.portable.json) to your own configuration. It contains disabled examples for `codex_cli`, `claude_code`, and `command`; configure and enable **only** entries you intend to run. Preserve the other top-level policy fields. Use one project ledger and pass the same configuration and state paths as **global options before every routing subcommand**:

```sh
cp examples/registry.portable.json ./my-routing.json
# Edit ./my-routing.json; this copy remains disabled until you configure and enable entries.
python3 scripts/route_worker.py --config ./my-routing.json --state .work/worker-routing/state.json create TASK.json
python3 scripts/route_worker.py --config ./my-routing.json --state .work/worker-routing/state.json route TASK_ID
python3 scripts/route_worker.py --config ./my-routing.json --state .work/worker-routing/state.json run TASK_ID
python3 scripts/route_worker.py --config ./my-routing.json --state .work/worker-routing/state.json review TASK_ID REVIEW.json
```

Make `TASK.json` from [`templates/adaptive-task.example.json`](../templates/adaptive-task.example.json), using the real workspace, baseline, scope, and acceptance checks. Review actual artifacts and logs before filling `REVIEW.json`. Also pass the same `--config` and `--state` when calling `inspect`, `recover`, `takeover`, or `validate`; `route` only previews and `run` reserves an attempt before starting. Do not test a billable service without authorization. The earlier two-GPT preset in [`examples/registry.original.json`](../examples/registry.original.json) is an optional historical example, not the main registry; the older [implementation report](adaptive-routing/IMPLEMENTATION_REPORT.md) describes its original snapshot.

## Supported adapter kinds

All `adapter.command` values are **argv arrays**, not shell strings. The router launches them with the task workspace as working directory; the bounded task is sent as JSON on standard input. The JSON includes task identity, attempt number, baseline, objective, scope, criteria and handoff; stdout/stderr are logged for commander review. Executables must be on `PATH` (or use an operator-controlled command path), authenticated by the operator, and capable of completing the task with authorized tools. The router does not inject credentials or parse a success claim into automatic acceptance.

| Kind | Starting `adapter.command` | Invocation and defaults |
| --- | --- | --- |
| `codex_cli` | `["codex"]` | Appends `exec --sandbox workspace-write --json`, optional `--model MODEL`, optional `--config model_reasoning_effort=...`, then `-` to read stdin. `model: "default"` omits the model flag; `reasoning_effort: "default"` omits the effort setting. A custom effort is passed through Codex's TOML config argument; use a value supported by your installed CLI/model. |
| `claude_code` | `["claude"]` | Appends `--print --output-format json`, optional `--model MODEL`, and optional `--effort EFFORT`. `default` omits each corresponding flag. Effort is a provider-specific string; confirm that the chosen Claude Code version and model support it. **Real Claude Code execution has not been tested here.** |
| `command` | Your executable and fixed args, e.g. `["your-worker-adapter"]` | Substitutes `{workspace}`, `{model}`, `{reasoning_effort}` in argv entries when present; sends the same structured JSON over stdin. Implement your own tool-capable adapter contract; no shell expansion or automatic provider API integration. |
| `codex_worker` | Your legacy launcher argv | Appends the workspace, optional `--model MODEL` and optional `--reasoning-effort EFFORT`; `default` omits those flags. The launcher is **not** included. |

The registry's `reasoning_effort` and `model` values are **per worker**, not inherited from the commander. Set actual provider/model/effort as needed; `default` explicitly means *defer to the installed tool's configuration*, not a guaranteed model or effort. Native adapters use the installed CLIs; their availability and runtime behavior depend on local installation, permissions, and CLI versions. Custom wrappers must handle input, tool use, bounded execution, artifacts, and error reporting themselves. An arbitrary text-only API cannot execute workspace tasks just because it appears in the registry.

## Review, costs and boundaries

Each logical task has at most **two worker attempts**, including an initial execution and at most one commander-requested correction. A model or host switch cannot reset that count. The commander inspects work and checks after **every** attempt, attributes failures (model versus specification, environment, tools, data or service), and records a decision. After a second failed attempt it repairs and validates directly or reports blocked; no third worker call. Acceptance and a project-local experience record are both required for successful delivery; only reviewed, applicable experience should influence future routing. See [review and learning](review-and-learning.md).

The router is a convenience and an auditable ledger, not an OS sandbox or a universal model adapter. Track actual primary-model quota, money, aggregate tokens, and review/repair effort separately. Unknown costs stay unknown; there is no automatic or universal savings claim. The operator must approve any paid use and decide what project material can leave the machine.

## Verified boundary and sources

The portable revision passes 52 local tests, including fake-executable integration of all four adapters (argv, stdin JSON, workspace cwd and mandatory review gate). Installed `codex exec --help` and `claude --help` were checked. This is not a paid end-to-end Claude Code/provider certification; local permissions and authentication remain configured by the operator. Native adapters never add permission-bypass flags. Claude Code print mode can deny tools that have not been authorized; configure the intended permissions in your host before use.

When using `model=default`, the stored model label cannot detect changes in the host's hidden default. Prefer explicit model names for comparative learning; update the registry version or worker identity when changing underlying provider/model settings. The `provider` field is metadata, not an endpoint switch: configure the actual provider in the trusted runner.

Official references: [Claude Code memory and imports](https://code.claude.com/docs/en/memory), [programmatic execution](https://code.claude.com/docs/en/headless). Codex command options were checked against the installed CLI. No instruction-file format proves sandbox isolation or semantic acceptance.
