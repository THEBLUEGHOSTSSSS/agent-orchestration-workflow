# GPT / Claude 盲审接口实测 — 2026-09-26

这是 source_kind=probe 的人工植入 bug 实验，不是生产 Worker 执行能力或 Reviewer 准确率基准。未写入真实路由经验。

| 输入 | 模型 | 结构化结果 | 费用 USD | token | 秒 |
|---|---|---|---:|---:|---:|
| hidden_bug | openai/gpt-6-sol | FAIL | 0.002674 | 569 | 8.001 |
| hidden_bug | anthropic/claude-haiku-4.5 | FAIL | 0.003611 | 1047 | 7.934 |
| corrected | openai/gpt-6-sol | PASS | 0.002064 | 512 | 4.005 |
| corrected | anthropic/claude-haiku-4.5 | PASS | 0.001561 | 641 | 3.736 |

目标为整数加法；隐藏错误为 `return a-b`，修正为 `return a+b`。两模型独立收到原始标准、源码与仅做 import 的检查证据，互不见意见。Commander 核对返回反例与实际算术相符；修正版返回 PASS。两个模型都把简单错误标成 high/critical，提示严重度仍须人工校准，不可机械跟随。

本轮共 7 次收费调用，含首次 GPT 成功、Claude 围栏兼容失败及一次 Claude 诊断，总报告费用 **$0.017123**，总 token **4848**。费用来自响应 usage，不是最终账单核销。失败费用包含在内。

兼容修复：仅剥离完整的单一 ```json 围栏，随后仍严格验证 JSON、字段、角色、证据和模型身份；不从任意自然语言提取 JSON。保留 `pre-compatibility-results.json`、`diagnostic-result.json` 和最终 `live-results.json`。

全仓回归：`python3 -m unittest discover -s tests -q` → **116 tests, OK**（2.571s）；A–F 生命周期测试全通过。`git diff --check` 通过，注册表与 task 样例通过解析和风险计算。A–F 的 Reviewer 是确定性 fixture；本文件四条最终结果才是真实外部模型调用。

复现：设置环境变量 OPENROUTER_API_KEY 后，运行 `python3 experiments/verification-20260926/run_probe.py --output /path/to/new-result.json`。最多四次调用，首次异常停止；拒绝覆盖既有证据。该脚本显式收费，不由工作流后台执行。

结论仅限：GPT/Claude 的结构化盲审适配器在该小探针中可用。未证明复杂代码检错率、跨模型独立性、审核总体节省成本或视觉/视频能力。
