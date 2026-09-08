# 模块与数据约定

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

### tavily_search(query, max_results=3, include_domains=None)

使用 `basic`，模型可选择 1–10 条候选，省略默认 3，不请求 raw content 或 provider 生成的答案。可选 include_domains 最多 10 个域名，空列表或省略不限制；仅接受明确 ASCII 主机名，不含协议、路径、IP 或通配符，规范化空白/大小写并去重。有域名时明确发送 include_domains_mode=filter，不自动退回全网。返回 query、results[{title,url,content}]、processing 和实际 search_parameters；API 失败也保留有效请求参数供核查。参数不合法在联网前作为 invalid_arguments 回传模型。

模型根据任务选择数量和域名，不新增用户开关；这提供检索控制能力，不保证模型每次都会选择最优参数。普通显示直接使用 provider 标题和 URL，模型历史与内容不因显示清理而改变。标题和链接在显示副本中遮蔽配置密钥及终端控制字符，原始正文不做语义去噪。

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

普通界面向 stderr 显示“正在思考/搜索/读取网页/整理信息”等简短状态；`--verbose` 额外显示轮次、参数、实际结果、读取范围、结果写回和预算。正文增量写 stdout，模型工具前说明也会显示，不在完成后重复输出。内部工具 JSON 不进入普通正文，隐藏 reasoning_content 不展示。详细调试显示副本遮蔽 API key，stdout 正文保留原文。

`deepseek.py` 使用同步 SSE 接收，按工具 index 累计独立调用，完整 finish_reason 和 DONE 后校验所有调用，再交给 `agent.py` 依次执行。流式消息不逐片写入历史。无工具验收与主 Agent 共用该接收器，不创建第二套 Agent 核心。模型响应完成事件先结束正文行，再显示工具状态；整个问题仍仅在成功答案后提交 Session。

工具 id/type/name 必须保持一致，arguments 字符串累计后交给 execute_tool 解析；整轮所有调用结构通过校验后才执行第一个工具。正常结束为 stop 且正文非空、无工具，或 tool_calls 且工具完整。缺 DONE、截断、协议异常或网络中断均失败，不自动重试、不退回非流式。

run_agent 的 on_content 回调逐段通知正文，on_event 通知模型/工具生命周期；函数仍返回完整最终答案。不传回调的程序调用者可以只消费返回值。CLI 不重复 print 返回答案。已显示文字无法撤回，stdout 重定向可能保留工具前说明或失败残稿。

“正在思考”是界面状态，不能推断模型启用了 thinking。verbose 的首段正文时间从本轮模型调用事件到首个含非空白字符片段写入并 flush 后计算，是显示提交时刻的近似值，不是精确屏幕渲染时刻；总耗时包含等待与接收，片段数单位为段，不等于 token 数。程序没有人为限速。

未增加独立 chat/stream 产品开关，不实现关键词去噪、语义去重或额外来源数据库。事实依据和保留问题见 [研究结论](retrieval-findings.md)，运行证据见 [验收记录](harness-validation.md)。

## Session 与文件职责

|文件|职责|
|---|---|
|agent.py|模型请求、工具循环、当前轮次、成功提交与失败回退|
|deepseek.py|共享流式接收、消息组装、结束校验与连接释放|
|tools.py|工具定义、参数校验和分派，选择笔记实验模式|
|retrieval.py|Search/Extract 获取、结果整理、页面范围与快照|
|operations.py|公共操作状态及失败结果构造|
|display.py|终端事件展示，无研究决策|
|session.py|已完成消息和页面快照的内存容器|
|main.py|配置、单次命令、REPL 生命周期|
|tests/|不联网的工程测试|

`run_agent(..., session=同一个Session)` 可连续提问；不传时使用临时 Session。每次输入深复制消息和页面快照，只在正常取得非空答案后一起保存。请求失败、截断、空答案、超限或中断不保存本次临时数据。工具错误如果已回传且最终正常回答，则作为成功完成研究的一部分保留。

一个 Session 只支持顺序调用；退出程序后丢失。`Session.clear()` 同时清空消息与页面快照。研究笔记已经保存在对应 assistant/tool 消息中，没有额外可失同步的笔记数据库。长会话仍可能超过模型上下文限制。
