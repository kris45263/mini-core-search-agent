# mini-core-search-agent

一个普通 Python 实现的最小迭代搜索 Agent。模型固定接入 DeepSeek，搜索固定接入 Tavily，只提供 `tavily_search` 和 `think_tool` 两个工具。

## 为什么它能够迭代搜索

核心是「模型决策 → 执行工具 → 将结果写回消息 → 模型重新决策」。程序没有预先生成的搜索列表，也不决定第二次应该搜什么。模型读取前一次实际返回的信息后，生成新的工具名和参数。

1. 创建包含系统提示词和用户问题的 `messages`。
2. 把完整 `messages` 和两个工具的 JSON schema 发给 DeepSeek。
3. 追加完整 assistant 响应，保留正文、工具参数及调用编号。
4. 有工具调用时执行工具，为每个调用追加带相同 `tool_call_id` 的 tool 消息。
5. 将增长后的消息历史再次发给模型。
6. 模型不再调用工具时，返回其非空最终文本；最多执行 12 次模型请求。

`think_tool` 不调用其他模型，也不搜索。模型生成一份简短研究笔记作为 `reflection` 参数，工具将其回显到上下文。它帮助下一轮看见已有证据、缺口和下一步；它本身不能创造或验证事实。提示词建议搜索后使用该工具，代码不强制固定调用顺序。

## 参考源码与取舍

阅读基于上游提交 `93f35e5d2a51590f9542207a9ff66a01901da5bc`，实现为独立编写，未复制整个项目。

