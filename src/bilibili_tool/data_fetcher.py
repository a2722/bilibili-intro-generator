# -*- coding: utf-8 -*-
"""
B站简介图生成器 — 数据获取与LLM弹幕分类模块
"""

import asyncio
import json
import sys
from typing import Optional, List

try:
    from bilibili_api import video
    from bilibili_api import opus as bili_opus
    from bilibili_api import comment as bili_comment
    from bilibili_api.exceptions import (
        ResponseCodeException,
        NetworkException,
        ArgsException,
    )
    COMMENT_RESOURCE_TYPE_VIDEO = bili_comment.CommentResourceType.VIDEO
except ImportError:
    print("请安装: pip install bilibili-api-python")
    sys.exit(1)

try:
    import aiohttp
except ImportError:
    print("请安装: pip install aiohttp")
    sys.exit(1)

from .bili_config import (
    is_danmaku_filtered,
    LLM_CONFIG,
    DANMAKU_CATEGORY_COLORS,
)
from .paths import normalize_bvid

_BILI_ERROR_HINTS = {
    -404: "内容不存在或已被删除",
    -403: "访问受限（可能需要登录，或存在地区/权限限制）",
    -412: "请求被风控拦截，请稍后重试或配置登录 Cookie",
    -509: "请求过于频繁，已被限流，请稍后再试",
    62002: "内容不可见（可能审核中或被隐藏）",
    62004: "稿件审核中，暂不可访问",
}


def format_fetch_error(error: Exception, target: str) -> str:
    """把抓取过程中的异常翻译成具体、可读的错误提示。"""
    if isinstance(error, ResponseCodeException):
        code = getattr(error, "code", None)
        msg = getattr(error, "msg", str(error))
        hint = _BILI_ERROR_HINTS.get(code)
        if hint:
            return f"目标 {target} 获取失败：{hint}（错误码 {code}）"
        return f"目标 {target} 获取失败：接口返回错误码 {code} - {msg}"
    if isinstance(error, NetworkException):
        return f"获取目标 {target} 时网络错误：状态码 {getattr(error, 'status', '?')} - {getattr(error, 'msg', str(error))}"
    if isinstance(error, ArgsException):
        return f"参数错误：{getattr(error, 'msg', str(error))}（目标 {target}）"
    if isinstance(error, asyncio.TimeoutError):
        return f"获取目标 {target} 超时：请求B站接口超时，请检查网络后重试"
    if isinstance(error, aiohttp.ClientError):
        return f"获取目标 {target} 时网络错误：{type(error).__name__} - {error}"
    return f"获取目标 {target} 失败：{type(error).__name__} - {error}"


async def classify_danmaku_llm(danmaku_texts: list, title: str, desc: str) -> dict:
    """调用 DeepSeek API 对弹幕分类，返回 {text: category} 映射"""
    if not LLM_CONFIG.get("api_key"):
        return {}

    prompt = f"""【系统指令】
你是一个B站弹幕分类专家。请根据视频背景信息，将以下弹幕列表分为4类。
分类标准严格遵循：
1. 玩梗/高能（橙色） — 玩网络梗、谐音梗、呼应视频名场面、高能预警。
2. 共鸣/泪目（琥珀色） — 表达感动、心疼、陪伴感、或对UP主/角色的深情告白。
3. 吐槽/戏谑（蓝色） — 略带调侃的锐评、反驳视频观点、或揭露视频中的穿帮细节。
4. 硬核/科普（绿色） — 补充背景知识、解释专业术语、指出视频中的隐藏彩蛋或细节。

【视频上下文】
- 视频标题：{title}
- 视频简介：{desc}

【待分类弹幕】
{json.dumps(danmaku_texts, ensure_ascii=False)}

【输出要求】
仅返回一个合法的JSON数组，数组元素为 {{"text": "弹幕原文", "category": "分类名称"}}。"""

    headers = {
        "Authorization": f"Bearer {LLM_CONFIG['api_key']}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": LLM_CONFIG["model"],
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": 2000,
    }

    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{LLM_CONFIG['base_url'].rstrip('/')}/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=timeout,
        ) as resp:
            result = await resp.json()

    content = result["choices"][0]["message"]["content"]

    try:
        categories = json.loads(content)
    except json.JSONDecodeError:
        import re
        match = re.search(r'\[[\s\S]*\]', content)
        if match:
            categories = json.loads(match.group())
        else:
            print("LLM 返回格式异常，无法解析:", content[:200])
            return {}

    mapping = {}
    for item in categories:
        text = item.get("text", "")
        cat = item.get("category", "")
        if text and cat in DANMAKU_CATEGORY_COLORS:
            mapping[text] = cat

    return mapping


