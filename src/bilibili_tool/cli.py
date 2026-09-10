# -*- coding: utf-8 -*-
"""命令行入口：intro（简介图）/ download（视频下载）子命令。"""

import argparse
import asyncio
import sys


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
                         help="生成简介图后同时下载视频")

    p_dl = sub.add_parser(
        "download", help="下载B站视频（下载前进行时长/分P难度检测）"
    )
    p_dl.add_argument("bv_id", help="BV号（含或不含 BV 前缀均可）")

    return parser


def main() -> None:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    args = _build_parser().parse_args()

    if args.command == "intro":
        # 惰性导入：download 分支无需安装 playwright
        from .intro_generator import run as run_intro
        asyncio.run(run_intro(args.target, keep_html=args.keep_html,
                              browser_choice=args.browser))
        if args.video:
            from .wrapper import run as run_download
            ok = asyncio.run(run_download(args.target))
            sys.exit(0 if ok else 1)
    elif args.command == "download":
        from .wrapper import run as run_download
        ok = asyncio.run(run_download(args.bv_id))
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
