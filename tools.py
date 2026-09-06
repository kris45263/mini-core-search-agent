"""最小研究工具：提供 Tavily 搜索和研究笔记回写，不引入额外模型或框架。"""

import json
from typing import NotRequired, TypedDict
from urllib.parse import urlsplit

import httpx


class SearchResult(TypedDict):
    """经过校验的单条来源，字段均为非空字符串。"""
    title: str
    url: str
    content: str


class ProcessingInfo(TypedDict):
    """本次结果处理计数，用于说明保留数量与排除原因。"""
    received: int
    kept: int
    removed: dict[str, int]


class SearchResponse(TypedDict):
    """搜索工具的成功或全部过滤结果；请求失败仍沿用 error 返回。"""
    query: str
    results: list[SearchResult]
    processing: ProcessingInfo
    error: NotRequired[str]


def normalize_search_results(query: str, response: object) -> SearchResponse:
    """显式校验原始字典并保守整理；TypedDict 本身不执行运行时校验。

    坏条目只记首个失败原因。精确去重限定本次调用，保留首次出现顺序。
    URL 只做语法检查，既不验证可访问性，也不合并域名或查询参数。
    """
    if not isinstance(query, str) or not query.strip():
        raise ValueError("查询必须为非空字符串")
    if not isinstance(response, dict) or not isinstance(response.get("results"), list):
        raise ValueError("Tavily 响应必须包含 results 列表")
    results: list[SearchResult] = []
    removed: dict[str, int] = {}
    seen: set[tuple[str, str]] = set()
    for item in response["results"]:
        reason = ""
        if not isinstance(item, dict):
            reason = "invalid_item"
        elif not isinstance(item.get("url"), str):
            reason = "invalid_url"
        else:
            url = item["url"].strip()
            try:
                parts = urlsplit(url)
                if (parts.scheme not in {"http", "https"} or not parts.hostname
                        or any(c.isspace() or ord(c) < 32 for c in url)):
                    reason = "invalid_url"
                # 读取 port 会检查非法端口；不对合法 URL 做重写。
                _ = parts.port
            except ValueError:
                reason = "invalid_url"
            if not reason:
                content = item.get("content")
                title = item.get("title")
                if not isinstance(content, str) or (title is not None and not isinstance(title, str)):
                    reason = "invalid_fields"
                else:
                    content = content.replace("\r\n", "\n").replace("\r", "\n").strip()
                    title = (title or "").replace("\r\n", "\n").replace("\r", "\n").strip() or url
                    if not content:
                        reason = "empty_content"
                    elif (url, content) in seen:
                        reason = "duplicate"
                    else:
                        seen.add((url, content))
                        results.append({"title": title, "url": url, "content": content})
        if reason:
            removed[reason] = removed.get(reason, 0) + 1
    output: SearchResponse = {
        "query": query, "results": results,
        "processing": {"received": len(response["results"]), "kept": len(results), "removed": removed},
    }
    if response["results"] and not results:
        output["error"] = "Tavily 返回的条目全部被过滤，本次没有可用搜索证据。"
    return output


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "tavily_search",
            "description": "搜索网络获取新信息。根据当前信息缺口提出一个查询，返回标题、链接及内容片段。",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "本次搜索词"}},
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "think_tool",
            "description": "记录简短研究笔记：已有证据、仍缺的信息、下一步搜索或结束。不会获取新事实。",
            "parameters": {
                "type": "object",
                "properties": {"reflection": {"type": "string", "description": "简短的研究进展与下一步"}},
                "required": ["reflection"],
                "additionalProperties": False,
            },
        },
    },
]


def tavily_search(query: str, *, client: httpx.Client, api_key: str) -> str:
    """执行单次搜索，经字段校验、文本整理和精确去重后返回 JSON。"""
    response = client.post(
        "https://api.tavily.com/search",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"query": query, "search_depth": "basic", "max_results": 3,
              "include_answer": False, "include_raw_content": False},
        timeout=30,
    )
    response.raise_for_status()
    return json.dumps(normalize_search_results(query, response.json()), ensure_ascii=False)


def think_tool(reflection: str) -> str:
    """回显模型提交的研究笔记；笔记通过工具消息留在当前上下文中。"""
    return f"已记录研究笔记：{reflection}"


def execute_tool(tool_call: dict, *, client: httpx.Client, api_key: str) -> str:
    """校验并执行两个允许的工具，将可恢复的失败作为工具结果返回。"""
    name = tool_call["function"]["name"]
    try:
        if name not in {"tavily_search", "think_tool"}:
            raise ValueError("未知工具，只允许 tavily_search 和 think_tool")
        arguments = json.loads(tool_call["function"]["arguments"])
        parameter = "query" if name == "tavily_search" else "reflection"
        if (not isinstance(arguments, dict) or set(arguments) != {parameter}
                or not isinstance(arguments[parameter], str)
                or not arguments[parameter].strip()):
            raise ValueError(f"参数必须且只能包含非空字符串 {parameter}")
    except (ValueError, TypeError) as exc:
        return json.dumps({"error": f"工具参数错误：{exc}"}, ensure_ascii=False)

    if name == "think_tool":
        return think_tool(arguments["reflection"])
    try:
        result = tavily_search(arguments["query"], client=client, api_key=api_key)
        return result
    except httpx.HTTPStatusError as exc:
        error = f"Tavily 请求失败（HTTP {exc.response.status_code}），本次未获取搜索证据。"
    except httpx.RequestError:
        error = "Tavily 网络连接失败或超时，本次未获取搜索证据。"
    except (ValueError, KeyError, TypeError):
        error = "Tavily 返回的数据格式异常，本次未获取搜索证据。"
    # 不回传服务端错误正文，避免将无关或敏感信息加入研究历史。
    return json.dumps({"error": error}, ensure_ascii=False)