class BiliIntroData:
    """B站视频数据获取"""

    def __init__(self, bv_id: str):
        self.bv_id = normalize_bvid(bv_id)
        self.v = video.Video(bvid=self.bv_id)
        self.info: Optional[dict] = None
        self.danmaku_list: Optional[List] = None
        self.comments: Optional[List] = None
        self.fans_count: int = 0

    async def fetch_all(self):
        """获取所有数据（视频信息、粉丝数、弹幕、评论）"""
        await self._fetch_video_info()
        await self._fetch_fans_count()
        await self._fetch_danmaku(limit=100)
        await self._fetch_comments(limit=50)

    async def _fetch_video_info(self):
        print("获取视频信息...")
        self.info = await self.v.get_info()

    async def _fetch_fans_count(self):
        try:
            mid = self.info["owner"]["mid"]
            url = f"https://api.bilibili.com/x/relation/stat?vmid={mid}"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://www.bilibili.com/",
            }
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=timeout) as resp:
                    data = await resp.json()
                    if data.get("code") == 0:
                        self.fans_count = (data.get("data") or {}).get("follower", 0)
                    else:
                        print(f"获取粉丝数失败（已降级为 0，不影响出图）: code={data.get('code')} {data.get('message', '')}")
                        self.fans_count = 0
        except Exception as e:
            print(f"获取粉丝数失败（已降级为 0，不影响出图）: {e}")
            self.fans_count = 0

    async def _fetch_danmaku(self, limit=100):
        print("获取弹幕...")
        try:
            cid = self.info.get("cid", 0)
            if not cid:
                pages = self.info.get("pages", [])
                if pages:
                    cid = pages[0].get("cid", 0)
            if cid:
                dms = await self.v.get_danmakus(page_index=0)
                dms_list = list(dms)
                filtered = []
                for dm in dms_list:
                    if isinstance(dm, dict):
                        text = dm.get('text', '')
                    else:
                        text = getattr(dm, 'text', str(dm))
                    if not is_danmaku_filtered(text):
                        filtered.append(dm)

                def get_like(dm):
                    if isinstance(dm, dict):
                        return dm.get('like', 0)
                    return getattr(dm, 'like', 0)

                with_likes = [d for d in filtered if get_like(d) > 0]
                without_likes = [d for d in filtered if get_like(d) == 0]
                with_likes.sort(key=get_like, reverse=True)
                final_list = with_likes[:limit]
                if len(final_list) < limit:
                    remaining = limit - len(final_list)
                    final_list += without_likes[:remaining]
                self.danmaku_list = final_list
            else:
                self.danmaku_list = []
        except Exception as e:
            print(f"获取弹幕失败: {e}")
            self.danmaku_list = []

    async def _fetch_comments(self, limit=50):
        print("获取评论...")
        try:
            aid = self.info.get("aid", 0)
            req = await bili_comment.get_comments(
                aid, COMMENT_RESOURCE_TYPE_VIDEO,
                order=bili_comment.OrderType.LIKE,
            )
            top_comments = (req.get("top_replies") or [])[:1]
            replies = req.get("replies", [])
            top_ids = {c.get("rpid") for c in top_comments}
            replies = [r for r in replies if r.get("rpid") not in top_ids]
            self.comments = top_comments + replies[:limit - len(top_comments)]
        except Exception as e:
            print(f"获取评论失败: {e}")
            self.comments = []


