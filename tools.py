"""最小研究工具：提供 Tavily 搜索和研究笔记回写，不引入额外模型或框架。"""

import json

import httpx


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
    """执行单次搜索，将三个结果的标题、链接和内容原样写入 JSON。"""
    response = client.post(
        "https://api.tavily.com/search",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"query": query, "search_depth": "basic", "max_results": 3,
              "include_answer": False, "include_raw_content": False},
        timeout=30,
    )
    response.raise_for_status()
    # 只选择研究所需字段，不再调用模型摘要，也不截断返回的内容片段。
    results = [{key: item[key] for key in ("title", "url", "content")}
               for item in response.json()["results"]]
    return json.dumps({"query": query, "results": results}, ensure_ascii=False)


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
