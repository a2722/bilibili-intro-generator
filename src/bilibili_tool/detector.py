# python3
# -*- coding: utf-8 -*-
# @File    : bv_detector.py
# @Software: PyCharm
"""
视频难度检测器
在拉起下载前检测BV号视频的难度
避免在低带宽服务器上下载过大的视频
"""

import asyncio
import sys
import os
import time
import json
from datetime import datetime
from typing import Dict, Optional
from dataclasses import dataclass
from .paths import PROJECT_ROOT, normalize_bvid
from .settings import CONFIG

# 需要安装的库：bilibili-api-python
try:
    from bilibili_api import video
    from bilibili_api.exceptions import ResponseCodeException
except ImportError:
    print("请安装依赖库: pip install bilibili-api-python")
    sys.exit(1)

# 缓存文件锚定到项目根目录（gitignored）
CACHE_FILE = PROJECT_ROOT / "video_cache.json"

@dataclass
class VideoDifficulty:
    """视频难度评估结果"""
    bv_id: str
    title: str
    duration_seconds: int  # 总时长（秒）
    part_count: int       # 分P数量
    difficulty_score: float  # 难度分数（0-10）
    is_too_difficult: bool  # 是否太难（应该驳回）
    reason: str           # 驳回原因（如果被驳回）
    cache_hit: bool = False  # 是否命中缓存
    
    def to_dict(self) -> dict:
        return {
            "bv_id": self.bv_id,
            "title": self.title,
            "duration_seconds": self.duration_seconds,
            "part_count": self.part_count,
            "difficulty_score": self.difficulty_score,
            "is_too_difficult": self.is_too_difficult,
            "reason": self.reason,
            "cache_hit": self.cache_hit,
            "timestamp": datetime.now().isoformat()
        }

