# mini-core-search-agent

普通 Python 实现的迭代研究 Agent：DeepSeek 负责决策，Tavily Search 寻找来源，Tavily Extract 读取指定页面。支持单次命令、内存 Session 和 REPL。

## 启动

需要 Python 3.13 和 uv：

```powershell
uv sync --locked
uv run python -X utf8 main.py "你的研究问题" --verbose
uv run python -X utf8 main.py --repl --verbose
```

项目已有本地 `.env`；新拉取的副本如果没有它，执行 `Copy-Item .env.example .env`，不要覆盖已填写的文件。

```dotenv
DEEPSEEK_API_KEY=你的DeepSeek密钥
DEEPSEEK_MODEL=deepseek-v4-flash
TAVILY_API_KEY=你的Tavily密钥
```

只读取 `main.py` 同目录的 `.env`，不回退到系统环境中的同名密钥，不展开 `${变量}`。`.env`、虚拟环境及缓存均被 Git 忽略。若终端找不到 uv，可使用 `& "$env:USERPROFILE/.local/bin/uv.exe"`。

REPL 在启动时创建一次客户端和 Session，之后连续复用：

- `/new` 清空历史和页面快照。
- `/exit` 或 EOF 退出。
- 空输入不调用模型；未知斜杠命令会提示可用命令。
- 研究期间 Ctrl+C 取消本次输入、返回提示；等待输入时 Ctrl+C 退出。
- 研究失败后仍可继续输入，先前完成的历史保留。

`--max-iterations 12` 控制每个问题最多的模型请求次数，默认 12。一次模型响应可能包含多个工具调用，因此它不是搜索次数或总费用上限。每次模型请求前，唯一系统消息都会更新当前轮次、此前已完成次数及本次之后的剩余次数。直接回答也是一次模型调用；到上限仍没有正常答案会报错，不自动强行总结。

## 搜索闭环

```text
用户问题 + Session 已完成历史
→ 当前问题的临时副本
→ DeepSeek 读取上下文和工具定义
→ 生成工具调用或直接回答
→ 执行工具，将统一操作结果写回 tool 消息
→ 下一轮模型决策
→ 正常答案后保存本次历史及页面快照
```

不预先生成固定搜索清单，不强制搜索、读取、think 的调用顺序。不压缩历史，不将工具执行成功认证为结论正确。DeepSeek 内部 thinking 模式当前关闭，显式 think 工具与隐藏推理不同。

## 三个工具

### tavily_search(query)

使用 `basic`、最多 3 条结果，不请求 raw content 或 provider 生成的答案。返回 `query`、`results[{title,url,content}]` 和 `processing`。

`retrieval.py` 中的 `normalize_search_results()` 显式校验原始返回；TypedDict 只是结构声明，本身不提供运行时校验：

- 顶层必须是对象，results 必须为列表。
- 无效 URL、非字符串正文/标题、空正文会被排除。缺失、null 或空标题用 URL 代替。
- 只整理首尾空白和换行，不删除导航、不改写正文、不摘要。
- 单次搜索内，整理后的 URL 和正文均相同才去重，保留第一次出现的顺序。同 URL 不同片段保留。
- 不合并 www、不删除查询参数，不做跨轮次去重或重复搜索惩罚。
- 坏条目只记首个排除原因，有效条目不受其他坏条目影响。

### read_page(url, start=0)

通过 Tavily Extract 的 `basic` 提取指定 URL，返回 Markdown 文本，不搜索替代页面，不调用摘要模型。读取公开 HTTP(S) 文本网页，不支持登录、点击操作或本地文件。

- `start=0` 重新请求该页面，并在临时会话中保存内容快照。
- 每次最多返回 24,000 字符；长页面给出 `next_start`，模型可用同一个 URL 和该起点继续读取。
- 续读使用同一快照，不重复联网。结果包含 `snapshot_id`、`start/end`、总字符数及下一起点。
- `success` 代表本次返回全部已提取文本；`partial` 代表只返回该快照的一段。最后一段也仍是 partial，只是 next_start 为空。
- 请求地址和服务报告地址分别保留；Extract 没有提供可核实的最终重定向地址，`final_url` 为 null，不从报告地址猜测。
- 返回全部提取文本不等于网站全文完整无缺。网页未记载也不等于现实中不存在该事实。
- 新读取失败时不保留当前输入中的旧快照供续读；整次输入失败时 Session 仍回退到提问前。
- 地址校验阻止本地文件、凭据 URL、localhost 和非公网 IP 字面量；这是请求形式校验，不是对 provider DNS 或重定向行为的安全认证。本机代理 DNS 不参与 provider 地址校验。

