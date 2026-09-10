# -*- coding: utf-8 -*-
"""命令行入口：intro（简介图）/ download（视频下载）子命令。"""

import argparse
import asyncio
import re
import sys

from .paths import normalize_bvid

_BV_RE = re.compile(r"[Bb][Vv][0-9A-Za-z]{10}")


def _extract_bv(target: str):
    """从目标字符串中提取并规范化 BV 号；提取不到返回 None（暂不支持 opus/短链解析）。"""
    match = _BV_RE.search(target or "")
    return normalize_bvid(match.group(0)) if match else None


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bili-intro-generator",
        description="B站工具箱：简介图生成 + 视频下载",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_intro = sub.add_parser(
        "intro", help="生成B站简介图（支持 BV号 / opus图文链接 / b23.tv短链）"
    )
    p_intro.add_argument("target", help="BV号或链接")
    p_intro.add_argument("--keep-html", "-k", action="store_true",
                         help="保留临时 HTML 文件")
    p_intro.add_argument("--browser", "-b", default=None,
                         help="指定渲染浏览器 (chromium / edge / chrome / firefox / webkit)")
    p_intro.add_argument("--video", "-v", action="store_true",
                         help="生成简介图后同时下载视频（仅支持 BV号）")

    p_dl = sub.add_parser(
        "download", help="下载B站视频（下载前进行时长/分P难度检测）"
    )
    p_dl.add_argument("bv_id", help="BV号（含或不含 BV 前缀均可）")

    return parser


def _force_utf8_output() -> None:
    """尽力把标准输出/错误切到 UTF-8，避免 Windows 控制台中文乱码。

    使用 reconfigure 原地修改流，不替换 sys.stdout/sys.stderr 对象，
    因此不会干扰外部调用方或测试对标准输出的捕获。
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def main() -> None:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    _force_utf8_output()
    args = _build_parser().parse_args()

    if args.command == "intro":
        # 惰性导入：download 分支无需安装 playwright
        from .intro_generator import run as run_intro
        asyncio.run(run_intro(args.target, keep_html=args.keep_html,
                              browser_choice=args.browser))
        if args.video:
            bv_id = _extract_bv(args.target)
            if bv_id is None:
                print("提示：-v 目前仅支持 BV 号视频；当前目标不是 BV 号，已跳过视频下载。")
                print("      如需下载，请解析出 BV 号后单独运行: python main.py download <BV号>")
                return
            from .wrapper import run as run_download
            ok = asyncio.run(run_download(bv_id))
            sys.exit(0 if ok else 1)
    elif args.command == "download":
        from .wrapper import run as run_download
        ok = asyncio.run(run_download(args.bv_id))
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
