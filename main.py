"""命令行入口：从项目 .env 读取配置，运行一次搜索并输出最终答案。"""

import argparse
from pathlib import Path
import sys

from dotenv import dotenv_values
import httpx

from agent import run_agent


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


def main() -> int:
    """解析问题和循环上限，失败时输出简短提示并返回非零退出码。"""
    parser = argparse.ArgumentParser(description="最小迭代搜索 Agent：DeepSeek + Tavily")
    parser.add_argument("question", help="需要研究的问题，请用引号包住")
    parser.add_argument("--max-iterations", type=int, default=12, help="最多模型决策次数，默认 12")
    parser.add_argument("--verbose", action="store_true", help="在 stderr 显示研究过程")
    args = parser.parse_args()
    try:
        config = read_config(Path(__file__).resolve().with_name(".env"))
        with httpx.Client() as client:
            answer = run_agent(
                args.question, client=client, model=config["DEEPSEEK_MODEL"],
                deepseek_api_key=config["DEEPSEEK_API_KEY"],
                tavily_api_key=config["TAVILY_API_KEY"], max_iterations=args.max_iterations,
                verbose=args.verbose,
            )
        print(answer)
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


if __name__ == "__main__":
    raise SystemExit(main())
