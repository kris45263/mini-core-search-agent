# mini-core-search-agent

一个可在终端连续对话的搜索研究 Agent。DeepSeek 根据已有消息自主选择搜索、读取网页、整理笔记或回答；harness 执行工具并将结果写回上下文。

适用于观察和理解迭代搜索过程，以及进行需要来源支持的轻量研究。采用普通 Python，便于阅读和扩展。

## 功能

- Tavily Search 搜索来源，包含结果校验、基础整理和单次精确去重。
- Tavily Extract 读取指定 URL，长页面支持继续读取同一内容快照。
- 内存会话和 REPL，支持连续追问、清空会话与失败恢复。
- 可读的工具执行过程、明确的成功/空结果/部分内容/失败状态及轮次预算。
- 可选的结构化研究笔记实验模式。

## 安装与配置

需要 Python 3.13、[uv](https://docs.astral.sh/uv/) 和有效的 DeepSeek、Tavily API key。

```powershell
git clone https://github.com/kris45263/mini-core-search-agent.git
cd mini-core-search-agent
uv sync --locked
Copy-Item .env.example .env
```

已有 `.env` 时不要重复覆盖。在项目根目录的 `.env` 中填写：

```dotenv
DEEPSEEK_API_KEY=你的DeepSeek密钥
DEEPSEEK_MODEL=deepseek-v4-flash
TAVILY_API_KEY=你的Tavily密钥
```

密钥可在 [DeepSeek 平台](https://platform.deepseek.com/) 和 [Tavily 控制台](https://app.tavily.com/) 创建。程序只读取项目 `.env`，不使用系统环境中的同名密钥；该文件不会进入 Git。模型必须支持当前使用的工具调用协议。

## 使用

单次研究：

```powershell
uv run python -X utf8 main.py "查找 Python 3.13 的主要改进，并提供官方来源"
```

连续对话并显示研究过程：

```powershell
uv run python -X utf8 main.py --repl --verbose
```

|参数或命令|作用|
|---|---|
|`--repl`|启动连续输入模式，不能同时提供单次问题|
|`--verbose`|向 stderr 显示轮次、工具参数、结果、读取范围和预算|
|`--max-iterations N`|每个问题最多请求模型 N 次，默认 12|
|`--structured-think`|实验性结构化笔记，默认关闭|
|`/new`|在 REPL 中清空消息和页面快照|
|`/exit`|退出 REPL|

研究期间 Ctrl+C 取消当前问题并返回输入提示；等待输入时 Ctrl+C 或 EOF 退出。空输入不调用模型。最终答案输出到 stdout，执行过程输出到 stderr。

模型调用轮次不等于工具调用次数，也不是费用上限。一次模型响应可能包含多个工具调用；达到轮次上限仍没有答案时会明确报错。

## 测试

工程测试不联网、不读取真实密钥：

```powershell
uv run python -X utf8 -m unittest discover -s tests -v
```

列出真实验收问题（不调用 API）：

```powershell
uv run python -X utf8 scripts/run_live_case.py --list
```

显式运行一个真实用例并保存新记录（会产生服务调用费用）：

```powershell
uv run python -X utf8 scripts/run_live_case.py --case page --output live-page-result.json
```

- [测试方案与判定标准](docs/testing/plan.md)
- [真实验收结果与已知问题](docs/harness-validation.md)
- [实际测试数据](docs/testing/results/)
- [模块与数据约定](docs/architecture.md)

## 能力边界

- Session 仅在当前进程内保留；退出后不恢复，不支持并发操作同一会话。
- 不自动压缩历史，长会话可能达到模型上下文上限。
- 网页提取可能失败或不完整，不支持登录和交互式浏览器操作。
- 工具成功只表示取得内容，不证明内容可靠、版本适用或模型结论正确。
- 结构化笔记尚未证明普遍改善答案质量；模型目前不流式输出。

## 项目结构

```text
agent.py        模型循环、预算、会话提交与回退
tools.py        工具定义、参数校验与分派
retrieval.py    搜索结果处理、指定页面读取与续读
operations.py   公共操作结果约定
display.py      终端展示
session.py      内存消息与页面快照
main.py         配置与命令行入口
tests/          工程测试
scripts/        显式执行的验收脚本
docs/           设计和测试文档
```

## 帮助与贡献

项目由 [kris45263](https://github.com/kris45263) 维护。问题或建议可提交到 [Issues](https://github.com/kris45263/mini-core-search-agent/issues)，请提供复现命令、预期与实际行为，并删除密钥及敏感内容。提交代码前请运行工程测试，Python 文件说明和注释使用中文。

## 参考

研究闭环参考 [langchain-ai/deep_research_from_scratch](https://github.com/langchain-ai/deep_research_from_scratch/tree/93f35e5d2a51590f9542207a9ff66a01901da5bc) 的 Notebook 2。

协议文档：[DeepSeek Tool Calls](https://api-docs.deepseek.com/guides/tool_calls/)、[Tavily Search](https://docs.tavily.com/documentation/api-reference/endpoint/search)、[Tavily Extract](https://docs.tavily.com/documentation/api-reference/endpoint/extract)。
