# CURRENT_ARCHITECTURE_ASSESSMENT

审计基线：`02d975a44cb2b5d5f8c216050d05e20e8d349f89`；2026-09-24。本文件描述实施前事实，后续实现不回写成原有能力。

## 当前调用链

Human request → 主会话理解与拆解 → 人工填写契约或提示 → 外部 `codex-worker <workspace>` → 实际文件与报告 → 主会话审核 → 人工决定通过/返工/接管。

公开仓库只有一个执行检查脚本 `scripts/validate_review.py`，没有任务调度器。外部私有 launcher 不在仓库分发：它复制用户 Worker 配置，读取已有认证，启动 `codex exec`，保存 prompt / events.jsonl / final.txt，返回退出码。此次审计读取的生效配置为 `gpt-6-sol / xhigh`；模型与强度没有按任务变化。客户端配置不能证明供应商内部模型路由。

## 逐项审计

| 项目 | 当前实现位置 | 分类与缺口 |
| --- | --- | --- |
| 1 Strong Model rules | AGENTS.md 的 COMMAND/REVIEW 与 REVIEW PROTOCOL | POLICY_ENFORCED：最终判断仍由主会话执行 |
| 2 Worker templates | templates/delegation.md、worker-report.md、各 evidence pack | POLICY_ENFORCED：范围、基线和停止条件需要填写 |
| 3 task schema | templates/task-contract.json，examples/contracts/task-01.json（0.2） | POLICY_ENFORCED：说明性 JSON，无运行时状态机 |
| 4 review schema | docs/review-record.example.json，validate_review.py | STATIC_CHECKED：完成状态、证据引用与摘要可检查 |
| 5 attempt tracking | worker_attempts 数组、模板中的 1/2、2/2 | STATIC_CHECKED：事后最多两项；启动前没有额度预留 |
| 6 static acceptance | scripts/validate_review.py、tests/test_validate_review.py | STATIC_CHECKED：16 项边界测试；不执行 Worker |
| 7 global instructions | 用户级 AGENTS.md 与安装资源目录 | POLICY_ENFORCED：副本哈希可核对，不代表所有旧会话遵守 |
| 8 experience/memory | templates/experience-record.md、records/*.md | POLICY_ENFORCED：项目经验必须写；无结构化模型检索与计分 |
| 9 logging | 私有 launcher 的 runs 目录；records 中人工验收 | 日志写盘属实际行为，但没有事务性任务/归因账本；被中止时可能无 final |
| 10 configuration | 全局规则、用户 Worker TOML、公开任务模板 | 没有统一路由配置或 registry |
| 11 invocation | 私有 launcher → codex exec | 固定后端；CLI 自身支持 model/config 参数，但 launcher 未暴露按次选择 |
| 12 reasoning effort | 用户 TOML 的 model_reasoning_effort | 固定 xhigh；不是 task-aware |
| 13 Worker selection | 主会话人工选择及固定默认值 | NOT_CURRENTLY_ENFORCEABLE：不存在可执行选择器 |
| 14 failure handling | AGENTS.md、workflow.md，人工纠错 | POLICY_ENFORCED：无结构化 attribution，失败不等于模型失败 |
| 15 task identity | task_id / lineage 文档字段 | NOT_CURRENTLY_ENFORCEABLE：无共享持久账本，别名可绕过人工记录 |
| 16 retry rules | 两轮规则与静态检查器 | POLICY_ENFORCED + STATIC_CHECKED；第三次实际调用未被启动入口拦截 |

## 执行边界

- HARD_ENFORCED：旧检查器被显式运行时会按其代码拒绝不合格记录；这只是该检查程序的行为，不是 Worker 生命周期的硬门禁。
- STATIC_CHECKED：JSON 结构、轮次顺序、证据文件存在及 SHA-256、经验引用。
- POLICY_ENFORCED：人类权限、强模型真实审核、Worker 不扩权/不递归、真实归因、必须积累经验。
- NOT_CURRENTLY_ENFORCEABLE：所有入口下的全局次数、隐藏调用、语义等价任务识别、模型能力真实性、经验真实性。

## 最小实施方向

保留现有 Markdown 经验与旧 checker；新增 Python 标准库模块和一个 CLI。用有文件锁、原子替换的项目本地 JSON 账本保存任务、执行、经验与事件，避免引入数据库服务。显式别名/父任务与相同 work_key 共享额度；隐瞒语义关系仍是已知边界。新入口预留额度后才启动，返回后等待主会话提交审核，审核与经验更新在同一事务完成。成本未知保持 null，不虚构价格。