class VideoDetector:
    """视频难度检测器"""
    
    def __init__(self, config: Optional[dict] = None):
        self.config = config or CONFIG["detector"]
        self.cache = self._load_cache()
        self.last_request_time = 0
        self.min_request_interval = self.config.get("min_request_interval", 1.0)  # 请求间隔（秒）
        # 配置项语义为“最大尝试次数”，至少为 1；避免设为 0/负数时循环不执行导致 info 未赋值
        try:
            self.max_retries = max(1, int(self.config.get("max_retries", 1)))
        except (TypeError, ValueError):
            print(f"max_retries 配置无效，回退为 1: {self.config.get('max_retries')!r}")
            self.max_retries = 1
        
    def _load_cache(self) -> dict:
        """加载缓存"""
        if CACHE_FILE.exists():
            try:
                with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"加载缓存失败: {e}")
        return {}
    
    def _save_cache(self):
        """保存缓存"""
        try:
            # 清理过期缓存
            current_time = time.time()
            expired_keys = []
            for key, data in self.cache.items():
                cache_time = datetime.fromisoformat(data.get("timestamp", "1970-01-01")).timestamp()
                if current_time - cache_time > self.config["cache_ttl"]:
                    expired_keys.append(key)
            
            for key in expired_keys:
                del self.cache[key]
            
            # 原子写入：先写临时文件并落盘，再重命名覆盖，
            # 避免中途失败/断电时留下半截 JSON 导致缓存损坏
            tmp_file = CACHE_FILE.with_name(CACHE_FILE.name + ".tmp")
            with open(tmp_file, 'w', encoding='utf-8') as f:
                json.dump(self.cache, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_file, CACHE_FILE)

            if expired_keys:
                print(f"清理了 {len(expired_keys)} 个过期缓存")
                
        except Exception as e:
            print(f"保存缓存失败: {e}")
    
    async def _rate_limit(self):
        """请求速率限制"""
        current_time = time.time()
        elapsed = current_time - self.last_request_time
        if elapsed < self.min_request_interval:
            await asyncio.sleep(self.min_request_interval - elapsed)
        self.last_request_time = time.time()
    
    async def get_video_info(self, bv_id: str) -> Optional[Dict]:
        """获取视频信息"""
        # 检查缓存
        cache_key = normalize_bvid(bv_id)
        if cache_key in self.cache:
            cache_data = self.cache[cache_key]
            cache_time = datetime.fromisoformat(cache_data.get("timestamp", "1970-01-01")).timestamp()
            if time.time() - cache_time < self.config["cache_ttl"]:
                print(f"命中缓存: {cache_key}")
                cache_data["video_info"]["cache_hit"] = True
                return cache_data.get("video_info")
        
        # 应用速率限制
        await self._rate_limit()
        
        # 处理BV号格式（统一为规范的大写 BV 前缀）
        bv_full = normalize_bvid(bv_id)
        
        try:
            print(f"正在获取视频信息: {bv_full}")
            
            # 创建视频对象
            v = video.Video(bvid=bv_full)
            
            # 获取视频信息（带重试）
            for retry in range(self.max_retries):
                try:
                    info = await asyncio.wait_for(
                        v.get_info(), 
                        timeout=self.config["timeout"]
                    )
                    break
                except asyncio.TimeoutError:
                    if retry == self.max_retries - 1:
                        raise
                    print(f"请求超时，第 {retry + 1} 次重试...")
                    await asyncio.sleep(1)
            
            # 获取分P信息
            pages = info.get('pages', [])
            part_count = len(pages)
            
            # 计算总时长
            total_duration = 0
            for page in pages:
                total_duration += page.get('duration', 0)
            
            # 如果没有分P信息，使用主视频信息
            if part_count == 0:
                total_duration = info.get('duration', 0)
                part_count = 1
            
            video_info = {
                "title": info.get('title', '未知标题'),
                "total_duration": total_duration,
                "part_count": part_count,
                "pages": pages,
                "bvid": bv_full,
                "aid": info.get('aid'),
                "timestamp": datetime.now().isoformat(),
                "cache_hit": False
            }
            
            # 更新缓存
            self.cache[cache_key] = {
                "video_info": video_info,
                "timestamp": datetime.now().isoformat()
            }
            self._save_cache()
            
            return video_info
            
        except ResponseCodeException as e:
            print(f"API错误 ({bv_full}): {e.code} - {e.msg}")
            if e.code == -404:
                raise ValueError(f"视频不存在或已被删除: {bv_full}")
            elif e.code == -403:
                raise ValueError(f"视频访问受限: {bv_full}")
            else:
                raise ValueError(f"获取视频信息失败: {e.msg}")
        except asyncio.TimeoutError:
            raise ValueError(f"获取视频信息超时: {bv_full}")
        except Exception as e:
            raise ValueError(f"获取视频信息时出错: {str(e)}")
    
    def calculate_difficulty(self, video_info: Dict) -> VideoDifficulty:
        """计算视频难度"""
        bv_full = video_info.get('bvid', '')
        bv_id = normalize_bvid(bv_full)
        
        total_duration = video_info.get('total_duration', 0)
        part_count = video_info.get('part_count', 1)
        title = video_info.get('title', '未知标题')
        cache_hit = video_info.get('cache_hit', False)
        
        # 检查是否超过硬性限制
        is_too_difficult = False
        reason = ""
        
        # 检查单P时长限制（如果有）
        if self.config.get("max_single_video_duration", 0) > 0:
            # 检查每个分P的时长
            pages = video_info.get('pages', [])
            if pages:
                for i, page in enumerate(pages):
                    page_duration = page.get('duration', 0)
                    if page_duration > self.config["max_single_video_duration"]:
                        is_too_difficult = True
                        reason = f"第{i+1}P时长过长 ({page_duration//60}分{page_duration%60}秒)"
                        break
        
        # 检查总时长限制
        if not is_too_difficult and total_duration > self.config["max_total_duration"]:
            is_too_difficult = True
            hours = total_duration / 3600
            reason = f"视频总时长过长 ({hours:.1f}小时，超过{self.config['max_total_duration']/3600:.1f}小时)"
        
        # 检查分P数限制
        if not is_too_difficult and part_count > self.config["max_part_count"]:
            is_too_difficult = True
            reason = f"分P数过多 ({part_count}P，超过{self.config['max_part_count']}P)"
        
        # 如果已经超过硬性限制，直接返回结果
        if is_too_difficult:
            return VideoDifficulty(
                bv_id=bv_id,
                title=title,
                duration_seconds=total_duration,
                part_count=part_count,
                difficulty_score=10.0,  # 硬性限制给予最高难度
                is_too_difficult=True,
                reason=reason,
                cache_hit=cache_hit
            )
        
        # 如果没有超过硬性限制，计算综合难度分数
        # 标准化难度计算（0-10分）
        # 时长因素（0-10分）
        max_duration = self.config["max_total_duration"]
        duration_score = min(total_duration / max_duration * 10, 10)
        
        # 分P因素（0-10分）
        max_parts = self.config["max_part_count"]
        part_score = min((part_count - 1) / max_parts * 10, 10) if max_parts > 0 else 0
        
        # 加权总分
        weights = self.config["difficulty_weights"]
        total_score = (duration_score * weights["duration_weight"] + 
                      part_score * weights["part_count_weight"])
        
        # 检查是否超过阈值
        if total_score > self.config["difficulty_threshold"]:
            is_too_difficult = True
            reason = f"综合难度过高 (分数: {total_score:.1f}/10)"
        
        return VideoDifficulty(
            bv_id=bv_id,
            title=title,
            duration_seconds=total_duration,
            part_count=part_count,
            difficulty_score=total_score,
            is_too_difficult=is_too_difficult,
            reason=reason,
            cache_hit=cache_hit
        )
    
    async def detect_video_difficulty(self, bv_id: str) -> VideoDifficulty:
        """检测视频难度（主入口）"""
        print(f"开始检测视频难度: {bv_id}")
        
        try:
            # 获取视频信息
            video_info = await self.get_video_info(bv_id)
            
            # 计算难度
            result = self.calculate_difficulty(video_info)
            
            # 输出结果
            hours = result.duration_seconds / 3600
            print(f"检测完成: {result.bv_id}")
            print(f"标题: {result.title}")
            print(f"时长: {result.duration_seconds}秒 ({hours:.2f}小时)")
            print(f"分P数: {result.part_count}")
            print(f"难度分数: {result.difficulty_score:.2f}/10")
            print(f"是否驳回: {'是' if result.is_too_difficult else '否'}")
            if result.is_too_difficult:
                print(f"驳回原因: {result.reason}")
            
            return result
            
        except ValueError as e:
            # 返回一个表示错误的难度结果
            return VideoDifficulty(
                bv_id=bv_id,
                title="获取失败",
                duration_seconds=0,
                part_count=0,
                difficulty_score=10.0,  # 错误情况下给最高难度
                is_too_difficult=True,
                reason=str(e)
            )
        except Exception as e:
            return VideoDifficulty(
                bv_id=bv_id,
                title="检测异常",
                duration_seconds=0,
                part_count=0,
                difficulty_score=10.0,
                is_too_difficult=True,
                reason=f"检测过程出错: {str(e)}"
            )