class OpusIntroData:
    """B站图文动态（opus）数据获取，字段与 BiliIntroData 对齐以复用渲染逻辑"""

    def __init__(self, opus_id: int):
        self.mode = "opus"
        self.opus_id = int(opus_id)
        self.opus = bili_opus.Opus(opus_id=self.opus_id)
        self.info: Optional[dict] = None
        self.title: str = ""
        self.author: dict = {}
        self.pub_time: str = ""
        self.text_paras: List[str] = []
        self.content_paras: List[dict] = []
        self.images: List[dict] = []
        self.stats: dict = {}
        self.comments: Optional[List] = None
        self.fans_count: int = 0

    async def fetch_all(self):
        """获取所有数据（图文信息、粉丝数、评论）"""
        await self._fetch_opus_info()
        await self._fetch_fans_count()
        await self._fetch_comments(limit=50)

    async def _fetch_opus_info(self):
        print("获取图文动态信息...")
        self.info = await self.opus.get_info()
        item = self.info.get("item", {})
        self.author = {"mid": 0, "name": "未知用户", "face": "", "desc": ""}
        for m in item.get("modules", []):
            mt = m.get("module_type")
            if mt == "MODULE_TYPE_AUTHOR" and m.get("module_author"):
                a = m["module_author"]
                self.author = {
                    "mid": a.get("mid", 0),
                    "name": a.get("name", "未知用户"),
                    "face": a.get("face", ""),
                    "desc": a.get("desc") or "",
                }
                self.pub_time = a.get("pub_time", "")
            elif mt == "MODULE_TYPE_STAT" and m.get("module_stat"):
                s = m["module_stat"]
                self.stats = {
                    "like": (s.get("like") or {}).get("count", 0),
                    "coin": (s.get("coin") or {}).get("count", 0),
                    "favorite": (s.get("favorite") or {}).get("count", 0),
                    "share": (s.get("forward") or {}).get("count", 0),
                    "comment": (s.get("comment") or {}).get("count", 0),
                }
            elif mt == "MODULE_TYPE_TITLE" and m.get("module_title", {}).get("text"):
                self.title = m["module_title"]["text"]
            elif mt == "MODULE_TYPE_TOP" and m.get("module_top"):
                album = (m["module_top"].get("display") or {}).get("album") or {}
                for pic in album.get("pics", []) or []:
                    self._add_image(pic.get("url", ""), pic.get("width", 0), pic.get("height", 0))
            elif mt == "MODULE_TYPE_CONTENT" and m.get("module_content"):
                self._parse_content(m["module_content"])

        if not self.author.get("face"):
            face_url = (self.info.get("item", {}).get("basic", {}) or {}).get("face") or ""
            if face_url:
                self.author["face"] = face_url

    def _add_image(self, url: str, width=0, height=0):
        if not url:
            return
        if url.startswith("//"):
            url = "https:" + url
        if any(url == img.get("url") for img in self.images):
            return
        self.images.append({"url": url, "width": width, "height": height})

    def _parse_content(self, module_content: dict):
        """解析正文段落：文本（para_type=1/4）、列表（5）、图片（2）、代码（7）"""
        for para in module_content.get("paragraphs", []):
            ptype = para.get("para_type")
            if ptype in (1, 4):
                segments = self._parse_nodes(para.get("text", {}).get("nodes", []))
                if segments:
                    self.text_paras.append("".join(
                        s["text"] for s in segments if s["type"] == "text"
                    ).strip())
                    self.content_paras.append({"kind": "text", "segments": segments})
            elif ptype == 5:
                for item in para.get("list", {}).get("items", []):
                    segments = self._parse_nodes(item.get("nodes", []))
                    if segments:
                        self.text_paras.append("".join(
                            s["text"] for s in segments if s["type"] == "text"
                        ).strip())
                        self.content_paras.append({"kind": "text", "segments": segments})
            elif ptype == 7:
                code_text = para.get("code", {}).get("content", "")
                if code_text.strip():
                    self.text_paras.append(code_text.strip())
                    self.content_paras.append({"kind": "code", "text": code_text})
            elif ptype == 2:
                pics = para.get("pic", {}).get("pics", []) or []
                for pic in pics:
                    self._add_image(pic.get("url", ""), pic.get("width", 0), pic.get("height", 0))

    @staticmethod
    def _parse_nodes(nodes: List[dict]) -> List[dict]:
        """把富文本节点转成渲染用分段：text / emoji"""
        segments = []
        for node in nodes or []:
            if node.get("word"):
                words = node["word"].get("words", "")
                if words:
                    if segments and segments[-1]["type"] == "text":
                        segments[-1]["text"] += words
                    else:
                        segments.append({"type": "text", "text": words})
            elif node.get("rich"):
                rich = node["rich"]
                text = rich.get("text", "")
                emoji = rich.get("emoji") or {}
                icon = emoji.get("icon_url") or ""
                if icon.startswith("//"):
                    icon = "https:" + icon
                if icon:
                    segments.append({"type": "emoji", "url": icon})
                elif text:
                    if segments and segments[-1]["type"] == "text":
                        segments[-1]["text"] += text
                    else:
                        segments.append({"type": "text", "text": text})
        return segments

    async def _fetch_fans_count(self):
        try:
            mid = self.author.get("mid")
            if not mid:
                return
            url = f"https://api.bilibili.com/x/relation/stat?vmid={mid}"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://www.bilibili.com/",
            }
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=timeout) as resp:
                    data = await resp.json()
                    if data.get("code") == 0:
                        self.fans_count = (data.get("data") or {}).get("follower", 0)
                    else:
                        print(f"获取粉丝数失败（已降级为 0，不影响出图）: code={data.get('code')} {data.get('message', '')}")
                        self.fans_count = 0
        except Exception as e:
            print(f"获取粉丝数失败（已降级为 0，不影响出图）: {e}")
            self.fans_count = 0

    async def _fetch_comments(self, limit=50):
        print("获取评论...")
        try:
            item = self.info.get("item", {})
            basic = item.get("basic", {})
            rid = int(basic.get("rid_str") or 0)
            ctype = basic.get("comment_type")
            if not rid or not ctype:
                self.comments = []
                return
            if ctype == 12:
                rtype = bili_comment.CommentResourceType.ARTICLE
            elif ctype == 11:
                rtype = bili_comment.CommentResourceType.DYNAMIC_DRAW
            else:
                rtype = bili_comment.CommentResourceType.DYNAMIC

            req = await bili_comment.get_comments(
                rid, rtype, order=bili_comment.OrderType.LIKE,
            )
            top_comments = (req.get("top_replies") or [])[:1]
            replies = req.get("replies", [])
            top_ids = {c.get("rpid") for c in top_comments}
            replies = [r for r in replies if r.get("rpid") not in top_ids]
            self.comments = top_comments + replies[:limit - len(top_comments)]
        except Exception as e:
            print(f"获取评论失败: {e}")
            self.comments = []
