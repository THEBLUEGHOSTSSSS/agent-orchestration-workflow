# 委派提示模板

> 用途：将方括号内容替换为当前任务信息。只提交完成任务必需且允许由第三方处理的材料。不要在提示中包含凭据或无关私密内容。

```text
MODE:
[SOFTWARE | PAPER | RESEARCH | DOCUMENT | LEARNING | DECISION | GENERAL]

OBJECTIVE:
[描述最终要实现的结果，而不只是某个操作。]

CONTEXT:
- [必要背景、现状和已作出的高层决定。]
- [允许读取或修改的目录、文件、章节或数据范围。]
- [与现有工作并行时，说明必须保留其他人的改动。]

TASK:
[准确列出本次要执行的阅读、实现、改写、分析或验证工作。]

REQUIREMENTS:
- [必须保持的行为、格式、术语或兼容性。]
- [禁止访问、禁止修改和禁止外部操作。]
- [风险边界：哪些决定必须留给指挥者。]
- [只报告实际证据，不把推测写成验证。]

ACCEPTANCE CRITERIA:
- [可观察的交付物或行为。]
- [必须实际执行的检查，或无法执行时必须报告的原因。]
- [报告必须包含的定位、输出和残余风险。]

AUTONOMY:
在上述范围内执行合理的 inspect -> execute -> verify -> diagnose failure
-> fix -> reverify -> self-check 循环后再返回。普通执行失败应自行处理；
不要扩大权限、改变高层决策或无限重试。若外部依赖、缺失授权或关键选择
阻塞完成，报告已完成工作、确切阻塞和缺失证据。

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

OBJECTIVE:
[最终结果]

CONTEXT:
[最小必要背景]

TASK:
[精确执行范围]

REQUIREMENTS:
- [必须项与禁止项]

ACCEPTANCE CRITERIA:
- [可验证完成条件]

AUTONOMY:
Perform reasonable inspect -> execute -> verify -> fix -> reverify loops
before returning.

OUTPUT:
Return a compact evidence-backed report using the required sections.
WORKER_PROMPT
```

没有兼容可执行程序时，人工填写本模板，审查并删除敏感信息后提交给用户选择的执行系统，再由指挥者按风险复核。不要自动信任任意目录，也不要覆盖项目现有 `AGENTS.md` 或用户全局指令。
