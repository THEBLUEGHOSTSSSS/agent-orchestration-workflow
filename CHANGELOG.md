# 变更记录 / Changelog

## 2026-09-24 — Portable hosts and models

- Neutral disabled-by-default registry; original GPT pool moved to an optional example.
- Native Codex CLI and Claude Code CLI adapters, generic command runner, provider-specific effort labels.
- Shared AGENTS.md / CLAUDE.md policy and bilingual portable setup documentation.
- Existing local user installation is unchanged.

## 2026-09-24 — Adaptive routing

- Added registry, structured profiler, conditional historical retrieval, transparent routing, outcome attribution and experience feedback.
- Added locked pre-launch two-attempt lifecycle, model-switch handoff, commander takeover and static validation.
- Added A–M scenario coverage and live adapter probes; economic benefits remain unmeasured.
- Documented policy and same-user bypass boundaries; no daemon or recursive workers.

## 2026-09-23：强模型审核与经验闭环

- 明确强模型的指挥、审核和技术验收职责；角色不绑定 Astra、Sol 或固定供应商。
- 同一逻辑任务的 Worker 总执行次数最多 2 次，即初次执行加最多 1 次打回重做。
- 第二次仍不合格，由指挥者直接修改、验证和验收；允许提前接管，禁止换模型或任务名清零。
- 项目经验记录成为必需步骤，包含失败与阻塞结果，并在后续相关任务中查阅。
- 更新任务契约、交接、报告、委派与经验模板；增加静态验收检查器及 16 项边界测试。
- 补充中英文 README 的规则速览、文档导航、检查器上手步骤，以及贡献者验收要求。

政策与检查器首次提交：[`2c1f209`](https://github.com/THEBLUEGHOSTSSSS/agent-orchestration-workflow/commit/2c1f20943b7854666d129ce786ac759879058bf8)。

本版本未提供自动调度器、不可绕过的调用拦截、运行时模型切换或递归 Worker；静态检查通过不代表成果语义正确。尚未发布同任务、同质量的成本对照测量。

## 2026-09-20：结构化交接

增加目标/任务契约、交接与经验模板，以及全局采用和回滚说明。此后，经验记录从可选机制升级为上述必需职责；不要继续沿用旧版的可选表述。
