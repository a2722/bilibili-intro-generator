import asyncio
import os
import aiohttp
import aiofiles
import subprocess
import shutil
from datetime import datetime, timedelta
from bilibili_api import video

from .paths import PROJECT_ROOT, FFMPEG_EXE, normalize_bvid

def setup_directories():
    """设置统一输出目录结构并清理旧文件。

    统一输出到 output/yyyymm/，并细分为三个子文件夹：
      - video/  最终视频
      - temp/   下载与合并过程中的临时文件
      - intro/  简介图（由 bili_intro_generator.py 使用，此处一并创建以保持结构统一）
    """
    base_dir = str(PROJECT_ROOT)
    output_dir = os.path.join(base_dir, "output")

    # 确保 output 目录存在
    os.makedirs(output_dir, exist_ok=True)

    # 创建当前月份文件夹
    current_month = datetime.now().strftime("%Y%m")
    current_month_dir = os.path.join(output_dir, current_month)
    os.makedirs(current_month_dir, exist_ok=True)

    # 创建分类子文件夹
    video_dir = os.path.join(current_month_dir, "video")
    temp_dir = os.path.join(current_month_dir, "temp")
    intro_dir = os.path.join(current_month_dir, "intro")
    os.makedirs(video_dir, exist_ok=True)
    os.makedirs(temp_dir, exist_ok=True)
    os.makedirs(intro_dir, exist_ok=True)

    # 清理超过3个月的本分类文件夹（video/temp），保留 intro 等其他分类
    clean_old_folders(output_dir)

    return current_month_dir, video_dir, temp_dir

def clean_old_folders(output_dir):
    """清理超过3个月的旧月份目录下的 video/ 和 temp/ 子目录。

    注意：只清理视频与临时文件所属的分类，不删除整个月份文件夹，
    以免误删简介图（intro/）等其他分类内容。
    """
    try:
        current_date = datetime.now()
        # 计算3个月前的日期
        three_months_ago = current_date - timedelta(days=90)
        three_months_ago_str = three_months_ago.strftime("%Y%m")

        print(f"清理旧文件，将删除 {three_months_ago_str} 及之前的 video/temp 文件夹...")

        deleted_count = 0
        # 遍历 output 目录下的所有项目
        for item in os.listdir(output_dir):
            item_path = os.path.join(output_dir, item)

            # 只处理文件夹且名称是6位数字（年月格式）
            if os.path.isdir(item_path) and item.isdigit() and len(item) == 6:
                try:
                    # 如果文件夹名称（年月）早于3个月前，则清理其 video/temp 子目录
                    if int(item) <= int(three_months_ago_str):
                        for sub in ("video", "temp"):
                            sub_path = os.path.join(item_path, sub)
                            if os.path.isdir(sub_path):
                                shutil.rmtree(sub_path, ignore_errors=True)
                                print(f"删除旧{sub}文件夹: {item}/{sub}")
                                deleted_count += 1
                except ValueError:
                    # 如果转换数字失败，跳过
                    continue

        if deleted_count > 0:
            print(f"已清理 {deleted_count} 个旧文件夹")
        else:
            print("没有需要清理的旧文件夹")

    except Exception as e:
        print(f"清理旧文件夹时出错: {e}")

def _truncate_name(title: str, directory: str, suffix: str,
                   max_title: int = 150, path_limit: int = 259) -> str:
    """按“目录 + 后缀”的剩余空间截断标题，避免 Windows 260 字符路径上限。

    默认给标题留 150 字符（尽量不截断故意取长标题的视频），仅当目录很深、
    剩余空间不足时才进一步缩短，但至少保留 20 字符。
    """
    budget = path_limit - len(directory) - len(os.sep) - len(suffix)
    limit = min(max_title, budget)
    if limit < 20:
        limit = 20
    return title[:limit]


