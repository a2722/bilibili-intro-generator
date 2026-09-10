# -*- coding: utf-8 -*-
"""视频下载调度模块：下载前难度检测 → 进程内调用下载器。

原 bv_wrapper.py。重构后不再通过 subprocess 拉起
bv_detector.py / organized_downloader.py，改为直接导入调用，
输出行为（stdout 消息）保持与旧版一致以兼容外部调用方。
"""

import sys
import os
from pathlib import Path

from .paths import PROJECT_ROOT

# 可选：导入外部 web_logger（服务器端伴生模块，不随项目分发）。若不存在则优雅降级。
try:
    sys.path.append(str(PROJECT_ROOT / "web"))
    from web_logger import web_logger
except Exception as e:
    print(f"web_logger 导入失败，使用降级日志: {e}")

    class _NoopLogger:
        def log_download(self, *args, **kwargs):
            pass

        def update_current_files(self, *args, **kwargs):
            pass

    web_logger = _NoopLogger()

from .detector import VideoDetector
from .downloader import download_video_with_audio


async def check_download_limit(bv_id: str) -> tuple:
    """下载前难度检测（进程内调用检测器，无需解析子进程 JSON）"""
    try:
        detector = VideoDetector()
        result = await detector.detect_video_difficulty(bv_id)
        if result.is_too_difficult:
            return False, result.reason
        return True, "视频通过检测"
    except Exception as e:
        print(f"下载限制检查出错: {e}")
        return False, f"检查过程出错: {str(e)[:30]}"


async def run(bv_id: str) -> bool:
    """完整下载流程：难度检测 → 下载合并 → 记录日志。返回是否成功。"""
    try:
        print(f"开始处理BV号: {bv_id}")

        # ============ 下载前检测 ============
        print("正在检查视频下载限制...")
        allow_download, reason = await check_download_limit(bv_id)

        if not allow_download:
            print(f"视频下载被拒绝: {reason}")

            # 记录到web_logger
            web_logger.log_download(
                "bilibili",
                bv_id,
                "",
                "",
                f"rejected: {reason}"
            )

            # 输出错误信息供外部调用方读取
            print(f"ERROR: 下载被拒绝 - {reason}")
            return False

        print("视频通过下载限制检查，开始下载...")

        # ============ 进程内直接调用下载器 ============
        success = await download_video_with_audio(bv_id)

        # 记录结果
        if success:
            # 查找生成的文件（统一在 output/yyyymm/video/ 下查找）
            output_dir = PROJECT_ROOT / "output"
            found_files = []
            if output_dir.exists():
                for root, dirs, files in os.walk(output_dir):
                    # 只匹配 video 分类子目录，排除 temp/ 中的过程文件
                    rel_parts = Path(root).relative_to(output_dir).parts
                    if "video" not in rel_parts:
                        continue
                    for file in files:
                        if bv_id in file and file.endswith('.mp4'):
                            file_path = os.path.join(root, file)
                            found_files.append(file_path)

            if found_files:
                # 取最近修改的一个文件（假设是新下载的）
                latest_file = max(found_files, key=os.path.getmtime)
                web_logger.log_download("bilibili", bv_id, os.path.basename(latest_file), latest_file, "success")
                print(f"下载成功: {latest_file}")
            else:
                web_logger.log_download("bilibili", bv_id, "", "", "failed: file not found")
                print("下载完成但未找到文件")

            web_logger.update_current_files()
            print("下载成功并记录日志")
            return bool(found_files)
        else:
            web_logger.log_download("bilibili", bv_id, "", "", "failed: download error")
            print("下载失败")
            return False

    except Exception as e:
        web_logger.log_download("bilibili", bv_id, "", "", f"error: {str(e)}")
        print(f"下载出错: {e}")
        return False
