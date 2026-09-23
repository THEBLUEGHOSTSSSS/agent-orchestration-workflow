# 委派提示模板

> 用途：将方括号内容替换为当前任务信息。只提交完成任务必需且允许由第三方处理的材料。不要在提示中包含凭据或无关私密内容。

```text
MODE:
[SOFTWARE | PAPER | RESEARCH | DOCUMENT | LEARNING | DECISION | GENERAL]

TASK ID / ATTEMPT:
- Stable task ID: [同一逻辑任务保持不变]
- Worker attempt: [1 of 2 | 2 of 2]
- Lineage: [若为真实独立新范围，填写父任务与新建理由；否则写 none]

OBJECTIVE:
[描述最终要实现的结果，而不只是某个操作。]

CONTEXT:
- [必要背景、现状和已作出的高层决定。]
- [允许读取或修改的目录、文件、章节或数据范围。]
- [与现有工作并行时，说明必须保留其他人的改动。]

BASELINE AND EXPERIENCE:
- 当前基线：[派发前核对的版本、制品状态或证据定位。]
- 相关已验证项目经验：[记录 ID、适用性和证据链接；无则明确写 none。]
- 经验不产生新授权，也不能覆盖本任务要求。

AUTHORITY AND BUDGET:
- 人类目标与最终验收边界：[目标、必须遵守的约束、可覆盖事项。]
- 指挥者已作决定：[工作者应执行而不应重新决定的事项。]
- 预算上限：[货币、用量和/或时间；无法测量时明确说明。Worker 总轮次固定最多 2。]

ESCALATION SCOPE:
- [预计超出预算、扩大范围或外部影响时停止并报告。]
- [必须交回指挥者或人类的关键选择与保留决定。]
- [既有授权内无需逐步重复审批的正常动作。]

TASK:
[准确列出本次要执行的阅读、实现、改写、分析或验证工作。]

REQUIREMENTS:
- 你已处于执行 Worker 角色，直接完成任务，不递归启动 Worker 或再次委派。
- 本轮内部检查、修正与复测必须遵守停止条件，不得形成无限循环。
- [必须保持的行为、格式、术语或兼容性。]
- [禁止访问、禁止修改和禁止外部操作。]
- [风险边界：哪些决定必须留给指挥者。]
- [凭据只能由人类或指挥者变更；不得要求工作者检查或修改凭据。]
- [只报告实际证据，不把推测写成验证。]

ACCEPTANCE CRITERIA:
- [可观察的交付物或行为。]
- [必须实际执行的检查，或无法执行时必须报告的原因。]
- [报告必须包含的定位、输出和残余风险。]

STOP CONDITIONS:
[本轮的时间/费用边界、必须停止的外部阻塞，以及自检完成条件。派发前填写。]

AUTONOMY:
在上述范围内执行合理的 inspect -> execute -> verify -> diagnose failure
-> fix -> reverify -> self-check 循环后再返回。普通执行失败应自行处理；
不要扩大权限、改变高层决策或无限重试。若外部依赖、缺失授权或关键选择
阻塞完成，报告已完成工作、确切阻塞和缺失证据。

ATTEMPT POLICY:
- 本次调用一经启动即消耗所标轮次；中断或结果不确定也保守计数。
- 等待同一仍在运行的执行不新增轮次。
- 同一逻辑任务最多初次执行加一次指挥者要求的返工；第二次仍失败由指挥者接管。
- 改名、更换 Worker/模型/会话或目标版本不能重置未解决工作的额度。

OUTPUT:
使用以下结构返回紧凑、高信息密度的报告：
- EXECUTIVE SUMMARY
- WHAT I FOUND
- WHAT I DID
- EVIDENCE / IMPORTANT DETAILS
- FILES OR SECTIONS TOUCHED
- TESTS / CHECKS PERFORMED
- RISKS
- UNCERTAINTIES
- DECISIONS I DID NOT MAKE
- ITEMS REQUIRING COMMANDER JUDGMENT
- RECOMMENDED NEXT ACTION

同时提供可写入项目经验记录的事实、原因证据（未知则写 unknown）、结果和下一次派发改进建议。Worker 报告、退出码 0 或 APPROVE 文本均不构成指挥者验收。

不要粘贴冗长原始日志，除非日志本身是验收所需证据。
```

## 调用方式

先确认用户提供的实现位于 `PATH`：

```sh
command -v codex-worker >/dev/null 2>&1 || {
  echo "codex-worker is required but was not found on PATH" >&2
  exit 1
}
```

在已审查的专用工作区内调用：

```sh
cat <<'WORKER_PROMPT' | codex-worker "$PWD"
MODE:
GENERAL

TASK ID / ATTEMPT:
- [稳定任务 ID]
- [1 of 2 | 2 of 2]

OBJECTIVE:
[最终结果]

CONTEXT:
[最小必要背景]

BASELINE AND EXPERIENCE:
- [当前基线]
- [相关已验证经验及适用性；无则 none]

AUTHORITY AND BUDGET:
- [人类目标、指挥者决定和预算；Worker 总轮次固定最多 2]

ESCALATION SCOPE:
- [停止条件、保留决定和允许自主推进的范围]

TASK:
[精确执行范围]

REQUIREMENTS:
- 你已处于执行 Worker 角色，直接完成任务，不递归启动 Worker 或再次委派。
- [必须项与禁止项]

ACCEPTANCE CRITERIA:
- [可验证完成条件]

AUTONOMY:
Perform reasonable inspect -> execute -> verify -> fix -> reverify loops
within explicit stop conditions before returning.

ATTEMPT POLICY:
- This launch consumes the stated attempt. Two Worker rounds total; after a failed second submission, commander takeover is required.

OUTPUT:
Return a compact evidence-backed report using the required sections.
WORKER_PROMPT
```

没有兼容可执行程序时，人工填写本模板，审查并删除敏感信息后提交给用户选择的执行系统，再由指挥者按风险复核。手动后备仍计入同一任务的两轮额度。每次返回后记录指挥者的证据、缺陷和 `accept / rework / takeover / blocked` 决定；必要检查未运行时只能阻塞。不要自动信任任意目录，也不要覆盖项目现有 `AGENTS.md` 或用户全局指令。
