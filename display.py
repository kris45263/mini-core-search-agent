"""终端事件展示：只读取操作结果，不生成证据、不更改模型上下文。"""

import json
import sys


def make_emitter(verbose: bool, secrets: tuple[str, ...]):
    """建立当前运行的 stderr 展示函数；关闭时不输出，始终不保存日志。"""
    def emit(event: str, **details) -> None:
        """输出一条可观察事件；只处理显示副本，不保存文件或更改研究状态。"""
        if not verbose:
            return
        if event == "start":
            text = f"任务\n{details['question']}"
        elif event == "model_call":
            text = (f"\n── 第 {details['round']} 轮 ──\n"
                    f"模型调用：上下文 {details['message_count']} 条消息；"
                    f"本次之后剩余 {details['remaining']} 次")
        elif event == "model_response":
            # 无工具调用的正常正文由 stdout 作为最终答案显示，不在这里重复。
            if not details.get("tool_calls") or not details.get("content"):
                return
            text = f"模型说明：\n{details['content']}"
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
        # 即使显式输出意外回显了本次密钥，也只在终端副本中遮蔽。
        for secret in secrets:
            if secret:
                text = text.replace(secret, "[已隐藏密钥]")
        try:
            print(text, file=sys.stderr, flush=True)
        except (OSError, UnicodeError):
            # 观察输出不可用时继续原有研究，避免开关影响实际请求。
            pass

    return emit
