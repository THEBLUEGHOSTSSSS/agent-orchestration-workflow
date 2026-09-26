# Verification & Deliberation Layer

这是现有 Worker Router 之上的可选验证阶段。Worker Router 决定谁执行；Reviewer Router 决定谁审核；风险策略决定审核深度。两者使用独立经验。Commander 仍承担最终技术验收，人保留最终权力。当前支持 GPT 和 Claude Reviewer，不使用 Gemini。

## 开始使用

1. 复制 `examples/registry.verification.json`，配置真实 Worker，以及可用的 GPT/Claude Reviewer；样例全部禁用，不会隐式收费。模型版本由注册表指定，核心代码不固定版本。
2. 基于 `templates/verification-task.example.json` 填写任务。八个风险值均为 `[0,1]`，由 Commander 根据任务和已核实历史填写。`worker_historical_failure_rate` 是有来源的输入，不会自动从全局失败数推断。配置实际验收断言；文件存在不能代替行为正确。
3. 保持原项目账本，显式运行下列命令。密钥只通过 `OPENROUTER_API_KEY` 环境变量传入，不放进配置、任务或日志。

```sh
python3 scripts/route_worker.py --config my-routing.json --state .work/worker-routing/state.json create task.json
python3 scripts/route_worker.py --config my-routing.json --state .work/worker-routing/state.json run TASK_ID
python3 scripts/route_worker.py --config my-routing.json --state .work/worker-routing/state.json verify TASK_ID
# Commander 检查真实文件和审核意见，填写既有 review 契约。
python3 scripts/route_worker.py --config my-routing.json --state .work/worker-routing/state.json review TASK_ID review.json
python3 scripts/route_worker.py --config my-routing.json --state .work/worker-routing/state.json validate
```

`verify` 返回审核 session 和 Judge 建议；不会自动接受、重试或消耗 Worker 第二轮。任务创建时冻结审核策略，改配置不会降低既有任务门槛。没有 `verification` 字段的历史任务继续遵循原流程；新建需要此层的任务必须带该字段。

## 策略与预算

| 风险 | 必需自动检查 | 普通 Reviewer | 对抗 Reviewer | 人工状态 |
|---|---|---:|---|---|
| LOW | 是 | 0 | 默认关闭 | 无默认人工确认 |
| MEDIUM | 是 | 1 | 默认关闭 | 同上 |
| HIGH | 是 | 2 | 可配置开启 | 同上 |
| CRITICAL | 是 | 2 | 必需，独立调用 | 必需 |

规则集中在 `routing/verification_policy.json`。默认加权均值阈值为 0.25/0.5/0.75；安全、不可逆性、外部副作用另有风险下限。总费用按 USD 计，默认 $2、40000 token、600 秒墙钟、6 次 Reviewer 调用；这些是样例默认值，应按真实项目调节。墙钟从任务创建开始，包含等待时间。

每次调用前做保守资源预留，已知实际值更高时按较高值计费，不返还预留。未知费用保持 null，不能称为零费用。实际总支出和 token 超额阻止后续调用及验收；供应商真实扣费无法被本地声明上限硬性限制，须结合供应商账户限额。不要将预算预留当成账单。

`max_revision_rounds` 只能为 0 或 1，不可突破原来的两次 Worker 执行。每个 attempt 的 worker/takeover 各最多两次 verification session；审核失败不会自动重试模型。严重分歧、缺少配置、超时、无效 JSON、证据过期或预算不足均不能 PASS。

## 盲审接口

Reviewer 只收到原始目标、原始验收标准、Commander 提供的必要 context、指定 UTF-8 文本制品及哈希、确定性检查结果、其专业角色。不会附带 Worker 身份、推理、计划、自评或其他 Reviewer 意见。人工填写的 context 和制品本身仍可能泄露来源；须由 Commander 控制。

支持九个角色：requirements、correctness、code、security、architecture、adversarial、ux、business、evidence，均以 `_reviewer` 结尾。高风险使用不同普通角色；对抗角色使用独立提示，寻找反例和遗漏约束。当前仅传文本，不能声称已做截图视觉、视频、音频实审。

OpenRouter 适配器请求结构化输出、不给工具、无自动重试、拒绝重定向，验证返回模型身份、角色、证据、数值和结果 schema。别名快照可登记 `allowed_resolved_models`，必须属于相同模型家族。

Codex/Claude Code 可通过 `command` bridge 接入：

```json
{"kind":"command","command":["/absolute/path/to/review-bridge","--model","{model}"]}
```

Bridge 在新临时目录启动，从 stdin 读取完整 JSON packet，stdout **只能**返回：

```json
{
  "resolved_model":"实际模型标识",
  "usage":{"cost_usd":null,"total_tokens":null},
  "result":{
    "verdict":"PASS","confidence":0.8,"issues":[],
    "evidence":["文件或检查证据"],"recommended_action":"accept",
    "reviewer_specialty":"correctness_reviewer"
  }
}
```

`issues` 每项要求 id、severity（low/medium/high/critical）、description、非空 evidence 数组。FAIL 必须有 issues；PASS 必须无 issues 且 action=accept。UNCERTAIN 不得推荐 accept。这是通用 bridge 契约，不能直接把 CLI 任意自然语言输出冒充此接口。子进程环境会清除凭据；bridge 认证需 Commander 明确配置，不可由 Reviewer 修改凭据。新 cwd、超时、输出限额和角色标记均不构成操作系统沙箱。

## 修订、仲裁与人工状态

