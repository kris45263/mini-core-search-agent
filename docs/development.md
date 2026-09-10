# 开发指南

Seekra 使用 Python 3.13、uv 和普通同步 Python 模块。首次运行与用户命令见 [README](../README.md)，修改核心前先读 [架构与契约](architecture.md)。

## 环境与运行

在仓库根目录执行：

```powershell
uv sync --locked
uv run seekra --help
uv run seekra --repl
```

首次使用需将 `.env.example` 复制为 `.env` 并填写 DeepSeek、Tavily 配置。已有配置不要覆盖。CLI 默认只读启动目录的 `.env`；在其它目录运行时使用 `--env-file PATH`。帮助、版本和离线工程测试无需真实密钥。

使用 `uv tool install --python 3.13 --editable .` 可安装本地源码命令。移动源码目录后需重新安装；项目虚拟环境可通过 `uv sync --locked` 重新绑定当前源码。安装命令的详细说明见 README。

## 如何定位修改

|修改目标|主要模块|需要关注的回归|
|---|---|---|
|模型决策循环、预算|`src/seekra/agent.py`|请求历史、工具配对、超限与失败回退|
|流式协议|`src/seekra/deepseek.py`|分片、DONE、工具组装、连接释放|
|工具接口与校验|`src/seekra/tools.py`、`operations.py`|非法参数不联网、操作结果语义|
|Search/Extract|`src/seekra/retrieval.py`|结果整理、失败原因、分页与快照|
|终端展示|`src/seekra/display.py`|正文一次输出、请求不变、诊断故障隔离|
|命令与会话入口|`src/seekra/cli.py`|配置来源、独立目录安装入口、REPL|

## 工程验证

```powershell
uv run python -X utf8 -m unittest discover -s tests -v
```

测试从已安装的同一个 `seekra` 包导入，使用假配置和 MockTransport，不访问真实模型或搜索服务。安装入口测试会在临时目录中启动子进程。测试类别与真实能力判定见 [验证指南](validation.md)。

## 真实服务验证

列出用例不会调用 API：

```powershell
uv run python -X utf8 scripts/run_live_case.py --list
```

显式运行会调用已配置服务并产生费用；输出路径必须是新文件：

```powershell
uv run python -X utf8 scripts/run_live_case.py --case page --output evals/runs/page.json
```

`evals/runs/` 用于新运行产物；已选择用于解释项目行为的证据见 [证据索引](../evals/README.md)。现有 `run_live_case.py` 记录操作摘要和页面片段，不能代替完整请求对照。需要检查证据供应或 think 格式差异时使用索引中对应的实验脚本。

`scripts/check_streaming.py` 是无工具流式开发验收入口，复用生产 SSE 接收器；它可测试直接回答与追问，不代表完整搜索 Agent 通过验收。

## 构建与分发

```powershell
uv build
```

`dist/` 内的 wheel 和源码包是构建时的快照，不随源码编辑更新；可编辑安装运行当前源码，不依赖这些包。需要分发时重新构建并验证安装入口。

本项目当前没有把真实服务实验变成自动通过/失败的 CI 评分。离线测试成功只证明所覆盖的工程行为，不能认证答案事实正确。
