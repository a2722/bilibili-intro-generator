# -*- coding: utf-8 -*-
"""项目唯一入口。

用法:
    python main.py intro BV1GJ411x7h7 [--keep-html] [--browser edge]
    python main.py download BV1GJ411x7h7
"""

import sys
from pathlib import Path

# 将 src/ 加入模块搜索路径（无需 pip install 即可直接运行）
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from bilibili_tool.cli import main

if __name__ == "__main__":
    main()
