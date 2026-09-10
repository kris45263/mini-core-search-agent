"""终端事件展示：只读取操作结果，不生成证据、不更改模型上下文。"""

import json
import sys
import time
import unicodedata


def display_text(value: object, secrets: tuple[str, ...] = (), *, single_line: bool = False) -> str:
    """只处理显示副本：遮蔽密钥与终端控制字符，不改证据或模型消息。"""
    text = str(value)
    for secret in secrets:
        if secret:
            text = text.replace(secret, '[已隐藏密钥]')
    text = ''.join(c if c in '\n\t' or unicodedata.category(c) not in {'Cc', 'Cf'}
                   else f'\\u{ord(c):04x}' for c in text)
    return ' '.join(text.splitlines()) if single_line else text


class TextStreamWriter:
    """正文逐段写入并刷新；与可忽略写入故障的调试展示不同。"""

    def __init__(self):
        """绑定当前 stdout，记录终端行状态。"""
        self.output = sys.stdout
        self.needs_newline = False

    def write(self, text: str) -> None:
        """原样输出非空片段，写入或刷新失败向上传播。"""
        if text:
            self.output.write(text)
            self.needs_newline = not text.endswith("\n")
            self.output.flush()

    def finish(self) -> None:
        """必要时补换行，重复调用不会重复输出。"""
        if self.needs_newline:
            self.write("\n")


class AgentDisplay:
    """普通状态与模型正文；性能数字仅在 verbose 下显示。"""

    def __init__(self, verbose: bool = False, secrets: tuple[str, ...] = ()):
        self.writer = TextStreamWriter()
        self.verbose = verbose
        self.started = None
        self.first = None
        self.fragments = 0
        self.secrets = secrets

    def content(self, text: str) -> None:
        """立即展示正文；记录首段可见字符写入刷新的近似时刻。"""
        self.writer.write(text)
        self.fragments += 1
        if self.first is None and text.strip():
            self.first = time.monotonic()

    def event(self, event: str, **details) -> None:
        """只由真实模型/工具事件触发状态，不写进模型上下文。"""
        text = None
        if event == 'model_call':
            self.started = time.monotonic()
            self.first = None
            self.fragments = 0
            text = '正在思考…'
        elif event == 'model_response':
            self.writer.finish()
            if self.verbose and self.started is not None:
                elapsed = time.monotonic() - self.started
                first = f'{self.first - self.started:.3f} 秒' if self.first is not None else '无正文'
                text = f'本轮模型：首段正文 {first}，总耗时 {elapsed:.3f} 秒，正文片段 {self.fragments} 段。'
        elif event == 'tool_call':
            name = details['tool_call']['function']['name']
            text = {'tavily_search': '正在搜索…', 'read_page': '正在读取网页…',
                    'think_tool': '正在整理信息…'}.get(name, '正在执行工具…')
            try:
                args = json.loads(details['tool_call']['function']['arguments'])
                if isinstance(args, dict):
                    if name == 'tavily_search':
                        text += '\n搜索词：' + display_text(args.get('query', ''), self.secrets, single_line=True)
                        domains = args.get('include_domains')
                        if isinstance(domains, list) and domains:
                            text += '\n限定来源：' + display_text('、'.join(map(str, domains)), self.secrets, single_line=True)
                    elif name == 'read_page':
                        start = args.get('start', 0)
                        if type(start) is int and start > 0:
                            text = '正在续读已有页面内容…'
                        text += '\n' + display_text(args.get('url', ''), self.secrets, single_line=True)
            except (ValueError, TypeError):
                pass
        elif event == 'tool_result':
            try:
                result = json.loads(details['result'])
                status = result.get('status')
                if status == 'failed':
                    text = '本次工具未能完成，继续根据已有信息处理。'
                elif details['tool_name'] == 'tavily_search':
                    text = '未找到相关结果。' if status == 'empty' else f"找到 {len(result.get('results', []))} 条结果。"
                    for number, row in enumerate(result.get('results', []), 1):
                        title = display_text(row.get('title') or row.get('url', ''), self.secrets, single_line=True)
                        url = display_text(row.get('url', ''), self.secrets, single_line=True)
                        text += f'\n  {number}. {title}\n     {url}'
                elif details['tool_name'] == 'read_page':
                    if status == 'partial':
                        text = ('已取得本次提取内容的最后一部分。' if result.get('next_start') is None
                                else '已取得本次提取内容的一部分，可继续读取。')
                    else:
                        text = '已取得页面文本。'
                    text += '\n' + display_text(result.get('title') or result.get('url', ''), self.secrets, single_line=True)
            except (ValueError, TypeError, AttributeError):
                text = '工具已返回结果。'
        elif event == 'end':
            try:
                self.writer.finish()
            except (OSError, UnicodeError):
                pass  # 保留原始异常，不在异常清理时再次写坏掉的 stdout。
        if text:
            self._write_status(text)
        if self.verbose:
            detail = _verbose_text(event, **details)
            if detail:
                self._write_status(detail)

    def _write_status(self, text: str) -> None:
        """诊断只改显示副本；输出失败不改变研究执行。"""
        try:
            print(display_text(text, self.secrets), file=sys.stderr, flush=True)
        except (OSError, UnicodeError):
            pass