- `minor_fix` / `strategy_failure`：Commander 确认归因并批准 retry 后，路由保留原 Worker；记录 `VERIFICATION_RETRY_SAME`，不会伪装成人工指定。
- `worker_mismatch`：Commander 必须独立确认为严重模型相关失败，既有 Router 才选择合格替代者；没有替代者不会制造新的模型能力。
- `ambiguous_task`：retry review 必须给出 `task_clarification`，通过 handoff 解释任务，不能修改原验收标准。
- `high_risk_uncertainty` / 分歧：升级给 Commander 查证，不能凭多数 PASS 放行。
- 第二次执行失败：Commander 接管修复，再 `verify TASK_ID --kind takeover`，最后沿用 `takeover` 验收契约。

CRITICAL 的完整审核通过后为 `HUMAN_APPROVAL_REQUIRED`。取得真实人的决定后记录：

```json
{"session_id":"从 verify 返回值复制","actor":"实际决策者","reason":"实际理由","approved":true}
```

运行 `verification-approve TASK_ID approval.json`，再由 Commander 执行 `review`。这是操作员声明接口，不具备身份认证；工具不能自行冒充人。批准绑定制品哈希，变更后旧批准失效。

进程中断后，确认旧进程已停止，再 `verification-recover TASK_ID --reason "实际原因"`。已预留费用和 Reviewer 次数不清零。正常阻塞可用原 `review` action=blocked 记录；不要改账本绕过门槛。

## 分开的经验学习

既有 Worker experience 保持原字段，新增 `deliberation`（风险、session、资源、修订次数、结果）。新增顶层 `reviewer_experiences`，每条含专业角色、模型及快照、Worker 模型、结论、置信度、checks、Judge、人工决定、最终结果。

审核意见初始 `confirmed=false`，不拿多数意见当真值。Commander 根据测试、人的判断或独立制品检查核实后，执行 `verification-feedback TASK_ID feedback.json`：

```json
{"experience_id":"对应记录 ID","actor":"commander","correct":true,
 "basis":"commander_artifact_review","reason":"具体如何核实",
 "evidence":[{"path":"证据文件相对路径","sha256":"实际文件哈希"}]}
```

仅 real、valid、confirmed 记录进入同领域/任务类型/角色/模型的可靠性估计；probe/synthetic、无效任务、自己执行同一模型的记录不用于该估计。使用 90 天半衰期和 4 个中性先验样本抑制小样本过拟合；高风险不挪用低风险经验。反馈仍依赖 Commander 判断，不能自动证明判断准确。

完整架构、测试和局限：[IMPLEMENTATION_REPORT.md](IMPLEMENTATION_REPORT.md)。

## Claude Code 专用中转与全局部署

部分中转账号只接受真正的 Claude Code 客户端。此时使用 `claude_code_reviewer`，不要用普通 Messages 请求或伪装客户端请求头。完整禁用样例见 [`registry.claude-review.json`](../../examples/registry.claude-review.json)。

```json
{"kind":"claude_code_reviewer","executable":"claude",
 "settings_file":"~/.claude/settings.json","allowed_host":"YOUR-PROVIDER-HOST"}
```

适配器启动实际 CLI，显式指定 model，使用 bare 模式、空 tools、空 MCP、禁用 skills、不保存会话、原生 JSON Schema 输出约束和客户端预算限制。每次 Reviewer 执行最多两个 CLI turn，用于审核及结构化输出，不增加 Worker 轮次。认证从显式设置文件读取，只将所需 API key/base URL 传入客户端子进程环境，不放入 argv、模型 prompt 或日志；支持将 API-key 型 AUTH_TOKEN 用作 bare 模式的 API_KEY（OAuth token 不保证兼容）。审核上下文通过 stdin 输入；使用专门的盲审系统提示替换默认编码提示，避免把审核任务误当成修改任务。它不会加载工作项目的 CLAUDE.md 或 Worker 对话；管理员托管策略仍可能生效，bare 模式不是 OS 沙箱。须安装支持这些参数的 CLI；本次参数检查使用 2.1.282。

网络若必须走本机代理，可显式增加 `proxy_url`（例如 `http://127.0.0.1:7890`）。仅传递这一代理，不继承任意供应商环境变量；代理 URL 不允许内嵌凭据。不要假定 GUI 系统代理自动对隔离 CLI 生效。

CLI 的 modelUsage 必须只有一个实际模型，且与注册模型匹配；多模型/截断/失败输出不会 PASS。CLI 自带费用计算可能不是中转账单，因此实际费用记录 null，token 在有输出时记录。超时进程及其子进程会终止；上游已发生的调用是否收费仍需供应商账单确认。

普通支持 Anthropic Messages 的服务也可用 `anthropic_messages`：显式 `settings_file`、`allowed_host`、`max_output_tokens`；读取 CC 的 base URL 与认证，只允许 HTTPS 和指定主机，拒绝重定向。此通用适配器不保证能用于“仅允许 CC”的账号组。HTTP 适配器是 socket 超时，不是完整响应的硬墙钟截止；CLI 适配器有进程级总时限。

本机全局安装可保留原 Worker 注册表，再加入 verification 策略，并开启 `require_verification_for_new_tasks: true`。开启后，新建委派任务遗漏 verification 会被程序拒绝；既有任务和 alias 不迁移、不重置次数。两个宿主都应引用同一份已安装策略、路由代码和项目账本。公开默认仍关闭该强制开关且不启用任何模型。
