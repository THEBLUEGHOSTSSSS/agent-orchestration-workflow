# 说明性示例：软件任务

> **仅为说明性内容，状态为 pending。** 下列项目、文件、命令和预期结果均为虚构示例，不是实际运行记录、技术验收、客户历史或性能基准。

## 场景

一个虚构的命令行项目需要为 `report` 子命令增加 `--format json`。指挥者已决定公共字段为 `status`、`items` 和 `generated_at`，时间使用 UTC 的 ISO 8601 格式（以 `Z` 结尾），且不得改变默认文本输出。该决定属于接口策略；工作者只负责探索、实现和验证。

先确认用户自备的执行程序：

```sh
command -v codex-worker >/dev/null 2>&1 || {
  echo "codex-worker is required but was not found on PATH" >&2
  exit 1
}
```

## 完整委派命令

```sh
cat <<'WORKER_PROMPT' | codex-worker "$PWD"
MODE:
SOFTWARE

TASK ID / ATTEMPT:
- Stable task ID: EXAMPLE-SOFTWARE-REPORT-JSON
- Worker attempt: 1 of 2
- Lineage: none; this is a synthetic pending example

OBJECTIVE:
为虚构项目的 report 子命令增加 JSON 输出，同时保持现有默认文本输出兼容。

CONTEXT:
- 指挥者已决定 JSON 顶层字段仅为 status、items、generated_at。
- generated_at 使用 UTC 的 ISO 8601 格式，以 Z 结尾。
- 只处理 src/cli、src/report 和对应 tests 目录。
- 工作区可能有其他人的修改，必须保留无关变更。

BASELINE AND EXPERIENCE:
- 当前基线：派发前由指挥者核对 report 的当前文本输出、相关测试状态和工作区差异；本示例未实际核对。
- 相关已验证项目经验：none（说明性占位，不表示已检索真实项目记录）。
- 经验只作为范围内证据，不增加权限。

TASK:
1. 检查 report 命令入口、当前文本渲染路径和相关测试。
2. 实现 --format json，并复用现有领域数据，不从格式化文本反向解析。
3. 为 JSON 成功路径、无数据路径、非法格式和默认文本兼容添加测试。
4. 运行最小相关测试；若通过且仓库提供可识别的快速回归命令，再运行该命令。
5. 自查错误输出仍进入标准错误，JSON 标准输出不混入日志。

REQUIREMENTS:
- 不改变指挥者确定的字段或时间格式策略。
- 不修改认证、依赖锁文件、发布配置或工作区外文件。
- 不提交、推送、发布或调用外部服务。
- 不检查凭据、Codex 配置或私有工作者配置。
- 不递归启动另一个工作者，也不继续委派。
- 只把实际运行的检查写成通过。

ACCEPTANCE CRITERIA:
- report --format json 输出可解析 JSON，且只含既定顶层字段。
- 默认 report 输出与变更前行为一致。
- 非法格式返回非零状态并给出清晰错误。
- 相关自动化测试通过；无法运行的检查及原因被明确报告。
- 报告列出所有改动文件、关键定位、命令、退出状态和残余风险。

AUTONOMY:
在指定目录内完成 inspect -> implement -> test -> diagnose -> fix -> retest
-> self-check 循环，并在时间/范围边界达到时停止。普通测试失败可自行修复；
不要改变公共接口决定、扩大范围或无限循环。

ATTEMPT POLICY:
- 本次启动将消耗第 1 轮；中断或结果不确定也保守计数，等待同一运行不另计。
- 指挥者最多可要求一次第 2 轮修正；若仍失败，必须由指挥者接管修复、测试与复核。
- 改名、更换 Worker/模型/会话或目标版本不能重置同一未解决工作。

OUTPUT:
按 worker-report 模板返回 EXECUTIVE SUMMARY、WHAT I FOUND、WHAT I DID、
EVIDENCE / IMPORTANT DETAILS、FILES OR SECTIONS TOUCHED、TESTS / CHECKS
PERFORMED、RISKS、UNCERTAINTIES、DECISIONS I DID NOT MAKE、ITEMS REQUIRING
COMMANDER JUDGMENT 和 RECOMMENDED NEXT ACTION。
同时返回供指挥者写入项目经验记录的事实、原因证据或 unknown、结果和下次派发改进建议。
WORKER_PROMPT
```

## 指挥者复核要点

这是中等风险的公共 CLI 行为变更。每次提交后，指挥者应记录证据、缺陷及 `accept / rework / takeover / blocked` 决定，并检查参数解析、JSON 字段和错误通道，查看代表性测试，确认默认输出兼容。必要检查未运行时只能阻塞；退出码 `0` 和 Worker 自报不构成验收。最终技术接受还要求核对当前制品和项目本地经验记录。

若第 1 轮有缺陷，指挥者可以要求唯一一次针对性返工或更早接管；第 2 轮仍失败时不得第三次调用 Worker。真实独立的新范围需要新 ID、理由和谱系。本示例没有执行任何轮次，也没有生成接受结果或经验结论。

本示例提示将提交、推送和发布排除在任务范围之外；若真实任务已授权这些动作，应按已有授权推进，无需重复询问。