def _verbose_text(event: str, **details) -> str | None:
    """将生命周期事件格式化为详细诊断；不写终端，不重复正文。"""
    if event == "start":
        text = f"任务\n{details['question']}"
    elif event == "model_call":
        text = (f"\n── 第 {details['round']} 轮 ──\n"
                f"模型调用：上下文 {details['message_count']} 条消息；"
                f"本次之后剩余 {details['remaining']} 次")
    elif event == "tool_call":
        function = details["tool_call"]["function"]
        text = f"\n工具 {details['number']}：{function['name']}\n"
        try:
            arguments = json.loads(function["arguments"])
        except (ValueError, TypeError):
            arguments = None
        if isinstance(arguments, dict):
            for key, value in arguments.items():
                label = {"query": "查询", "reflection": "研究笔记"}.get(key, key)
                shown = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
                text += f"{label}：\n{shown}\n"
        else:
            text += f"原始参数（未解析）：{function['arguments']}\n"
        text += "工具执行：开始"
    elif event == "tool_result":
        result = details["result"]
        if details["tool_name"] == "think_tool" and result.startswith("已记录研究笔记："):
            text = "工具执行：研究笔记已记录"
        else:
            try:
                data = json.loads(result)
                if isinstance(data, dict) and "error" in data:
                    text = f"工具执行失败：{data['error']}"
                elif isinstance(data, dict) and data.get("content_kind") == "model_note":
                    text = "工具执行：研究笔记已记录（模型判断，不是外部证据）"
                elif isinstance(data, dict) and data.get("operation") == "read_page":
                    text = (f"页面读取：{data['status']}\n请求地址：{data['requested_url']}\n"
                            f"服务报告地址：{data['url']}\n最终地址：未知\n"
                            f"范围：{data['start']}–{data['end']} / {data['total_characters']} 字符\n"
                            f"继续起点：{data['next_start']}\n{data['coverage']}\n内容：\n{data['content']}")
                elif details["tool_name"] == "tavily_search" and isinstance(data, dict):
                    state = "无结果" if data["status"] == "empty" else "成功"
                    text = f"搜索完成：{state}，返回 {len(data['results'])} 条结果"
                    for number, item in enumerate(data["results"], 1):
                        text += (f"\n\n[结果 {number}] {item['title']}\n"
                                 f"链接：{item['url']}\n内容：\n{item['content']}")
                else:
                    text = f"工具结果：\n{result}"
                if isinstance(data, dict) and "processing" in data:
                    info = data["processing"]
                    labels = {"invalid_item": "条目不是对象", "invalid_url": "无效 URL",
                              "invalid_fields": "字段类型错误", "empty_content": "空正文",
                              "duplicate": "URL 与正文完全重复"}
                    reasons = "、".join(f"{labels.get(key, key)} {count} 条"
                                        for key, count in info["removed"].items()) or "无"
                    text += (f"\n结果处理：收到 {info['received']} 条，保留 {info['kept']} 条。"
                             f"排除：{reasons}")
            except (ValueError, KeyError, TypeError):
                text = f"工具结果（原文）：\n{result}"
        text += f"\n已写回上下文：当前 {details['message_count']} 条消息"
    elif event == "final_answer":
        text = ("模型决定：直接回答，不再调用工具\n\n"
                f"运行结束：模型返回最终答案，共 {details['round']} 轮模型调用。")
    elif event == "end":
        text = f"\n异常结束：{details['end_reason']}"
        if details.get("http_status") is not None:
            text += f"（HTTP {details['http_status']}）"
    else:
        return
    return text
