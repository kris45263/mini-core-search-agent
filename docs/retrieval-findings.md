# 检索与页面噪声研究结论

2026-09-08。本文保留已执行探索的结论与边界；当前实现以 [架构说明](architecture.md) 为准，运行验收见 [验收记录](harness-validation.md)。旧阶段计划已合并，不再作为待办指令。

## 两类目标

- 检索能力：让模型表达候选数量与来源范围，观察是否取得足够证据。参数可用不等于模型每次选择合理。
- 用户可观测性：直接展示搜索词、标题、URL 和读取对象。模型本来已经收到这些字段；显示更充分不等于答案更准确。

这两项已实现。跨次来源数据库、语义去重、自动 advanced 和通用噪声过滤没有实现，当前证据不足以支持优先引入。

## Search 机制与小样本

Search 返回候选来源及相关片段；Extract 读取明确 URL。max_results 控制条目数，chunks_per_source 控制单来源的片段；相关性 score 不代表真实性。当前只向模型保留 title/url/content、处理状态和实际搜索参数，不保留 score 或 favicon。标题来自 provider，缺失时用 URL 兜底。

同题“DeepSeek 官网 视觉模型 图像理解”，每种配置一次，均显式指定结果上限：

|配置|返回数/不同URL|官方文档条目|content总字符|
|---|---|---|---|
|basic、3条|3/3|1|4153|
|basic、6条|6/6|1|6600|
|basic、3条、官方域名filter|3/3|3|3559|
|advanced、3条|3/3|1|5700|
|basic、3条、chunks=1|3/3|1|1349|

增加至6条新增三个第三方URL，没增加官方来源。限定域名更直接符合这次来源要求，但中英文文档不等于独立证据。advanced 没有增加官方来源；chunks变化时URL也变了，不能把全部变化归因于该参数。不是跨题质量或稳定性评估。

上次两查询的六条结果只有五个不同URL；同一个中文Vision页面在不同查询中返回不同片段。因此“再次命中”不一定无用，“新URL”不一定新事实。上述五组本地精确去重删除数均为零；它只处理同一次响应中URL和内容都相同的条目，不承担搜索策略职责。

证据：[首次取样](testing/results/tavily-structure-sample-20260908.json)、[参数与提取取样](testing/results/tavily-mechanism-probe-20260908.json)。官方：[Search](https://docs.tavily.com/documentation/api-reference/endpoint/search)、[搜索实践](https://docs.tavily.com/documentation/best-practices/best-practices-search)。官方页面对默认数量描述不完全一致，项目显式传值，不依赖默认。

## Extract 成功与目标匹配

正常Vision页面返回10898字符；一个刻意构造的不存在路径返回4131字符的“Your First API Call”介绍，failed_results为空，报告URL仍是请求地址。回放当前read_page，两者都判success。不能确定是网站回退、重定向、缓存还是provider行为；没有取得最终跳转链。

这说明取得文本不证明目标匹配；返回全文快照也不保证网页完整。正常页面提取结果还出现重复代码展示。read_page的partial是本地每24000字符分段的状态，不是provider对网页完整性的认证。Python页面37718字符分两段返回，第二段仍partial但next_start为空。

Extract的query可以对相关片段重排，但对“本页是否记载”的问题不能将相关片段当全文。尚未实测 advanced 对复杂提取的收益。[Extract文档](https://docs.tavily.com/documentation/api-reference/endpoint/extract)

## GitHub 加载提示噪声

对于查版本修复，Loading、Uh oh和加载失败提示是界面噪声；对调查页面故障，它们可能是证据。下载哈希对修复问题未必有用，但对下载校验有用，不能全局删除。

GitHub源页面文本也含相同提示；Tavily片段/正文保留它，本地只做结构清理，随后整个结果进入tool消息。没有provider内部日志，不能确认是动态加载失败还是备用提示被提取。它不是harness生成的API错误。

|同日探查|字符数|固定加载错误句次数|
|---|---:|---:|
|第一次Search|1402|1|
|同请求再Search|1402|1|
|Extract releases汇总页|51760|11|
|Extract具体v7.5.10页|11921|3|

重复Search只返回一条，内容哈希相同，可能有缓存；不能估计长期出现率。具体页面少约77%文字，资料更集中，但仍有噪声，不能说已解决。汇总页按本地范围需三段才能遍历，具体页一段即可。

两组DeepSeek证据消费对照：固定问题要求v7.5.10的Engine Updates and Fixes及PR编号。原文11921字符；只删除三种完全匹配界面行后11694字符，减少227字符（约1.9%）。两组均正确选出pwsh -file高级函数脚本dot-sourcing修复和PR #27761；清理后回答更啰嗦，没有观察到准确率收益。每组一次，不能据耗时比较因果，也不覆盖自主工具决策。

证据：[抓取与重复计数](testing/results/tavily-noise-probe-20260908.json)、[原文/清理副本回答](testing/results/noise-answer-pair-20260908.json)。页面：[PowerShell Releases](https://github.com/PowerShell/PowerShell/releases)。删除仅用于实验副本，不是生产规则。

## 后续触发条件

先用已开放的搜索数量/域名控制及更精确页面选择解决具体任务。只有反复观察到噪声挤掉目标证据、导致误读或无效重试、明显增加上下文成本，再做少量对照评估清理方案及误删风险。

保持页面界面提示、工具请求失败、目标不匹配和任务无关正文四者分开；不要用含error/404即删除的特例规则。仍待观察：模型参数选择质量、长标题显示、语言版本混淆、最终结论归因。避免把单次真实成功或测试通过表述成通用答案质量提升。
