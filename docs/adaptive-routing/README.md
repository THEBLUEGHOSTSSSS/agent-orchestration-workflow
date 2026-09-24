# Adaptive Worker Routing with Experience Feedback

Human 决定目标与授权；Strong Model 负责策略、路由、审核、归因与最终接管；Worker 只做有边界的执行。角色不依赖固定模型名称。

第一版使用 Python 3.11+ 标准库、POSIX 文件锁和原子 JSON 账本，适用 macOS/Linux。没有数据库服务、模型训练、向量库或后台自动调用。运行命令才会派发。Windows 原生执行尚未验证。

## 从一个任务开始

```sh
# 在项目目录中，将 ROUTER 替换为安装后的绝对路径
ROUTER="/path/to/agent-orchestration-workflow/scripts/route_worker.py"
CONFIG="/path/to/your/registry.json"
# 从 examples/registry.portable.json 复制配置，填写并启用所需 Worker
python3 "$ROUTER" --config "$CONFIG" profile task-signature.json
python3 "$ROUTER" --config "$CONFIG" create task.json
python3 "$ROUTER" --config "$CONFIG" route T42
python3 "$ROUTER" --config "$CONFIG" run T42 --timeout 300
# 强模型检查真实成果、运行必要检查后，填写 review.json
python3 "$ROUTER" --config "$CONFIG" review T42 review.json
python3 "$ROUTER" --config "$CONFIG" validate
```

默认账本为当前目录 `.work/worker-routing/state.json`。同一项目必须始终使用同一账本；恢复会话不要更换路径。可通过命令前的 `--state PATH --config PATH` 指定账本及注册表。配置省略时读取 `routing/defaults.json`，其中模板默认停用，必须先注册并启用实际 Worker。配置参数应在各次操作中保持一致。使用 `inspect T42` 看任务，`inspect` 看完整账本。账本可能包含项目敏感信息，不应直接公开。

`route` 只是建议；`run` 在文件锁内重新计算并保留实际决定。强模型可以在启动时使用 `--worker WORKER_ID` 覆盖选择；Human 的明确指定优先。自动建议不能替代强模型对风险与能力的判断。

`templates/adaptive-task.example.json` 是待填写模板；workspace、baseline、目标、范围和验收条件必须与真实任务一致。Task Profiler 校验强模型提供的语义字段，不偷偷增加一次模型调用，也不声称自动理解任意提示。

## 两轮执行与审核

- 首轮启动前事务写入 `RUNNING`，次数立即消耗。退出码为零仍是 `AWAITING_REVIEW`。
- `review` 必须包含审核者、全部原始验收项、实际文件证据及 SHA-256、归因与处理决定。
- 首轮失败可 `retry`，必须提供完整 handoff；低级局部问题倾向同模型，推理/架构/循环等失配倾向替换模型。
- 第二次仍失败进入 `TAKEOVER_REQUIRED`，`run` 无法第三次启动。强模型自行修改验证后用 `takeover` 记录最终证据。
- 别名、已声明 parent/fix task 和已知 work key 继承原额度。人工指定模型也不增加额度。
- 中断时先确认旧进程已经停止，再用 `recover T42 --reason ...` 保留已消耗次数并转入待审核；不能直接重跑。

`review.json` 最小形状：

```json
{
  "reviewer": "actual commander session",
  "accepted": true,
  "action": "accept",
  "diagnosis": {"attribution": "NONE", "failure_type": "NONE", "severity": "none", "summary": "Verified against evidence"},
  "criteria": [{"id": "C1", "status": "passed", "observation": "Actual check and result"}],
  "evidence": [{"path": "result.txt", "sha256": "actual SHA-256"}],
  "static_checker_result": "passed",
  "final_quality": 1,
  "repair": {"required": false, "scope": null, "severity": "none", "burden": 0}
}
```

失败归因用 `MODEL_RELATED / TASK_SPEC_RELATED / ENVIRONMENT_RELATED / TOOL_RELATED / DATA_RELATED / EXTERNAL_SERVICE_RELATED / UNKNOWN`。成功使用 `NONE`。失败类型、严重度与解释由强模型判断；脚本只校验结构和矛盾，不能自动证明归因正确。