### think_tool

默认参数仍为 `reflection`，记录模型显式笔记。返回 `content_kind=model_note`，不是新增外部证据。

可用独立实验开关切换结构：

```powershell
uv run python -X utf8 main.py --repl --verbose --structured-think
```

实验字段为 `goal`（当前目标）、`observations`（实际观察）、`assessment`（判断与不确定性）、`next_step`（下一步及希望获得的信息）、`references`（已有搜索/读取的 tool_call_id，可为空）。只检查引用操作存在，不认证引用内容是否支持判断。失败操作也可以作为“尝试失败”的观察引用。模型仍可不调用 think 直接回答。

结构化模式已完成真实调用验证，但尚未证明普遍提升答案质量，因此默认关闭。

## 操作结果与显示

三个工具共同返回 `operation`、`status`、`content_kind`；具体内容由各工具提供。

|状态|含义|
|---|---|
|success|取得本次操作预期的数据或保存笔记；不表示结论已核实|
|empty|搜索正常完成但无命中|
|partial|读取返回了提取快照的一部分|
|failed|请求失败、数据不合法、提取失败或所有搜索条目被排除|

失败包含 `error_code` 和可读 `error`；API HTTP 状态与 provider 报告的页面失败原因分别表达。404 等可识别原因会保留，未知原因不猜测。认证错误正文和请求头不回传。

`--verbose` 仅控制 stderr 显示：按轮次显示调用、参数、实际结果、读取范围、结果写回和预算。不打印系统提示词或历史副本；笔记不机械回显两遍；最终答案只写入 stdout。`display.py` 与模型消费同一份工具结果，显示不改变消息、工具参数或结果。API key 在显示副本中遮蔽，不输出 reasoning_content。

## Session 与文件职责

|文件|职责|
|---|---|
|agent.py|模型请求、工具循环、当前轮次、成功提交与失败回退|
|tools.py|工具定义、参数校验和分派，选择笔记实验模式|
|retrieval.py|Search/Extract 获取、结果整理、页面范围与快照|
|operations.py|公共操作状态及失败结果构造|
|display.py|终端事件展示，无研究决策|
|session.py|已完成消息和页面快照的内存容器|
|main.py|配置、单次命令、REPL 生命周期|
|tests/|不联网的工程测试|

`run_agent(..., session=同一个Session)` 可连续提问；不传时使用临时 Session。每次输入深复制消息和页面快照，只在正常取得非空答案后一起保存。请求失败、截断、空答案、超限或中断不保存本次临时数据。工具错误如果已回传且最终正常回答，则作为成功完成研究的一部分保留。

一个 Session 只支持顺序调用；退出程序后丢失。`Session.clear()` 同时清空消息与页面快照。研究笔记已经保存在对应 assistant/tool 消息中，没有额外可失同步的笔记数据库。长会话仍可能超过模型上下文限制。

## 验证

```powershell
uv run python -X utf8 -m unittest discover -s tests -v
```

测试覆盖动态搜索、消息配对、参数与结果校验、分页快照、失败原因、预算、Session 回退、REPL、显示开关不改变请求以及笔记引用。真实验收记录见 `docs/harness-validation.md`，区分功能验证与模型回答质量。

## 指导项目和范围

参考 `langchain-ai/deep_research_from_scratch` 提交 `93f35e5d2a51590f9542207a9ff66a01901da5bc` 的 Notebook 2、research_agent.py、utils.py、state_research.py。保留“模型自主决策 → 工具结果写回 → 再决策”的核心；用内存列表维护消息，用普通 Python 执行循环。

当前没有照搬上游逐网页模型摘要及研究结束压缩。明确 URL 读取是实验支持的能力补充，采用 Tavily Extract；没有加入多 Agent、MCP、数据库、持久化、LangSmith、rerank 或大型评估框架。

官方协议：
- [DeepSeek 工具调用](https://api-docs.deepseek.com/guides/tool_calls/)
- [Tavily Search](https://docs.tavily.com/documentation/api-reference/endpoint/search)
- [Tavily Extract](https://docs.tavily.com/documentation/api-reference/endpoint/extract)
