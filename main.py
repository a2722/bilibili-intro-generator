# -*- coding: utf-8 -*-
"""项目唯一入口。

用法:
    python main.py BV1GJ411x7h7                 # 只生成简介图（默认）
    python main.py BV1GJ411x7h7 -v              # 简介图 + 视频下载
    python main.py intro BV1GJ411x7h7           # 只生成简介图
    python main.py download BV1GJ411x7h7        # 只下载视频
    python main.py intro BV1GJ411x7h7 --keep-html --browser edge
"""

import sys
from pathlib import Path

# 将 src/ 加入模块搜索路径（无需 pip install 即可直接运行）
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from bilibili_tool.cli import main

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] not in ("intro", "download", "-h", "--help"):
        sys.argv.insert(1, "intro")
    main()
