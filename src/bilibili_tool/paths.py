# -*- coding: utf-8 -*-
"""集中管理路径锚点：包目录、项目根目录、运行时输出目录。

所有模块需要定位配置文件 / 输出目录时，一律从这里取，
不再各自用 Path(__file__).parent 拼路径。
"""

from pathlib import Path

# src/bilibili_tool/ 本包所在目录
PACKAGE_DIR = Path(__file__).resolve().parent

# 项目根目录（src/ 的上一级，即 main.py、config.yml、ffmpeg.exe 所在处）
PROJECT_ROOT = PACKAGE_DIR.parent.parent

# 运行时输出根目录（output/yyyyMM/{intro,video,temp}/）
OUTPUT_DIR = PROJECT_ROOT / "output"

# 项目自带的可执行文件
FFMPEG_EXE = PROJECT_ROOT / "ffmpeg.exe"
