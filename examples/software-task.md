# 说明性示例：软件任务

> **仅为说明性内容。** 下列项目、文件、命令和预期结果均为虚构示例，不是实际运行记录、客户历史或性能基准。

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

OBJECTIVE:
为虚构项目的 report 子命令增加 JSON 输出，同时保持现有默认文本输出兼容。

CONTEXT:
- 指挥者已决定 JSON 顶层字段仅为 status、items、generated_at。
- generated_at 使用 UTC 的 ISO 8601 格式，以 Z 结尾。
- 只处理 src/cli、src/report 和对应 tests 目录。
- 工作区可能有其他人的修改，必须保留无关变更。

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
-> self-check 循环。普通测试失败可自行修复；不要改变公共接口决定或扩大范围。

OUTPUT:
按 worker-report 模板返回 EXECUTIVE SUMMARY、WHAT I FOUND、WHAT I DID、
EVIDENCE / IMPORTANT DETAILS、FILES OR SECTIONS TOUCHED、TESTS / CHECKS
PERFORMED、RISKS、UNCERTAINTIES、DECISIONS I DID NOT MAKE、ITEMS REQUIRING
COMMANDER JUDGMENT 和 RECOMMENDED NEXT ACTION。
WORKER_PROMPT
```

## 指挥者复核要点

这是中等风险的公共 CLI 行为变更。指挥者应检查参数解析、JSON 字段和错误通道，查看代表性测试，并确认默认输出兼容。若 `generated_at` 涉及时区或稳定性，应核对已决定的格式策略。工作者报告的命令必须能对应到实际输出或退出状态。

本示例提示将提交、推送和发布排除在任务范围之外；若真实任务已授权这些动作，应按已有授权推进，无需重复询问。
