"""命令行入口：从项目 .env 读取配置，运行单次搜索或复用会话连续输入。"""

import argparse
from importlib.metadata import version
import io
from pathlib import Path
import sys

from dotenv import dotenv_values
import httpx

from .agent import run_agent
from .session import Session
from .display import AgentDisplay


REPL_HELP = """/help  查看帮助
/new   清空会话，开始新对话
/exit  退出 Seekra

回答期间 Ctrl+C 取消本次提问；等待输入时 Ctrl+C 或 EOF 退出。
会话只保留在当前进程中。"""


def read_config(path: Path) -> dict[str, str]:
    """仅从指定 .env 读取三个配置项，不回退到系统环境或展开环境变量。"""
    if not path.is_file():
        raise ValueError(f"未找到配置文件：{path.resolve()}。请复制 .env.example 为 .env 并填写配置，"
                         "或使用 --env-file 指定文件。")
    values = dotenv_values(path, interpolate=False, encoding="utf-8-sig")
    config = {}
    for name in ("DEEPSEEK_API_KEY", "DEEPSEEK_MODEL", "TAVILY_API_KEY"):
        value = (values.get(name) or "").strip()
        if not value or "${" in value:
            raise ValueError(f"请在配置文件 {path} 中直接填写 {name}")
        config[name] = value
    return config


def run_question(question: str, *, client: httpx.Client, config: dict,
                 session: Session, max_iterations: int, verbose: bool, structured_think: bool = False) -> int:
    """执行一个问题并报告错误；失败时由调用者决定退出还是继续输入。"""
    view = AgentDisplay(verbose, secrets=(config['DEEPSEEK_API_KEY'], config['TAVILY_API_KEY']))
    try:
        run_agent(
            question, client=client, session=session, model=config["DEEPSEEK_MODEL"],
            deepseek_api_key=config["DEEPSEEK_API_KEY"], tavily_api_key=config["TAVILY_API_KEY"],
            max_iterations=max_iterations, verbose=verbose,
            structured_think=structured_think,
            on_content=view.content, on_event=view.event,
        )
        return 0
    except (ValueError, RuntimeError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
    except httpx.HTTPStatusError as exc:
        print(f"错误：DeepSeek 请求失败（HTTP {exc.response.status_code}），请检查 .env 配置和账户状态。",
              file=sys.stderr)
    except httpx.RequestError:
        print("错误：DeepSeek 网络连接失败或超时。", file=sys.stderr)
    except (KeyError, IndexError, TypeError):
        print("错误：DeepSeek 返回的数据格式异常。", file=sys.stderr)
    except KeyboardInterrupt:
        print("已取消。本次问答不会加入后续对话。", file=sys.stderr)
        return 130
    except (OSError, UnicodeError):
        print("终端输出失败，已停止当前任务。", file=sys.stderr)
        return 74
    print("本次回答未完成，本次问答不会加入后续对话。", file=sys.stderr)
    return 1


def main() -> int:
    """启动单次问答或 REPL，共用配置、客户端和当前内存会话。"""
    # 入口统一处理文本编码，用户不再需要传入 python -X utf8。
    # 仅配置真实文本流；嵌入调用和测试提供的自定义输出对象保持原样。
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(
        prog="seekra", description="Seekra · 终端搜索研究助手", add_help=False,
        epilog='连续对话：seekra --repl  |  单次提问：seekra "你的问题"',
    )
    parser.add_argument("-h", "--help", action="help", help="查看命令帮助并退出")
    parser.add_argument("--version", action="version", version=f"%(prog)s {version('seekra')}",
                        help="查看版本并退出")
    parser.add_argument("--env-file", type=Path, default=Path(".env"), metavar="PATH",
                        help="配置文件路径，默认读取当前工作目录的 .env")
    parser.add_argument("question", nargs="?", help="单次研究问题，请用引号包住")
    parser.add_argument("--repl", action="store_true", help="启动可连续输入的内存会话")
    parser.add_argument("--max-iterations", type=int, default=12, help="每个问题最多模型决策次数，默认 12")
    parser.add_argument("--verbose", action="store_true", help="在 stderr 显示研究过程")
    parser.add_argument("--structured-think", action="store_true", help="实验：使用结构化显式研究笔记")
    args = parser.parse_args()
    if args.repl == (args.question is not None):
        parser.error("请提供一个问题，或使用 --repl；两者不能同时使用")
    if args.max_iterations < 1:
        parser.error("最大循环次数必须大于零")
    try:
        config = read_config(args.env_file)
    except (ValueError, OSError) as exc:
        print(f"配置错误：{exc}", file=sys.stderr)
        return 1
    session = Session()
    with httpx.Client() as client:
        if not args.repl:
            return run_question(args.question, client=client, config=config, session=session,
                                max_iterations=args.max_iterations, verbose=args.verbose, structured_think=args.structured_think)
        print("\nSeekra · 搜索研究助手\n输入问题开始研究。/help 查看帮助 · /new 新对话 · /exit 退出\n",
              file=sys.stderr)
        while True:
            try:
                print("› ", end="", file=sys.stderr, flush=True)
                question = input().strip()
            except (EOFError, KeyboardInterrupt):
                print("\n会话已结束。", file=sys.stderr)
                return 0
            if not question:
                continue
            if question == "/exit":
                print("会话已结束。", file=sys.stderr)
                return 0
            if question == "/help":
                print(REPL_HELP + "\n", file=sys.stderr)
                continue
            if question == "/new":
                session.clear()
                print("已开始新对话。", file=sys.stderr)
                continue
            if question.startswith("/"):
                print("未知命令。输入 /help 查看可用命令。", file=sys.stderr)
                continue
            # run_question 报告失败后返回；Session 保留此前成功历史，继续等待输入。
            status = run_question(question, client=client, config=config, session=session,
                         max_iterations=args.max_iterations, verbose=args.verbose, structured_think=args.structured_think)
            if status == 74:
                return status


if __name__ == "__main__":
    raise SystemExit(main())