| 阅读范围 | 提炼出的机制及本项目处理 |
| --- | --- |
| [README 的 Research Agent 部分](https://github.com/langchain-ai/deep_research_from_scratch/blob/93f35e5d2a51590f9542207a9ff66a01901da5bc/README.md#2-research-agent-with-custom-tools-notebooks2_research_agentipynb) | 保留模型决策与同步工具执行的迭代结构。 |
| [2_research_agent.ipynb](https://github.com/langchain-ai/deep_research_from_scratch/blob/93f35e5d2a51590f9542207a9ff66a01901da5bc/notebooks/2_research_agent.ipynb) | 保留根据搜索结果判断缺口、继续或结束的思想，使用本地 mock 验证，去掉 Notebook 和 LangSmith 评估依赖。 |
| [research_agent.py](https://github.com/langchain-ai/deep_research_from_scratch/blob/93f35e5d2a51590f9542207a9ff66a01901da5bc/src/deep_research_from_scratch/research_agent.py) | `llm_call`、`tool_node`、`should_continue` 合并为直观的 Python 循环；去掉退出后的 `compress_research`。 |
| [state_research.py](https://github.com/langchain-ai/deep_research_from_scratch/blob/93f35e5d2a51590f9542207a9ff66a01901da5bc/src/deep_research_from_scratch/state_research.py) | `add_messages` 的追加语义用列表实现；去掉压缩结果、原始笔记副本及澄清/摘要 schema。 |
| [utils.py](https://github.com/langchain-ai/deep_research_from_scratch/blob/93f35e5d2a51590f9542207a9ff66a01901da5bc/src/deep_research_from_scratch/utils.py) | 保留单条 Tavily 查询、标题/URL/内容和 think 回显；去掉网页全文获取、另一个模型的摘要及多查询封装。 |
| [prompts.py](https://github.com/langchain-ai/deep_research_from_scratch/blob/93f35e5d2a51590f9542207a9ff66a01901da5bc/src/deep_research_from_scratch/prompts.py) | 保留按缺口调整查询、及时停止的研究指令；使用中文短提示词并实际填入日期和循环上限。 |

LangGraph 不是产生搜索能力的必要条件；在这个规模中，列表追加和 `for`/`if` 已能清楚表达其关键行为。`think_tool` 是本版按要求保留的显式笔记步骤，也不是某种隐藏的搜索引擎。

未引入多 Agent、supervisor、MCP、持久会话、数据库、LangSmith、大型评估、复杂状态机、recorder、metrics、privacy pipeline 或多 provider 抽象。单次研究的消息只存于内存。

## 文件结构

```text
agent.py              # 提示词、DeepSeek 请求和完整消息循环
session.py            # 进程内已完成历史及清空操作
tools.py              # 两个工具的 schema、执行与简单错误结果
main.py               # .env 配置、单次命令及 REPL 入口
tests/test_agent.py    # 无网络、无真实密钥的闭环测试
tests/test_session.py  # 跨输入继承、失败回退和清空隔离测试
tests/test_search_results.py # 搜索结果整理与校验测试
.env.example          # 可提交的空配置模板
.env                  # 本地填写真实配置，已被 Git 忽略
.gitignore
.python-version       # Python 3.13
pyproject.toml
uv.lock               # 锁定依赖版本
README.md
```

直接依赖只有 `httpx` 和 `python-dotenv`。使用 HTTP 调用 DeepSeek，不需要 OpenAI SDK 或 OpenAI API key。

## 填写密钥并运行

需要 Python 3.13 和 uv。当前项目已初始化虚拟环境；重新拉取项目后先在项目目录运行：

```powershell
uv sync --locked
```

当前文件夹已提供空 `.env`。新拉取的副本如果没有 `.env`，先执行 `Copy-Item .env.example .env`；不要覆盖已经填写过的文件。

用编辑器在 `.env` 中填入：

```dotenv
DEEPSEEK_API_KEY=你的DeepSeek密钥
DEEPSEEK_MODEL=deepseek-v4-flash
TAVILY_API_KEY=你的Tavily密钥
```

密钥分别在 [DeepSeek 平台](https://platform.deepseek.com/) 和 [Tavily 控制台](https://app.tavily.com/) 获取。模型名可以改成账号可用、支持工具调用的 DeepSeek 模型；程序没有静默默认模型或 provider 回退。

程序固定读取 `main.py` 同目录的 `.env`，不读取系统环境中的同名密钥，不展开 `${变量}`。不要把密钥写进 Python 文件或提交到 Git。

```powershell
uv run python -X utf8 main.py "查找 Python 3.13 的主要改进，并提供官方来源"
uv run python -X utf8 main.py "比较两个项目的最新发布情况" --max-iterations 8
```

控制台默认只输出最终答案；等待期间模型和搜索请求同步执行。添加 `--verbose` 可完整观察模型与 harness 的显式交互：

```powershell
uv run python -X utf8 main.py "查找 Python 3.13 的主要改进，并提供官方来源" --verbose
```

过程按轮次以中文文本排版到 stderr，不保存日志文件，也不再倾倒原始 JSON：

- 开始时显示一次用户问题。
- 每轮显示轮次及模型收到的消息数量；隐藏固定系统提示词、工具 schema，不重印历史消息。
- 模型调用工具时，非空的正常正文显示为“模型说明”；随后按同轮工具编号显示名称及解析后的参数。
- 搜索成功时完整显示每条结果的标题、URL 和内容片段，保留实际换行；不同搜索返回相同内容也照常显示，不做跨搜索来源编号、去重或截断。
- `think_tool` 的显式笔记只在参数区域显示一次；工具的机械回显简化为“研究笔记已记录”。参数错误及其他工具错误仍明确展示。
- 工具结果追加到消息后显示“已写回上下文”和当前消息数量。全部工具执行后才进行下一轮模型调用。
- 模型不调用工具并返回正常非空答案时，stderr 只显示“直接回答”和结束概况，答案正文仅通过 stdout 输出一次。
- 达到上限、模型请求失败或中断时显示异常结束原因，不冒充正常答案。

Tavily 展示的是处理后实际回传给模型的全部搜索片段，不是网页全文；同时显示收到、保留数量和各排除原因。不打印 `.env`、请求头、密钥或 `reasoning_content`，不请求隐藏推理。显式笔记、模型正常说明中的内容重叠不做语义删减，便于观察真实行为；显示副本中意外回显的本次密钥会被遮蔽。

## 搜索结果结构与处理规则

`tools.py` 用 `SearchResult`、`ProcessingInfo`、`SearchResponse` 三个 `TypedDict` 声明结果结构，`normalize_search_results()` 显式执行运行时校验；类型声明本身不提供运行时校验。

```text
query: 非空字符串，保留实际请求查询
results: [{title: 非空字符串, url: 非空字符串, content: 非空字符串}]
processing: {received: 收到数量, kept: 保留数量, removed: {原因: 数量}}
error: 可选，非空返回全部被过滤时说明没有可用证据
```

处理顺序为：Tavily JSON → 检查顶层对象及 results 列表 → 逐条字段校验 → 保守文本整理 → 单次精确去重 → JSON 工具结果。正常原始空列表没有 `error`；缺少 results 或 results 类型错误沿用工具格式异常错误；条目全被排除时附上 `error` 和处理数量。

- URL 必须是带主机的 HTTP(S) 字符串，拒绝内部空白、控制字符和非法端口。仅去掉首尾空白，不验证可访问性、不合并 www、不删除查询参数。
- 正文必须是字符串，统一 CRLF/CR 为 LF 并去掉首尾空白；空正文排除。不删导航、不改写、不摘要、不截断。
- 标题缺失、null 或空白时用 URL 代替；非字符串标题排除。非空标题仅整理换行和首尾空白。
- 仅在单次调用内，整理后的 URL 和正文均相同时保留第一条。标题差异不影响判重；同 URL 不同正文、不同 URL 相同正文都保留，不进行跨轮次去重。
- 每个坏条目仅计一个首要原因：`invalid_item`、`invalid_url`、`invalid_fields`、`empty_content` 或 `duplicate`。有效条目不会因其他坏条目而丢失。

处理数量是工具结果的一部分，开关前后相同。没有引入 relevance threshold、域名质量筛选、rerank 或摘要模型。

所有显示内容都不写入 `messages`。开关不改变提示词、工具定义、搜索结果、请求内容或调用次数；事件只同步显示真实执行步骤，没有新增状态机或评估框架。mock 测试逐项比较开关前后的请求相等，这保证程序没有因开关改变决策输入，不保证两次真实模型运行的随机输出相同。

如果当前终端找不到 `uv`，将上述命令的 `uv` 替换为 `& "$env:USERPROFILE/.local/bin/uv.exe"`。项目将 uv 缓存放在已忽略的 `.uv-cache` 中，避免当前受限环境的全局缓存权限问题。

## 内存 Session

`run_agent()` 可接收同一个 `Session`，让连续输入继承已完成的用户消息、assistant 正文、工具调用、工具结果和最终答案。不传 `session` 时自动使用临时会话，现有单次命令行为保持不变。

以下是同一 Python 进程内的调用示例；使用现有 `.env` 配置和 HTTP 客户端：

```python
from pathlib import Path
import httpx
from agent import run_agent
from main import read_config
from session import Session

config = read_config(Path(".env"))
session = Session()
with httpx.Client() as client:
    for question in ("Python 3.13 有哪些主要改进？", "其中第一项有哪些限制？"):
        answer = run_agent(
            question, client=client, session=session,
            model=config["DEEPSEEK_MODEL"],
            deepseek_api_key=config["DEEPSEEK_API_KEY"],
            tavily_api_key=config["TAVILY_API_KEY"],
        )
        print(answer)
session.clear()
```

每次提问深复制历史，更新唯一系统提示词的日期与循环上限，再追加新问题。仅正常返回非空最终答案后保存全部临时历史；请求失败、输出截断、空答案、超限或中断均保留提问前的历史。工具错误如果已回传给模型，且模型最终正常回答，则该错误也属于成功完成输入的历史。

每个新问题重新计算模型调用轮次。清空会话会移除所有旧问答和工具结果。不撤销已经发生的请求、费用或终端输出，不自动重试失败输入。

`Session.messages` 由 Agent 维护，调用方不要手工插入不配对的工具消息；同一 Session 只供顺序调用，不支持并发提问。暂无持久化、自动裁剪或压缩，长会话可能触及模型上下文上限。进程退出后历史消失。

启动 REPL 可在同一个进程内连续使用这个会话：

```powershell
uv run python -X utf8 main.py --repl
uv run python -X utf8 main.py --repl --verbose
```

启动时读取一次 `.env`，创建一个 HTTP 客户端及一个 Session，循环接收输入并复用它们。每次输入等待回答结束后再输入下一问。

- `/new`：清空历史，继续输入。
- `/exit`：退出程序；EOF（Windows 可用 Ctrl+Z 后回车）也会退出。
- 空白输入：忽略，不请求模型。未知斜杠命令提示可用命令。
- 研究期间 Ctrl+C：取消当前问题，保留此前完成历史，返回输入提示。
- 等待输入期间 Ctrl+C：退出 REPL。
- 研究失败：显示错误后继续输入；配置错误则在启动时退出。

`--max-iterations` 对每个问题分别生效；`--verbose` 对本次启动的所有问题生效。`--repl` 不能同时附带单次问题。退出后不保存会话，反复执行单次 CLI 命令仍是独立会话。模型暂不流式输出。

## 无密钥验证

```powershell
uv run python -X utf8 -m unittest discover -s tests -v
```

测试只替换 HTTP 传输，实际执行 `run_agent` 和两个工具。动态搜索测试分别返回「青松」和「白桦」，模拟模型必须从已收到的结果中取得对应名称，再发起不同的第二次搜索；同时断言旧消息完整保留、工具结果编号正确和最终答案及时结束。这证明循环能传递决策所需的信息，不代表真实模型在所有问题上都会做出正确判断。

## 边界和 API 依据

- 上限按模型请求次数计算，搜索和 think 都会消耗决策轮次；一轮可能包含多个工具调用，按顺序执行。到上限仍未回答时返回错误和退出码 1，不额外请求模型强行总结。
- Tavily 每次最多返回 3 个结果，使用 `basic` 搜索；保留结果的标题、URL、内容片段，不获取网页全文，不再用模型压缩。空结果同样回传给模型。
- 搜索失败或错误工具参数作为 tool 错误回传，供下一轮决策；DeepSeek 请求失败、空答案或截断则停止。没有自动重试框架。
- 所有消息始终保留，因此较长研究仍可能超过模型上下文限制。本版不增加自动裁剪或压缩。
- 引用来源和及时停止由提示词引导，未实现事实核验或引用校验器。
- DeepSeek 采用 [Chat Completions 工具调用协议](https://api-docs.deepseek.com/guides/tool_calls/)，显式设置 `thinking.type=disabled`，降低第一版协议复杂度；这是模型内部模式，与应用的 `think_tool` 不同。模式参数见 [Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode/)。Tavily 请求字段及结果形状见 [Search API](https://docs.tavily.com/documentation/api-reference/endpoint/search)。
- 自动测试使用 mock；已完成真实 DeepSeek/Tavily 搜索闭环和 REPL 连续两问的会话记忆验证。尚未做系统性的回答质量或费用评估；真实运行成功不代表所有问题都能准确回答。
