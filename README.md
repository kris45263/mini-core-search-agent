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
tools.py              # 两个工具的 schema、执行与简单错误结果
main.py               # .env 配置和命令行入口
tests/test_agent.py    # 无网络、无真实密钥的闭环测试
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

Tavily 展示的是现有工具实际回传的全部搜索片段，不是网页全文。没有修改搜索结果 schema、校验或过滤机制。不打印 `.env`、请求头、密钥或 `reasoning_content`，不请求隐藏推理。显式笔记、模型正常说明中的内容重叠不做语义删减，便于观察真实行为；显示副本中意外回显的本次密钥会被遮蔽。

所有显示内容都不写入 `messages`。开关不改变提示词、工具定义、搜索结果、请求内容或调用次数；事件只同步显示真实执行步骤，没有新增状态机或评估框架。mock 测试逐项比较开关前后的请求相等，这保证程序没有因开关改变决策输入，不保证两次真实模型运行的随机输出相同。

如果当前终端找不到 `uv`，将上述命令的 `uv` 替换为 `& "$env:USERPROFILE/.local/bin/uv.exe"`。项目将 uv 缓存放在已忽略的 `.uv-cache` 中，避免当前受限环境的全局缓存权限问题。

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
- 当前验证使用 mock，没有使用真实 API key；真实连接、账户权限、费用和搜索回答质量尚未验证。
