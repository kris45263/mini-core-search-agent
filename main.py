"""命令行入口：从项目 .env 读取配置，运行单次搜索或复用会话连续输入。"""

import argparse
from pathlib import Path
import sys

from dotenv import dotenv_values
import httpx

from agent import run_agent
from session import Session


def read_config(path: Path) -> dict[str, str]:
    """仅从指定 .env 读取三个配置项，不回退到系统环境或展开环境变量。"""
    values = dotenv_values(path, interpolate=False, encoding="utf-8-sig")
    config = {}
    for name in ("DEEPSEEK_API_KEY", "DEEPSEEK_MODEL", "TAVILY_API_KEY"):
        value = (values.get(name) or "").strip()
        if not value or "${" in value:
            raise ValueError(f"请在项目 .env 中直接填写 {name}")
        config[name] = value
    return config


def run_question(question: str, *, client: httpx.Client, config: dict,
                 session: Session, max_iterations: int, verbose: bool) -> int:
    """执行一个问题并报告错误；失败时由调用者决定退出还是继续输入。"""
    try:
        answer = run_agent(
            question, client=client, session=session, model=config["DEEPSEEK_MODEL"],
            deepseek_api_key=config["DEEPSEEK_API_KEY"], tavily_api_key=config["TAVILY_API_KEY"],
            max_iterations=max_iterations, verbose=verbose,
        )
        print(answer, flush=True)
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
        print("研究已中断。", file=sys.stderr)
        return 130
    return 1


def main() -> int:
    """启动单次问答或 REPL，共用配置、客户端和当前内存会话。"""
    parser = argparse.ArgumentParser(description="最小迭代搜索 Agent：DeepSeek + Tavily")
    parser.add_argument("question", nargs="?", help="单次研究问题，请用引号包住")
    parser.add_argument("--repl", action="store_true", help="启动可连续输入的内存会话")
    parser.add_argument("--max-iterations", type=int, default=12, help="每个问题最多模型决策次数，默认 12")
    parser.add_argument("--verbose", action="store_true", help="在 stderr 显示研究过程")
    args = parser.parse_args()
    if args.repl == (args.question is not None):
        parser.error("请提供一个问题，或使用 --repl；两者不能同时使用")
    if args.max_iterations < 1:
        parser.error("最大循环次数必须大于零")
    try:
        config = read_config(Path(__file__).resolve().with_name(".env"))
    except (ValueError, OSError) as exc:
        print(f"配置错误：{exc}", file=sys.stderr)
        return 1
    session = Session()
    with httpx.Client() as client:
        if not args.repl:
            return run_question(args.question, client=client, config=config, session=session,
                                max_iterations=args.max_iterations, verbose=args.verbose)
        print("REPL 已启动。/new 清空会话，/exit 退出。", file=sys.stderr)
        while True:
            try:
                question = input("你：").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n会话已结束。", file=sys.stderr)
                return 0
            if not question:
                continue
            if question == "/exit":
                print("会话已结束。", file=sys.stderr)
                return 0
            if question == "/new":
                session.clear()
                print("已清空会话。", file=sys.stderr)
                continue
            if question.startswith("/"):
                print("未知命令。可用命令：/new、/exit。", file=sys.stderr)
                continue
            # run_question 报告失败后返回；Session 保留此前成功历史，继续等待输入。
            run_question(question, client=client, config=config, session=session,
                         max_iterations=args.max_iterations, verbose=args.verbose)


if __name__ == "__main__":
    raise SystemExit(main())
