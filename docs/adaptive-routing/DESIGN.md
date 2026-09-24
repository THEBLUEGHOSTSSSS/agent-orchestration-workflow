# 第一版数据与接口设计

实现顺序：审计 → 本设计 → registry → 持久经验与任务账本 → profiler → 检索 → router → retry → diagnosis/review → experience/update → events → 静态校验 → A–M 场景 → 架构复核。

采用 Python 3.11+ 标准库；POSIX 文件锁。不是常驻服务，无自动循环调用。Strong Model 提交结构化任务和审核；代码计算可解释建议、执行有界一次调用、保存状态。不在脚本中另行调用 Astra 来冒充审核。

## 核心对象

- TaskSignature：domain/task_type/task_subtype/language/framework 是非空语义标签；complexity/reasoning_intensity/tool_intensity/risk_level/cross_module_scope/estimated_execution_volume 为 low/medium/high；verification_strength 为 weak/moderate/strong；scope 为 single_file/multi_file/repository；environment 为 local/ci/staging/production。Strong Model 填写，profiler 做结构化校验并保存 repo_context。
- WorkerDefinition：worker_id/provider/model/reasoning_effort/version/enabled/availability/adapter/capabilities/cost_profile/latency_profile/prior/manual_notes。公开配置不含密钥或私有端点。实际初始供应商沿用本地已配置 gateway，不冒称官方直连。
- RoutingDecision：selected_worker/reasoning_effort/selection_mode/routing_reason/historical_sample_count/historical_confidence/alternative_worker/historical_evidence_used/suitability；完整 worker 快照保存在实际 attempt。
- OutcomeDiagnosis：attribution（MODEL_RELATED/TASK_SPEC_RELATED/ENVIRONMENT_RELATED/TOOL_RELATED/DATA_RELATED/EXTERNAL_SERVICE_RELATED/UNKNOWN/NONE）、failure_type、severity（none/low/medium/high）、summary。接受时 attribution/type 为 NONE；失败必须有归因和说明。
- ExperienceRecord：experience_id/timestamp/logical_task_id/attempt_number/task_signature/worker/routing/execution/verification/outcome/diagnosis/retry/repair/source_kind/valid。真实调用返回先存 pending review；审核事务更新结果、归因和经验。source_kind 为 real/probe/synthetic，后两种不得用于真实能力学习。

## 共享接口（字典序列化）

`routing.models.load_config(path=None)`；`validate_signature(fields)`；`profile_task(fields, repo_context=None)`；`validate_diagnosis(fields, accepted)`。

`routing.selection.route(signature, experiences, config, *, now=None, previous_worker=None, diagnosis=None, manual_worker=None)` 返回 RoutingDecision。`now` 为 timezone-aware datetime。此函数只推荐，不消耗次数、不调用模型。统计字段：sample_count、confidence、first_pass_acceptance_rate、second_pass_acceptance_rate、overall_acceptance_rate、model_related_failure_rate、retry_rate、switch_away_rate、strong_model_takeover_rate、average_execution_cost、average_latency、average_repair_burden、accepted_tasks_per_cost。

经验约定：worker 为 registry 快照；execution 字段 duration_seconds/token_usage/estimated_cost/currency/tool_calls；verification 字段 tests_run/tests_passed/static_checker_result/reviewer_result/reviewer/evidence；outcome 字段 accepted/final_quality/worker_result_status；repair 字段 required/scope/severity/burden/takeover；retry 字段 required/action/previous_worker/next_worker。来源未核验、取消/污染/非模型失败不能作为模型能力负样本。

`routing.store.Store(path).read()` 与 `.transaction(mutator)` 原子读改写；首次不存在初始化，不容忍损坏文件自动重置。单个 JSON 内同时保存 tasks/aliases/work_keys/experiences/events。登记 alias 或子 fix task 继承逻辑任务额度；更换状态目录、伪造新的工作身份以及删除账本不能程序识别，必须明确列为 gap。

`routing.service.Workflow(state_path, config_path=None)` 提供 create / preview / run / review / takeover / recover / inspect。run 在锁内完成路由、额度预留和 RUNNING 状态落盘，然后在锁外一次性启动受信 registry adapter。未审核不得进行下一轮；中止、超时、启动失败保守占用次数。第二次拒绝即 TAKEOVER_REQUIRED。最终接管仍由主会话提供验证证据。

## 初始配置与策略

两个候选：gpt6_sol_xhigh 和 gpt56_sol_high。只有冷启动 priors 表达用户提供的任务倾向，不固定主次模型。价格/延迟未测量为 null。阈值集中 routing/defaults.json；max_worker_attempts 必须等于中央常量 2，拒绝其他值。

相关性为结构化匹配，限制领域与推理强度差异；经验使用时间衰减与版本折扣。少量样本向 prior 收缩；样本数只影响置信度和收缩，不作为加分项。环境/工具/数据/服务/任务描述问题剔除能力计分，但保留可观测记录。探索只在低风险、强验证、非 production、候选分差小且缺少样本时确定性选择，重试时不探索。人工指定优先于建议，但不能越过 enabled/availability、能力约束或两次上限。

## 调用与安全边界

初始 adapter 使用 `codex-worker WORKSPACE --model MODEL --reasoning-effort EFFORT`，由指挥者更新本地 launcher 支持这些按次参数，保留已有认证方式。其他供应商注册受信 command adapter（argv 列表，无 shell=True）。Worker 子进程带角色标记，受控 CLI 拒绝递归调用；同一 OS 用户可修改环境、账本、执行其他程序，故这不是安全隔离。不把凭据、原始日志或生产经验提交公共仓库。
