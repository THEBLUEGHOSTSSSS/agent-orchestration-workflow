# agent-orchestration-workflow

**Human → Commander → Worker：人掌握目标与最终决定，Commander 指挥并审核，可替换的 Worker 执行有界任务。**

这是一个与宿主工具、模型供应商无关的协作策略与可选的自适应路由实现。Commander 可以运行在 Codex、Claude Code 或其他具备相应能力的环境；Worker 后端可以独立选择。高价值判断、架构和关键复核留给 Commander；大量阅读、实现、改写、测试与自检交给合适的 Worker。小任务无需强行委派。

[English](README.en.md) · [完整规则](AGENTS.md) · [宿主与适配器](docs/host-adapters.md) · [审核与经验](docs/review-and-learning.md)

## 工作闭环

1. 人确定目标、预算、授权和最终验收；Commander 确定任务边界、基线、验收条件、停止条件和可用 Worker。
2. 路由器参考任务特征与**已审核、适用**的项目经验提出可解释的候选建议；Commander 审查并可覆盖选择。首次启动前保留执行次数。
3. Worker 在授权范围内执行并返回制品、检查结果和不确定性；Commander **每轮**检查实际证据，记录缺陷和决定，不能凭退出码或自报验收。
4. 同一逻辑任务最多 **两轮 Worker 执行**（首次加最多一次要求修正）；换模型、宿主或任务名称不重置额度。第二轮仍不合格时 Commander 直接修复和验证，或如实标记阻塞。
5. 验收与项目本地经验记录均为成功交付的必要条件。失败须区分模型问题与需求、环境、工具、数据、外部服务等原因；仅经审核且适用的经验用于后续选择。

目标是提高单位成本下的**已验收有用成果**，不是保证省钱。主模型额度、实际费用、总 token、复核与返工成本须分开核算；没有自动节省率或跨供应商质量保证。静态记录检查不是安全沙箱，也不能替代 Commander 的实质审核。

## 配置与使用

路由器要求 Python 3.11+ 和 POSIX 环境（macOS/Linux）。默认 [`routing/defaults.json`](routing/defaults.json) 仅含**禁用的中性 `worker_template`**；执行前须由人或 Commander 在自有配置中登记真实的 `provider`、`model`、`reasoning_effort`、工具能力、命令及可用状态。配置 `available` 只是操作员声明，并非实时健康检测；仓库不代管认证或私有启动器。

[`examples/registry.portable.json`](examples/registry.portable.json) 包含默认禁用的 Codex CLI、Claude Code 和自定义命令示例。**复制完整 JSON 配置**到自己维护的文件，只启用并配置准备使用的条目；不要只复制 `workers` 数组而遗漏策略字段。每次路由操作均显式传入同一 `--config PATH` 和项目账本 `--state PATH`（全局选项在子命令前）：

```sh
cp examples/registry.portable.json ./my-routing.json
# 编辑自己的配置：实际 provider/model/effort、命令、能力和 enabled/availability。
python3 scripts/route_worker.py --config ./my-routing.json --state .work/worker-routing/state.json create TASK.json
python3 scripts/route_worker.py --config ./my-routing.json --state .work/worker-routing/state.json route TASK_ID
python3 scripts/route_worker.py --config ./my-routing.json --state .work/worker-routing/state.json run TASK_ID
# Commander 检查真实产物并填写 REVIEW.json；不可自动验收。
python3 scripts/route_worker.py --config ./my-routing.json --state .work/worker-routing/state.json review TASK_ID REVIEW.json
```

`TASK.json` 应基于 [`templates/adaptive-task.example.json`](templates/adaptive-task.example.json) 填写真实工作区、基线、范围和验收条件。预览 `route` 不消耗轮次，`run` 在启动前重新计算并保留轮次；保持同一项目账本。后续 `inspect`、`recover`、`takeover` 等操作同样带上原 `--config` 和 `--state`。配置样例不是即开即用的模型授权；不要用样例直接发起收费调用。

适配器类型为 `codex_cli`、`claude_code`、通用 `command` 以及兼容旧启动器的 `codex_worker`。本机工具、模型权限和执行行为须由使用者自己核验；文本生成 API 不会仅凭注册配置获得工具能力。[宿主与适配器说明](docs/host-adapters.md) 详述输入契约、默认值与命令参数。[`examples/registry.original.json`](examples/registry.original.json) 保存早期双 GPT 预设，仅供可选的历史参考，不是默认推荐。早期的[完整实现报告](docs/adaptive-routing/IMPLEMENTATION_REPORT.md)是当时版本的快照，不作为现行配置说明。

## 安全与审核边界

任务提示、日志与账本可能包含敏感项目资料；仅向已授权的后端发送必要内容。Worker 不得改动认证、凭据、私有配置或递归委派；角色标记、任务范围和静态检查不构成操作系统隔离。高级架构、安全和数据策略决策由 Commander 在人的授权内承担。参考[审核与学习规则](docs/review-and-learning.md)、[Worker 契约](docs/worker-contract.md)与[安全指南](docs/security.md)。

## 可选 Jev 语义筛查

已提供默认关闭的 Jev 辅助阶段：Worker 返回后，可以显式运行 `screen`，再由 Commander 按原流程审核。它只提供证据支持性判断，不自动验收、不影响两轮执行额度，也不写入 Worker 适配经验。[接入与边界](docs/jev-screening.md) · [本项目对照试验及限制](experiments/jev-pilot-20260925/REPORT.md)。

## 风险分层与独立审核

新增可选 Verification & Deliberation Layer：LOW 先跑确定性检查；MEDIUM/HIGH 配置 1/2 个盲审 Reviewer；CRITICAL 增加对抗审核和人工批准状态。支持 GPT/Claude，保留原 Worker Router 和两轮上限。Reviewer 经验与 Worker 经验分开，Judge 按证据仲裁，不做多数投票。

[Guide](docs/verification/README.md) · [Implementation and test report](docs/verification/IMPLEMENTATION_REPORT.md) · [Disabled registry example](examples/registry.verification.json)
