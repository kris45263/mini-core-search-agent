"""进程内研究会话：保存已完成输入的消息历史，退出程序后不保留。"""

from dataclasses import dataclass, field


@dataclass
class Session:
    """供顺序提问复用的历史容器；不负责模型请求、工具执行或并发访问。"""

    messages: list[dict] = field(default_factory=list)
    pages: dict[str, dict] = field(default_factory=dict)

    def clear(self) -> None:
        """清空全部已完成历史，使下一次提问从新会话开始。"""
        self.messages.clear()
        self.pages.clear()