需要重试时设 `accepted=false, action=retry`，criteria 如实为 `failed/not_run`，并增加 handoff：`files_inspected, files_modified, current_diff, tests_run, test_results, previous_approach, what_worked, what_failed, known_bad_approaches, remaining_work, constraints`。原任务 ID、轮次、目标、范围、验收标准、原计划、repo context、前一 Worker 和诊断由程序添加，调用者不能覆盖。第二次失败使用 `action=takeover` 或如实 blocked，程序保留接管状态。

接管记录包含 `reviewer, summary, criteria, evidence, static_checker_result, repair_burden`。burden 默认约定为强模型修复时间（分钟），不要混用 token 与分钟；未知普通审核负担可为 null，完成接管须填写实际估计。接管成功不会给失败 Worker 记成功。

## 真实经验与经济性

每次执行生成一条 pending experience；强模型审核后才进入可检索经验。`source_kind=probe/synthetic`、未审核、取消、需求中途变化、损坏数据、非模型失败不会进入能力评分。可用 `invalid_task=true, invalid_reason=...` 标记污染样本。历史 Markdown 经验不自动转换成训练信号。

只在相似任务上下文比较 Worker。对 domain、任务类型族、推理强度先做排除，再按 subtype、语言、框架、范围等结构字段匹配。时间指数衰减、版本变化折扣、过期窗口、独立逻辑任务样本数、向 prior 收缩共同防止旧经验和 2/2 小样本支配决策。每次决定公开各候选评分、排除原因、引用的经验 ID 与 confidence。

公开版不预设模型优先级。用户配置的模型倾向只是 prior；没有永久主 Worker。低风险、强验证、非生产、候选差距小且已有历史时，才允许确定性的 `EXPLORE`。高风险不做探索，但冷启动仍可能使用无历史的 prior，强模型必须判断其适用性。

执行成本未知时保留 null，不伪装成零。审核时可附 `execution_metrics`，包含 `estimated_cost, currency, token_usage, tool_calls, source`，并把对应凭据加入 evidence。不同币种不能直接比较。ROI 是观察性指标，包含修复负担；第一版没有验证任何通用节省百分比。

## 新 Worker

Codex CLI、Claude Code CLI 与其他模型的完整配置见 [宿主适配说明](../host-adapters.md) 和 `examples/registry.portable.json`。推理强度是供应商自定义的非空标签，`default` 表示不传原生 CLI 覆盖参数；无需支持 xhigh。

复制注册表一条记录，指定唯一 worker_id、provider、model、reasoning_effort、version、能力、可用性和 prior。`codex_worker` adapter 使用 `command + workspace + --model + --reasoning-effort`；本地 launcher 必须支持这些参数。其他供应商可注册 `command` adapter，参数列表支持 `{workspace}/{model}/{reasoning_effort}` 替换，stdin 接收结构化任务；不会经过 shell。命令和配置必须由人或强模型维护，Worker 不可修改。

新模型通过冷启动、受控探索和真实审核逐步积累经验。配置中的 available 是操作员声明，不是实时健康探测；服务失败需要审核归因。密钥仍由外部 adapter 管理，仓库不包含供应商凭证或私有 launcher。

## Enforcement 边界

受控入口在同一未篡改账本内强制两轮、审核门槛、身份映射和原子更新。静态检查器检查记录一致性及当前最终证据摘要；历史失败证据可随修复而过时，不重新要求其文件摘要仍相同。

同一系统用户仍能直接调用其他 launcher、换账本、删除记录、去掉角色环境变量或谎报全新任务。第一版没有操作系统权限隔离、不可篡改日志或语义身份判定。`ADAPTIVE_WORKER_ROLE=worker` 会拒绝路由 CLI，但不是安全沙箱。scope 是明确约定与审核责任，不能阻止恶意命令访问其 OS 权限内的文件。

静态一致性通过不等于强模型实际审核，更不等于 Human 最终验收。完整审计、验证矩阵与剩余风险见 [IMPLEMENTATION_REPORT.md](IMPLEMENTATION_REPORT.md)。
