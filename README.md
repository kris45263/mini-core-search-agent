# Seekra

在终端中搜索、读取来源、继续追问的轻量研究助手。

Seekra 根据已有信息决定下一步：搜索网络、读取网页、整理研究笔记，或给出带来源的回答。你可以看到它搜索了什么、找到了哪些来源，以及正在读取哪个页面。

采用普通 Python，使用 DeepSeek 和 Tavily，无需额外 Agent 框架。适合轻量资料研究，也便于观察、理解和扩展迭代搜索过程。

## 快速开始

需要 [uv](https://docs.astral.sh/uv/getting-started/installation/)、Python 3.13，以及有效的 DeepSeek 和 Tavily API key。uv 可在本机缺少所需 Python 时下载对应版本。

```powershell
git clone https://github.com/kris45263/seekra.git
cd seekra
uv sync --locked
Copy-Item .env.example .env
```

已有 `.env` 时跳过复制，避免覆盖配置。应用名称为 Seekra，仓库、Python 包和命令名称统一为 `seekra`。

编辑项目根目录的 `.env`：

```dotenv
DEEPSEEK_API_KEY=你的DeepSeek密钥
DEEPSEEK_MODEL=deepseek-v4-flash
TAVILY_API_KEY=你的Tavily密钥
```

密钥可在 [DeepSeek 平台](https://platform.deepseek.com/) 和 [Tavily 控制台](https://app.tavily.com/) 创建。调用服务会产生相应费用；`.env` 已被 Git 忽略。

然后启动：

```powershell
uv run seekra --repl
```

无需再输入 `python -X utf8 main.py`。Seekra 在命令入口统一使用 UTF-8 处理输入输出。

## 直接使用 seekra 命令

如果希望每次只输入 `seekra --repl`，在项目根目录执行一次：

```powershell
uv tool install --python 3.13 --editable .
```

安装完成后：

```powershell
seekra --repl
seekra "查找 Python 3.13 的主要改进，并提供官方来源"
```

这是从当前本地项目安装，不需要从 PyPI 下载同名项目。可编辑安装会使用本地源码；请保留该项目目录。修改依赖或移动目录后，重新安装工具。

如果 uv 提示工具目录不在 PATH 中，执行 `uv tool update-shell`，再打开一个新终端。它会更新用户的 shell / PATH 配置；项目本身不会自动修改全局环境。[uv 工具安装说明](https://docs.astral.sh/uv/guides/tools/)

仅 clone 不会向 shell 注册命令。也可以不安装全局工具：继续使用 `uv run seekra`，或在当前终端激活项目虚拟环境后使用 `seekra`。PowerShell 的激活命令为 `.\.venv\Scripts\Activate.ps1`；若本机策略不允许运行该脚本，使用前两种方式即可。

移除工具可运行 `uv tool uninstall seekra`，不会删除项目源码。

## 连续对话

```text
Seekra · 搜索研究助手
输入问题开始研究。/help 查看帮助 · /new 新对话 · /exit 退出

› Python 3.13 的主要改进有哪些？请提供官方来源。
```

输入问题后，Seekra 会逐段显示回答，并展示搜索来源和读取对象。回答结束后可以直接追问；`›` 表示等待你的下一次输入。

| 会话命令 | 作用 |
| --- | --- |
| `/help` | 查看会话命令与快捷键 |
| `/new` | 同时清空对话历史和页面快照 |
| `/exit` | 退出 Seekra |

回答期间按 Ctrl+C 取消当前问题，并返回输入提示；等待输入时按 Ctrl+C 或输入 EOF 退出。空输入不调用模型。失败或取消的问答不会加入后续上下文，先前完成的对话仍然保留。退出程序后会话不保存。

## 命令与配置

下列示例使用安装后的 `seekra`；在项目目录内均可替换为 `uv run seekra`。

```powershell
seekra --repl --verbose
seekra "对比两个版本的行为，并提供来源" --max-iterations 8
seekra --help
seekra --version
```

| 参数 | 作用 |
| --- | --- |
| `问题` | 单次研究问题，与 `--repl` 二选一 |
| `--repl` | 连续对话 |
| `--verbose` | 展示工具参数、结果、轮次预算和计时 |
| `--max-iterations N` | 每个问题最多请求模型 N 次，默认 12 |
| `--env-file PATH` | 指定配置文件，默认读取当前工作目录的 `.env` |
| `--structured-think` | 实验性结构化研究笔记，默认关闭 |
| `--help` / `--version` | 查看帮助 / 版本，不需要配置密钥 |

默认配置以**启动时所在目录**为准，不从安装目录或父目录自动查找，也不使用系统环境中的同名密钥。它不会展开配置值中的环境变量。在其他目录启动时，可以明确指定文件：

```powershell
seekra --env-file "C:\path\to\seekra\.env" --repl
```

模型必须支持当前使用的工具调用协议。模型调用轮次不等于工具调用次数，也不是费用上限；达到轮次上限仍没有答案时会明确报错。

正文写入 stdout，欢迎信息、输入提示、来源和运行状态写入 stderr。工具前的模型说明也属于正文；完成后不会重复打印答案。流中失败或取消时，已经显示的正文无法撤回，重定向 stdout 的文件可能包含中间说明或失败残稿，应结合退出状态判断。

## 功能与边界

- **迭代搜索**：模型根据实际结果调整查询，可选择 1–10 条候选并限定明确域名；结果经过字段校验、基础整理和单次精确去重。
- **读取来源**：通过 Tavily Extract 获取指定 URL 的文本，长页面可以继续读取同一内容快照。
- **连续追问**：复用内存历史；消息与页面快照一起提交，失败时回退。
- **观察过程**：默认流式输出，工具调用完整接收后执行；普通界面显示来源，`--verbose` 提供执行细节。

工具成功只代表取得内容，不证明来源可靠、版本适用或模型结论正确。网页提取可能失败或不完整，不支持登录及交互式浏览器操作。Session 不支持并发访问，也不自动压缩历史；长会话可能达到模型上下文上限。结构化笔记尚未证明普遍改善答案质量。

## 开发与验证

先在项目根目录运行 `uv sync --locked`。主 CLI 使用已安装的 `src/seekra` 包，测试和脚本也从同一个包导入。

工程测试不联网、不读取真实密钥；安装入口测试使用临时目录和假配置：

```powershell
uv run python -X utf8 -m unittest discover -s tests -v
```

列出真实验收问题（不调用 API）：

```powershell
uv run python -X utf8 scripts/run_live_case.py --list
```

显式运行一个真实用例并保存新记录（会产生服务调用费用，不覆盖已有文件）：

```powershell
uv run python -X utf8 scripts/run_live_case.py --case page --output docs/testing/results/my-page-run.json
```

无工具流式开发验收仍可使用 `uv run python -X utf8 scripts/check_streaming.py`；它与主 Agent 共用同一接收器。这些开发脚本保留 Python 入口，不作为额外产品命令。

构建可安装的分发包：

```powershell
uv build
```

- [模块与数据约定](docs/architecture.md)
- [测试方案与判定标准](docs/testing/plan.md)
- [真实验收结果与已知问题](docs/harness-validation.md)
- [实际测试数据](docs/testing/results/)
- [检索与页面噪声研究结论](docs/retrieval-findings.md)

## 项目结构

```text
pyproject.toml
README.md
src/
└─ seekra/
   ├─ __init__.py
   ├─ __main__.py    python -m seekra 入口
   ├─ cli.py         配置、命令行与 REPL
   ├─ agent.py       模型循环、预算、会话提交与回退
   ├─ deepseek.py    SSE 接收、正文与工具调用组装
   ├─ tools.py       工具定义、参数校验与分派
   ├─ retrieval.py   搜索结果处理、页面读取与续读
   ├─ operations.py  公共操作结果约定
   ├─ display.py     终端展示
   └─ session.py     内存消息与页面快照
tests/
docs/
scripts/
```

## 帮助与参考

项目由 [kris45263](https://github.com/kris45263) 维护。问题或建议可提交到 [Issues](https://github.com/kris45263/seekra/issues)，请提供复现命令、预期与实际行为，并删除密钥及敏感内容。提交代码前请运行工程测试，Python 文件说明和注释使用中文。

研究闭环参考 [langchain-ai/deep_research_from_scratch 的 Notebook 2](https://github.com/langchain-ai/deep_research_from_scratch/tree/93f35e5d2a51590f9542207a9ff66a01901da5bc)。

协议文档：[DeepSeek Tool Calls](https://api-docs.deepseek.com/guides/tool_calls/)、[Tavily Search](https://docs.tavily.com/documentation/api-reference/endpoint/search)、[Tavily Extract](https://docs.tavily.com/documentation/api-reference/endpoint/extract)。