async def download_video_with_audio(bv_id):
    """下载视频并合并音频"""
    try:
        # 设置目录并清理旧文件
        current_month_dir, video_dir, temp_dir = setup_directories()
        
        # 处理BV号（统一为规范的大写 BV 前缀）
        bv_id = normalize_bvid(bv_id)
            
        print(f"正在处理: {bv_id}")
        
        # 创建视频对象
        v = video.Video(bvid=bv_id)
        
        # 获取视频信息
        info = await v.get_info()
        title = info['title']
        print(f"视频标题: {title}")
        
        # 获取cid
        if 'cid' in info:
            cid = info['cid']
        else:
            pages = info.get('pages', [])
            if pages:
                cid = pages[0]['cid']
            else:
                cid = await v.get_cid(page_index=0)
        
        print(f"视频CID: {cid}")
        
        # 获取下载URL
        print("获取下载链接...")
        download_url_data = await v.get_download_url(cid=cid)
        
        # 提取视频和音频URL
        video_url = None
        audio_url = None
        
        if 'dash' in download_url_data:
            # DASH格式：视频和音频分离
            dash_data = download_url_data['dash']
            
            # 获取最高质量的视频流
            if 'video' in dash_data:
                video_streams = dash_data['video']
                video_streams.sort(key=lambda x: x.get('bandwidth', 0), reverse=True)
                video_url = video_streams[0]['baseUrl']
                print(f"视频画质: {video_streams[0].get('id', '未知')}")
            
            # 获取最高质量的音频流
            if 'audio' in dash_data:
                audio_streams = dash_data['audio']
                audio_streams.sort(key=lambda x: x.get('bandwidth', 0), reverse=True)
                audio_url = audio_streams[0]['baseUrl']
                print("找到音频流")
        
        elif 'durl' in download_url_data:
            # 传统格式：视频和音频在一起
            video_url = download_url_data['durl'][0]['url']
            print("使用传统格式（已包含音频）")
        
        if not video_url:
            print("无法获取视频链接")
            return False
        
        # 清理文件名并按完整路径预算截断（上限 150 字符，避免 Windows 260 上限）
        safe_title = "".join(c for c in title if c not in r'<>:"/\|?*')
        safe_title = _truncate_name(safe_title, temp_dir, f"_{bv_id}_video.mp4")
        
        # 临时文件放在当月 temp 子目录（合并后会删除；若失败可清理，不污染根目录）
        temp_video_filename = os.path.join(temp_dir, f"{safe_title}_{bv_id}_video.mp4")
        temp_audio_filename = os.path.join(temp_dir, f"{safe_title}_{bv_id}_audio.mp4")
        
        # 最终输出文件放在当月 video 子目录
        final_filename = os.path.join(video_dir, f"{safe_title}_{bv_id}.mp4")
        
        # 下载视频流（失败则中止，避免后续合并空文件）
        if not await download_file(video_url, temp_video_filename, "视频流"):
            print("❌ 视频流下载失败，已中止（未生成最终文件）")
            return False

        # 如果有单独的音频流，下载音频流
        if audio_url:
            if not await download_file(audio_url, temp_audio_filename, "音频流"):
                print("❌ 音频流下载失败，已中止（视频临时文件保留在 temp 子目录）")
                return False
        
        # 合并视频和音频（如果需要）
        if audio_url:
            print("合并视频和音频...")
            if await merge_video_audio(temp_video_filename, temp_audio_filename, final_filename):
                # 删除临时文件（在 temp 子目录内，删除失败也不影响根目录）
                for tmp_file in (temp_video_filename, temp_audio_filename):
                    if os.path.exists(tmp_file):
                        try:
                            os.remove(tmp_file)
                        except Exception:
                            print(f"临时文件删除失败（已隔离在temp目录，可手动清理）: {tmp_file}")
                print(f"✅ 合并完成: {final_filename}")
                return True
            else:
                print("❌ 合并失败（临时文件保留在 temp 子目录）")
                return False
        else:
            # 如果只有一个文件，直接移动到月份文件夹的 video 子目录
            os.rename(temp_video_filename, final_filename)
            print(f"✅ 下载完成: {final_filename}")
            return True
        
    except Exception as e:
        print(f"❌ 下载出错: {e}")
        import traceback
        traceback.print_exc()
        return False

async def download_file(url, filename, file_type):
    """下载文件，返回是否成功；失败时清理残留的分片文件。"""
    print(f"开始下载{file_type}...")
    success = False
    try:
        async with aiohttp.ClientSession() as session:
            headers = {
                "Referer": "https://www.bilibili.com/",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }

            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    total_size = int(response.headers.get('content-length', 0))
                    downloaded = 0

                    async with aiofiles.open(filename, 'wb') as f:
                        async for chunk in response.content.iter_chunked(8192):
                            await f.write(chunk)
                            downloaded += len(chunk)
                            if total_size > 0:
                                percent = (downloaded / total_size) * 100
                                print(f"\r{file_type}下载进度: {percent:.1f}%", end='', flush=True)

                    print(f"\n{file_type}下载完成")
                    success = True
                    return True
                else:
                    print(f"❌ {file_type}下载失败，HTTP状态码: {response.status}")
                    return False
    except asyncio.TimeoutError:
        print(f"\n❌ {file_type}下载超时（网络中断或链接过期）")
        return False
    except aiohttp.ClientError as e:
        print(f"\n❌ {file_type}下载网络错误: {e}")
        return False
    except Exception as e:
        print(f"\n❌ {file_type}下载出错: {e}")
        return False
    finally:
        if not success and os.path.exists(filename):
            try:
                os.remove(filename)
            except Exception:
                print(f"残留临时文件删除失败（可手动清理）: {filename}")

async def merge_video_audio(video_file, audio_file, output_file):
    """使用ffmpeg合并视频和音频"""
    try:
        # 检查ffmpeg是否可用
        ffmpeg_path = str(FFMPEG_EXE) if FFMPEG_EXE.exists() else "ffmpeg"
        
        cmd = [
            ffmpeg_path, 
            "-i", video_file, 
            "-i", audio_file, 
            "-c", "copy",  # 直接复制流，不重新编码
            "-y",  # 覆盖输出文件
            output_file
        ]
        
        # 使用Popen并忽略输出，避免编码错误
        process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        process.wait()
        
        if process.returncode == 0:
            return True
        else:
            print("ffmpeg合并失败")
            return False
            
    except Exception as e:
        print(f"合并出错: {e}")
        return False
