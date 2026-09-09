# -*- coding: utf-8 -*-
"""
B站视频简介图生成 — 主入口模块
"""

import asyncio
import html
import os
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("请安装: pip install playwright && playwright install chromium")
    sys.exit(1)

from .bili_config import (
    format_number,
    format_time,
    sanitize_filename,
    dm_color_to_hex,
    LLM_CONFIG,
    DANMAKU_CATEGORY_COLORS,
    PLAY_STAT_SVG,
    DANMAKU_STAT_SVG,
    LIKE_SVG,
    COIN_SVG,
    FAV_SVG,
    SHARE_SVG,
    COMMENT_LIKE_SVG,
    COMMENT_TITLE_SVG,
)
from .data_fetcher import BiliIntroData, OpusIntroData, classify_danmaku_llm
from .paths import PROJECT_ROOT

OUTPUT_DIR = PROJECT_ROOT / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def setup_output_directory() -> Path:
    """创建按月分类的输出子目录，并清理 6 个月前的旧文件夹。

    统一输出结构: output/yyyymm/{intro,video,temp}/
      - intro/  简介图（本脚本产出）
      - video/  下载的视频（由 organized_downloader.py 使用，此处一并创建以保持结构统一）
      - temp/   临时 HTML 等过程文件
    """
    current_month = datetime.now().strftime("%Y%m")
    month_dir = OUTPUT_DIR / current_month
    month_dir.mkdir(parents=True, exist_ok=True)

    # 创建分类子文件夹（幂等）
    (month_dir / "intro").mkdir(parents=True, exist_ok=True)
    (month_dir / "video").mkdir(parents=True, exist_ok=True)
    (month_dir / "temp").mkdir(parents=True, exist_ok=True)

    six_months_ago = (datetime.now() - timedelta(days=180)).strftime("%Y%m")
    print(f"清理 6 个月前的旧图片文件夹（<={six_months_ago}）...")
    deleted = 0
    for item in OUTPUT_DIR.iterdir():
        if item.is_dir() and item.name.isdigit() and len(item.name) == 6:
            if item.name <= six_months_ago:
                shutil.rmtree(item, ignore_errors=True)
                print(f"  已删除: {item.name}")
                deleted += 1
    if deleted:
        print(f"共清理 {deleted} 个旧文件夹")
    else:
        print("无需要清理的旧文件夹")

    return month_dir


_CARD_CSS = '''        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            background: #c2c2c2;
            display: flex;
            justify-content: center;
            padding: 25px;
            font-family: -apple-system, "Microsoft YaHei", "PingFang SC", "Helvetica Neue", sans-serif;
            line-height: 1.4;
        }
        .card {
            width: 480px;
            background: rgba(255, 255, 255, 0.92);
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            border-radius: 28px;
            box-shadow: 0 20px 40px -12px rgba(0, 0, 0, 0.25);
            overflow: hidden;
            border: none;
        }
        .card-header {
            padding: 16px 24px 12px 24px;
            display: flex;
            align-items: center;
            border-bottom: 3px solid #f0f2f5;
        }
        .brand {
            font-size: 18px;
            font-weight: 700;
            color: #fb7299;
            letter-spacing: -0.3px;
        }
        .content {
            padding: 16px 14px 14px;
        }
        .cover {
            width: 100%;
            aspect-ratio: 16 / 9;
            border-radius: 14px;
            overflow: hidden;
            background: #e3e5e7;
            margin-bottom: 16px;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
        }
        .cover img {
            width: 100%;
            height: 100%;
            object-fit: cover;
            display: block;
        }
        .cover-stats {
            position: absolute;
            bottom: 12px;
            left: 12px;
            background: rgba(0, 0, 0, 0.55);
            backdrop-filter: blur(8px);
            -webkit-backdrop-filter: blur(8px);
            color: #fff;
            font-size: 11px;
            font-weight: 600;
            padding: 4px 14px;
            border-radius: 20px;
            letter-spacing: 0.3px;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .cover-stat {
            display: flex;
            align-items: center;
            gap: 3px;
        }
        .cover-stat svg {
            width: 14px;
            height: 14px;
            fill: currentColor;
        }
        .up-info {
            display: flex;
            align-items: center;
            margin-bottom: 15px;
            margin-top: 16px;
        }
        .up-avatar {
            width: 44px;
            height: 44px;
            border-radius: 50%;
            overflow: hidden;
            flex-shrink: 0;
            background: #F0EAEE;
            margin-right: 10px;
            border: 3px solid #fff;
            box-shadow: 0 0 0 2px #FB7299;
        }
        .up-avatar img {
            width: 100%;
            height: 100%;
            object-fit: cover;
        }
        .up-name {
            font-size: 16px;
            font-weight: 400;
            color: #18191C;
        }
        .up-fans {
            font-size: 12px;
            color: #9499A0;
            margin-top: 2px;
        }
        .video-title {
            font-size: 22px;
            font-weight: 800;
            color: #1a1816;
            line-height: 1.3;
            margin-bottom: 6px;
            padding-left: 12px;
            border-left: 4px solid #FB7299;
        }
        .pub-time {
            font-size: 11px;
            color: #9499A0;
            margin-bottom: 8px;
            padding-left: 19px;
        }
        .stats {
            display: flex;
            gap: 20px;
            margin-bottom: 10px;
            flex-wrap: nowrap;
            justify-content: center;
        }
        .stat-item {
            flex: 0 0 90px;
            background: #F6F3F5;
            border-radius: 14px;
            text-align: center;
            padding: 3px 4px;
            font-size: 10px;
            font-weight: 500;
            color: #18191C;
            white-space: nowrap;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 5px;
        }
        .stat-item svg {
            width: 16px;
            height: 16px;
            vertical-align: middle;
            fill: currentColor;
        }
        .desc-box {
            background: #F6F3F5;
            border-radius: 16px;
            padding: 12px 16px;
            font-size: 14px;
            color: #4a4540;
            line-height: 1.6;
            margin-bottom: 14px;
            font-weight: 500;
            border: 1px solid #F0EAEE;
            position: relative;
            word-break: break-word;
            max-height: 150px;
            overflow: hidden;
        }
        .desc-box-center {
            text-align: center;
        }
        .desc-box::before {
            content: "\\201C";
            font-size: 28px;
            color: #FB7299;
            font-weight: 700;
            line-height: 1;
            margin-right: 4px;
            opacity: 0.5;
        }
        /* 右双引号（真实元素，默认内联跟随文本，多行时由 JS 加 multi-line 锚定右下）*/
        .desc-quote-r {
            font-size: 28px;
            color: #FB7299;
            font-weight: 700;
            line-height: 1;
            margin-left: 4px;
            opacity: 0.5;
        }
        /* 多行：左右引号都绝对定位到第一行两端、同一高度，正文整体左右缩进，文字在引号之间 */
        .desc-box.multi-line {
            padding-left: 46px;     /* 正文起点距左边框，给左引号留出更宽气口 */
            padding-right: 46px;    /* 右引号占位 + 间距（与左对称）*/
        }
        .desc-box.multi-line::before {
            position: absolute;
            left: 14px;             /* 左引号左边缘距左边框 */
            top: 13px;              /* 与右引号同一高度，对齐第一行 */
            margin-right: 0;
        }
        .desc-box.multi-line .desc-quote-r {
            position: absolute;
            right: 14px;            /* 与左引号 left 对称 */
            top: 13px;              /* 与左引号同一高度，对齐第一行 */
            margin-left: 0;
            line-height: 1;
        }
        .danmaku-section {
            margin-bottom: 14px;
        }
        .danmaku-section .label {
            font-size: 12px;
            font-weight: 600;
            color: #9499A0;
            padding: 0 0 8px 0;
            display: flex;
            align-items: center;
            gap: 4px;
        }
        .danmaku-section .label svg {
            width: 18px;
            height: 18px;
            fill: currentColor;
            vertical-align: middle;
        }
        .danmaku-container {
            display: flex;
            flex-wrap: wrap;
            gap: 5px;
        }
        .danmaku-bubble {
            background: #F0F2F5;
            border-radius: 14px;
            padding: 2px 10px;
            font-size: 12px;
            color: #18191C;
            display: inline-flex;
            align-items: center;
            gap: 3px;
            white-space: nowrap;
        }
        .danmaku-bubble .like {
            color: #FB7299;
            font-size: 10px;
        }
        .comment-section {
        }
        .comment-section .label {
            font-size: 12px;
            font-weight: 600;
            color: #9499A0;
            margin-bottom: 6px;
            display: flex;
            align-items: center;
            gap: 4px;
        }
        .comment-section .label svg {
            width: 18px;
            height: 18px;
            fill: currentColor;
            vertical-align: middle;
            margin-top: 2px;
        }
        .comment-item {
            display: flex;
            padding: 8px 0;
            border-bottom: 1px solid #E3E5E7;
        }
        .comment-item:last-child {
            border-bottom: none;
        }
        .comment-avatar {
            width: 28px;
            height: 28px;
            border-radius: 50%;
            overflow: hidden;
            flex-shrink: 0;
            background: #e3e5e7;
            margin-right: 8px;
            margin-top: 2px;
        }
        .comment-avatar img {
            width: 100%;
            height: 100%;
            object-fit: cover;
        }
        .comment-body {
            flex: 1;
            min-width: 0;
        }
        .comment-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            margin-bottom: 2px;
        }
        .comment-user {
            display: flex;
            align-items: center;
            gap: 4px;
            flex-wrap: wrap;
        }
        .comment-name {
            font-size: 12px;
            font-weight: 500;
            color: rgba(24, 25, 28, 0.9);
        }
        .comment-level {
            display: inline-block;
            background: #C0C0C0;
            color: #fff;
            font-size: 10px;
            font-weight: 600;
            padding: 0 6px;
            border-radius: 10px;
            line-height: 16px;
            height: 16px;
        }
        .comment-up {
            background: #FB7299;
            color: #fff;
            font-size: 10px;
            font-weight: 600;
            padding: 0 6px;
            border-radius: 10px;
            line-height: 16px;
            height: 16px;
        }
        .comment-time {
            font-size: 10px;
            color: rgba(148, 153, 160, 0.9);
        }
        .comment-content-row {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 10px;
        }
        .comment-content {
            font-size: 16px;
            font-weight: 400;
            color: #18191C;
            word-break: break-word;
            line-height: 1.5;
            flex: 1;
        }
        .comment-pictures {
            margin-top: 4px;
            display: flex;
            flex-wrap: wrap;
            gap: 4px;
        }
        .comment-pictures img {
            width: 120px;
            height: 120px;
            object-fit: cover;
            border-radius: 8px;
            display: block;
        }
        .comment-pictures-sm img {
            width: 84px;
            height: 84px;
        }
        .comment-like {
            font-size: 11px;
            color: rgba(148, 153, 160, 0.9);
            white-space: nowrap;
            margin-top: 2px;
            display: flex;
            align-items: center;
            gap: 2px;
        }
        .comment-like svg {
            width: 14px;
            height: 14px;
            fill: currentColor;
        }
        .lv-0 { background: #999; }
        .lv-1 { background: #C0C0C0; }
        .lv-2 { background: #8bd29b; }
        .lv-3 { background: #7bcdef; }
        .lv-4 { background: #febb8b; }
        .lv-5 { background: #ee672a; }
        .lv-6 { background: #f04c49; }
        .opus-content {
            margin-bottom: 14px;
        }
        .opus-paragraph {
            font-size: 15px;
            color: #4a4540;
            line-height: 1.7;
            margin-bottom: 10px;
            word-break: break-word;
            font-weight: 500;
        }
        .opus-paragraph .emoji-img {
            width: 22px;
            height: 22px;
            vertical-align: -5px;
            display: inline-block;
        }
        .opus-img-grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 6px;
        }
        .opus-img-grid img {
            width: 100%;
            aspect-ratio: 1 / 1;
            object-fit: cover;
            border-radius: 8px;
            display: block;
            background: #f0f2f5;
        }
        .opus-img-list img {
            width: 100%;
            height: auto;
            border-radius: 8px;
            display: block;
            background: #f0f2f5;
            margin-bottom: 6px;
        }
        .opus-stats {
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 12px;
            font-weight: 500;
            padding: 10px 2px 0 2px;
        }
        .opus-stats-left {
            display: flex;
            align-items: center;
            gap: 18px;
        }
        .opus-stat-grey {
            color: #9499A0;
        }
        .opus-stat-cmt {
            color: #FB7299;
            font-weight: 600;
        }
        .opus-stats-line {
            height: 1px;
            background: #E3E5E7;
            margin: 8px 0 0 0;
        }
        .opus-stats-line-active {
            height: 3px;
            background: #FB7299;
            border-radius: 3px;
            margin: 6px 0 8px 0;
        }
        .opus-card .content {
            padding: 0 14px 14px;
        }
'''


# ========== HTML 生成器 ==========
async def generate_html(data: BiliIntroData) -> str:
    """根据获取的数据生成 HTML"""
    if getattr(data, "mode", "video") == "opus":
        return await _generate_opus_html(data)

    info = data.info
    owner = info.get("owner", {})
    up_name = html.escape(owner.get("name", "未知UP主"))
    avatar_url = owner.get("face", "")
    fans = data.fans_count

    title = html.escape(info.get("title", "未知标题"))
    pub_ts = info.get("pubdate", 0)
    pub_time = format_time(pub_ts)
    cover_url = info.get("pic", "")
    desc_raw = info.get("desc", "")
    desc = html.escape(desc_raw).replace('\n', '<br>') if desc_raw else ""

    # 简介区域
    if desc_raw and desc_raw.strip():
        # 短文本(<25字且无换行)：单行居中，左右引号紧贴文字
        # 长文本：直接走多行布局（左引号左上 / 右引号右下 / 正文缩进），不依赖运行时检测
        is_short_desc = len(desc_raw) < 25 and '\n' not in desc_raw
        if is_short_desc:
            desc_box_class = "desc-box desc-box-center"
        else:
            desc_box_class = "desc-box multi-line"
        desc_html = f'<div class="{desc_box_class}">{desc}<span class="desc-quote-r">\u201D</span></div>'
    else:
        desc_html = ""

    stat = info.get("stat", {})
    view_count = stat.get("view", 0)
    danmaku_count = stat.get("danmaku", 0)
    stats = [
        ("点赞", stat.get("like", 0), LIKE_SVG),
        ("投币", stat.get("coin", 0), COIN_SVG),
        ("收藏", stat.get("favorite", 0), FAV_SVG),
        ("分享", stat.get("share", 0), SHARE_SVG),
    ]

    # ---- 弹幕 ----
    danmaku_items = _build_danmaku_items(data)

    # ---- 评论 ----
    comments = _build_comments(data, owner.get("mid", 0))

    # ---- LLM 弹幕分类 ----
    danmaku_categories = await _classify_danmaku(danmaku_items, title, desc_raw)

    # ---- 组装 HTML 片段 ----
    danmaku_section_html = _render_danmaku_section(danmaku_items, danmaku_categories)
    comment_section_html = _render_comment_section(comments)

    stats_html_parts = []
    for _, val, icon in stats:
        if isinstance(icon, str) and not icon.startswith('<'):
            icon_html = f'<span style="font-size:16px;">{icon}</span>'
        else:
            icon_html = icon
        stats_html_parts.append(
            f'<div class="stat-item">{icon_html} {format_number(val)}</div>'
        )
    stats_html = "".join(stats_html_parts)

    cover_stats_html = f'''<div class="cover-stats">
        <span class="cover-stat">{PLAY_STAT_SVG} {format_number(view_count)}</span>
        <span class="cover-stat">{DANMAKU_STAT_SVG} {format_number(danmaku_count)}</span>
    </div>'''

    html_str = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>B站视频简介图</title>
    <style>{_CARD_CSS}</style>
</head>
<body>
    <div class="card">
        <div class="card-header">
            <span class="brand">bilibili</span>
        </div>
        <div class="content">
            <div class="cover" style="position: relative;">
                <img src="{cover_url}" alt="封面" onerror="this.style.display='none'">
                {cover_stats_html}
            </div>
            <div class="up-info">
                <div class="up-avatar">
                    <img src="{avatar_url}" alt="头像" onerror="this.style.display='none'">
                </div>
                <div>
                    <div class="up-name">{up_name}</div>
                    <div class="up-fans">粉丝 {format_number(fans)}</div>
                </div>
            </div>
            <div class="video-title">{title}</div>
            <div class="pub-time">{pub_time}</div>
            <div class="stats">
                {stats_html}
            </div>
            {desc_html}
            {danmaku_section_html}
            {comment_section_html}
        </div>
    </div>
</body>
</html>
"""
    return html_str


# ========== 图文动态（opus）HTML 生成器 ==========

def _render_opus_content(data: OpusIntroData) -> str:
    """渲染图文动态正文（文本段落 + 图片九宫格）"""
    if not data.content_paras and not data.images:
        return ""

    parts = []
    text_count = 0
    for p in data.content_paras:
        if text_count >= 6:
            break
        if p["kind"] == "text":
            seg_html = ""
            for s in p["segments"]:
                if s["type"] == "emoji":
                    seg_html += (
                        f'<img class="emoji-img" src="{s["url"]}" alt="" '
                        f'onerror="this.style.display=\'none\'">'
                    )
                else:
                    seg_html += html.escape(s["text"]).replace("\r", "").replace("\n", "<br>")
            if seg_html:
                parts.append(f'<div class="opus-paragraph">{seg_html}</div>')
                text_count += 1
        elif p["kind"] == "code":
            parts.append(
                f'<pre class="opus-paragraph" style="white-space:pre-wrap;font-family:Consolas,monospace;">'
                f'{html.escape(p["text"])}</pre>'
            )
            text_count += 1

    if data.images:
        grid_cells = "".join(
            f'<img src="{img["url"]}" loading="lazy" '
            f'onerror="this.style.display=\'none\'">'
            for img in data.images
        )
        cls = "opus-img-grid" if len(data.images) > 3 else "opus-img-list"
        parts.append(f'<div class="{cls}">{grid_cells}</div>')

    return f'''<div class="opus-content">
            {''.join(parts)}
        </div>'''


async def _generate_opus_html(data: OpusIntroData) -> str:
    """根据图文动态数据生成 HTML"""
    author = data.author
    up_name = html.escape(author.get("name", "未知用户"))
    avatar_url = author.get("face", "")

    title = html.escape(data.title) if data.title else ""
    pub_time = html.escape(data.pub_time)

    # ---- 正文 ----
    content_html = _render_opus_content(data)

    # ---- 评论 ----
    comments = _build_comments(data, author.get("mid", 0))
    comment_section_html = _render_comment_section(comments, show_label=False)

    # ---- 指标条（转发/评论/赞）----
    fwd = format_number(data.stats.get("share", 0))
    cmt = format_number(data.stats.get("comment", 0))
    like = format_number(data.stats.get("like", 0))
    stats_html = f'''<div class="opus-stats">
            <div class="opus-stats-left">
                <span class="opus-stat-grey">转发 {fwd}</span>
                <span class="opus-stat-cmt">评论 {cmt}</span>
            </div>
            <span class="opus-stat-grey">赞 {like}</span>
        </div>
        <div class="opus-stats-line-active"></div>
        <div class="opus-stats-line"></div>'''

    title_html = f'<div class="video-title">{title}</div>' if title else ""

    html_str = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>B站图文简介图</title>
    <style>
        {_CARD_CSS}
    </style>
</head>
<body>
    <div class="card opus-card">
        <div class="card-header">
            <span class="brand">bilibili</span>
        </div>
        <div class="content">
            <div class="up-info">
                <div class="up-avatar">
                    <img src="{avatar_url}" alt="头像" onerror="this.style.display='none'">
                </div>
                <div>
                    <div class="up-name">{up_name}</div>
                    <div class="up-fans">{pub_time}</div>
                </div>
            </div>
            {title_html}
            {content_html}
            {stats_html}
            {comment_section_html}
        </div>
    </div>
    <script>
        (function () {{
            const cmt = document.querySelector('.opus-stat-cmt');
            const line = document.querySelector('.opus-stats-line-active');
            if (cmt && line) {{
                const contentEl = line.parentElement;
                const content = contentEl.getBoundingClientRect();
                const padLeft = parseFloat(getComputedStyle(contentEl).paddingLeft) || 0;
                const c = cmt.getBoundingClientRect();
                line.style.width = c.width + 'px';
                line.style.marginLeft = (c.left - content.left - padLeft) + 'px';
            }}
        }})();
    </script>
</body>
</html>
"""
    return html_str


# ========== 弹幕处理子函数 ==========

def _build_danmaku_items(data: BiliIntroData) -> list:
    """从原始弹幕数据提取精选弹幕列表（去重、排序、长度过滤）"""
    danmaku_items = []
    if not data.danmaku_list:
        return danmaku_items

    def get_text(dm):
        if isinstance(dm, dict):
            return dm.get('text', '')
        return getattr(dm, 'text', str(dm))

    def get_like(dm):
        if isinstance(dm, dict):
            return dm.get('like', 0)
        return getattr(dm, 'like', 0)

    def get_color(dm):
        if isinstance(dm, dict):
            return dm.get('color', None)
        return getattr(dm, 'color', None)

    filtered = [d for d in data.danmaku_list if len(get_text(d)) <= 20]
    with_likes = [d for d in filtered if get_like(d) > 0]
    without_likes = [d for d in filtered if get_like(d) == 0]
    with_likes.sort(key=get_like, reverse=True)
    sorted_dms = with_likes + without_likes

    # 去重
    seen_texts = set()
    unique_dms = []
    for dm in sorted_dms:
        text = get_text(dm)
        if text not in seen_texts:
            seen_texts.add(text)
            unique_dms.append(dm)
            if len(unique_dms) >= 15:
                break

    for dm in unique_dms:
        text = html.escape(get_text(dm))
        like = get_like(dm)
        color = dm_color_to_hex(get_color(dm))
        if color in ("#ffffff", "#FFFFFF", "#000000"):
            color = "#18191C"
        danmaku_items.append({"text": text, "like": like, "color": color})

    return danmaku_items


def _replace_comment_emotes(message_raw: str, emote_map) -> str:
    """把评论消息中的 [表情名] 占位符替换为表情图片"""
    if not emote_map:
        return html.escape(message_raw)

    message = html.escape(message_raw)
    for key, emo in emote_map.items():
        if not isinstance(emo, dict):
            continue
        url = emo.get("url") or ""
        if url.startswith("//"):
            url = "https:" + url
        if not url:
            continue
        img = (
            f'<img src="{url}" alt="{html.escape(key)}" title="{html.escape(key)}" '
            f'style="width:36px;height:36px;vertical-align:-6px;display:inline-block;" '
            f'onerror="this.style.display=\'none\'">'
        )
        message = message.replace(html.escape(key), img)
    return message


def _build_comments(data: BiliIntroData, up_mid: int) -> list:
    """从原始评论数据提取展示用评论列表"""
    comments = []
    if not data.comments:
        return comments

    for c in data.comments[:20]:
        member = c.get("member", {})
        content_obj = c.get("content", {})
        comment_mid = member.get("mid", 0)
        comment_name = html.escape(member.get("uname", "未知用户"))
        comment_avatar = member.get("avatar", "")
        level_info = member.get("level_info", {})
        level = level_info.get("current_level", 0) if isinstance(level_info, dict) else 0
        ctime = c.get("ctime", 0)
        message_raw = content_obj.get("message", "")
        if len(message_raw) > 200:
            message_raw = message_raw[:198] + ".."
        message = _replace_comment_emotes(message_raw, content_obj.get("emote") or {})
        like_count = c.get("like", 0)
        is_up = str(comment_mid) not in ("", "0", "None") and str(comment_mid) == str(up_mid)

        pictures = []
        pic_list = content_obj.get("pictures") or c.get("pictures") or []
        for pic in pic_list:
            img_url = pic.get("img_src") or pic.get("src") or ""
            if img_url:
                if img_url.startswith("//"):
                    img_url = "https:" + img_url
                pictures.append(img_url)

        comments.append({
            "avatar": comment_avatar,
            "name": comment_name,
            "level": level,
            "is_up": is_up,
            "time": format_time(ctime),
            "content": message,
            "like": like_count,
            "pictures": pictures,
        })

    return comments


async def _classify_danmaku(danmaku_items: list, title: str, desc: str) -> dict:
    """尝试用 LLM 对弹幕分类，失败返回空字典"""
    if not LLM_CONFIG.get("api_key") or not danmaku_items:
        return {}
    try:
        danmaku_texts = [dm["text"] for dm in danmaku_items]
        categories = await classify_danmaku_llm(danmaku_texts, title, desc)
        if categories:
            print(f"LLM 弹幕分类成功: {len(categories)} 条")
        return categories
    except Exception as e:
        print(f"LLM 分类失败，使用轮询兜底: {e}")
        return {}


def _render_danmaku_section(danmaku_items: list, danmaku_categories: dict) -> str:
    """渲染弹幕区域 HTML"""
    if not danmaku_items:
        return ""

    danmaku_html_parts = []
    danmaku_theme_colors = [
        ("#fff6f0", "#e8613c"),
        ("#fffbeb", "#f59e0b"),
        ("#eff6ff", "#3b82f6"),
        ("#ecfdf5", "#10b981"),
    ]

    for i, dm in enumerate(danmaku_items):
        cat = danmaku_categories.get(dm["text"])
        if cat and cat in DANMAKU_CATEGORY_COLORS:
            bg, border = DANMAKU_CATEGORY_COLORS[cat]
        else:
            bg, border = danmaku_theme_colors[i % 4]
        like_html = f' <span class="like">+{dm["like"]}</span>' if dm["like"] else ""
        full_text = f'{dm["text"]}{like_html}'
        danmaku_html_parts.append(
            f'<div class="danmaku-bubble" style="color:{dm["color"]}; background:{bg}; border:1px solid {border};">{full_text}</div>'
        )

    danmaku_html = "".join(danmaku_html_parts)
    return f'''<div class="danmaku-section">
            <div class="label">{DANMAKU_STAT_SVG} 部分弹幕</div>
            <div class="danmaku-container">
                {danmaku_html}
            </div>
        </div>'''


def _render_comment_section(comments: list, show_label: bool = True) -> str:
    """渲染评论区域 HTML"""
    if not comments:
        return ""

    comments_html_parts = []
    for c in comments:
        level_class = f"lv-{c['level']}"
        content_html = c["content"]
        if c["pictures"]:
            pics_html = "".join(
                f'<img src="{u}" loading="lazy">' for u in c["pictures"]
            )
            cls = "comment-pictures-sm" if len(c["pictures"]) > 3 else "comment-pictures"
            content_html += f'<div class="{cls}">{pics_html}</div>'

        comments_html_parts.append(f'''
        <div class="comment-item">
            <div class="comment-avatar">
                <img src="{c["avatar"]}" alt="" onerror="this.style.display='none'">
            </div>
            <div class="comment-body">
                <div class="comment-header">
                    <div class="comment-user">
                        <span class="comment-name">{c["name"]}</span>
                        <span class="comment-level {level_class}">Lv{c["level"]}</span>
                        {f'<span class="comment-up">UP</span>' if c["is_up"] else ''}
                    </div>
                    <span class="comment-time">{c["time"]}</span>
                </div>
                <div class="comment-content-row">
                    <div class="comment-content">{content_html}</div>
                    <div class="comment-like">{COMMENT_LIKE_SVG} {format_number(c["like"])}</div>
                </div>
            </div>
        </div>
        ''')

    comments_html = "".join(comments_html_parts)
    label_html = f'<div class="label">{COMMENT_TITLE_SVG} 热门评论</div>' if show_label else ""
    return f'''<div class="comment-section">
            {label_html}
            {comments_html}
        </div>'''


# ========== 浏览器自动探测 ==========

def _probe_browser_executables() -> dict:
    """探测系统中已安装的浏览器可执行文件路径（跨平台）"""
    import platform
    system = platform.system()

    candidates = {
        # channel 名 -> 候选可执行文件路径列表
        "msedge": [],   # Microsoft Edge (Chromium)
        "chrome": [],   # Google Chrome (Chromium)
        "firefox": [],  # Mozilla Firefox
        "webkit": [],   # Apple Safari (仅 macOS)
    }

    if system == "Windows":
        candidates["msedge"] = [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        ]
        candidates["chrome"] = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        ]
        candidates["firefox"] = [
            r"C:\Program Files\Mozilla Firefox\firefox.exe",
            r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe",
        ]
        # Edge 其实也是 Chromium，可额外探测用户级安装
        candidates["msedge"] += [
            os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"),
        ]
    elif system == "Darwin":  # macOS
        candidates["msedge"] = ["/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"]
        candidates["chrome"] = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]
        candidates["firefox"] = ["/Applications/Firefox.app/Contents/MacOS/firefox"]
        candidates["webkit"] = ["/Applications/Safari.app/Contents/MacOS/Safari"]
    elif system == "Linux":
        candidates["chrome"] = ["/usr/bin/google-chrome", "/usr/bin/google-chrome-stable", "/usr/bin/chromium", "/usr/bin/chromium-browser"]
        candidates["msedge"] = ["/usr/bin/microsoft-edge", "/usr/bin/microsoft-edge-stable"]
        candidates["firefox"] = ["/usr/bin/firefox"]

    found = {}
    for channel, paths in candidates.items():
        for p in paths:
            if p and os.path.isfile(p):
                found[channel] = p
                break
    return found


def _resolve_browser(browser_choice: str = None):
    """解析要使用的浏览器，返回 (playwright_browser_name, launch_kwargs)。

    可选参数 browser_choice 用于显式指定浏览器（调试用），取值：
      "chromium" / "edge" / "chrome" / "firefox" / "webkit"（safari）
    若显式指定的浏览器不可用则抛出 RuntimeError。
    未指定时按优先级自动选择：
      Playwright 内置 Chromium → Edge → Chrome → Firefox → Safari（仅 macOS）。
    全部不可用则抛出 RuntimeError，由调用方处理。
    """
    import platform
    _system = platform.system()

    if browser_choice is not None:
        choice = browser_choice.strip().lower()
        if choice == "chromium":
            print("按参数使用 Playwright 内置 Chromium")
            return "chromium", {}
        if choice in ("edge", "msedge"):
            edge = _probe_browser_executables().get("msedge")
            if edge:
                print(f"按参数使用系统浏览器: Microsoft Edge ({edge})")
                return "chromium", {"channel": "msedge"}
            raise RuntimeError("指定的浏览器不可用: Edge 未在系统中检测到。")
        if choice in ("chrome", "google-chrome"):
            chrome = _probe_browser_executables().get("chrome")
            if chrome:
                print(f"按参数使用系统浏览器: Google Chrome ({chrome})")
                return "chromium", {"channel": "chrome"}
            raise RuntimeError("指定的浏览器不可用: Chrome 未在系统中检测到。")
        if choice == "firefox":
            firefox = _probe_browser_executables().get("firefox")
            if firefox:
                print(f"按参数使用系统浏览器: Firefox ({firefox})")
                return "firefox", {"executable_path": firefox}
            raise RuntimeError("指定的浏览器不可用: Firefox 未在系统中检测到。")
        if choice in ("webkit", "safari"):
            if _system != "Darwin":
                raise RuntimeError("指定的浏览器不可用: Safari 仅支持 macOS。")
            webkit = _probe_browser_executables().get("webkit")
            if webkit:
                print(f"按参数使用系统浏览器: Safari ({webkit})")
                return "webkit", {"executable_path": webkit}
            raise RuntimeError("指定的浏览器不可用: Safari 未在系统中检测到。")
        raise RuntimeError(
            f"未知的浏览器参数: {browser_choice}。可选值: chromium / edge / chrome / firefox / webkit"
        )

    # 1. Playwright 内置 Chromium（需执行 playwright install chromium）
    #    通过探测 Playwright 浏览器缓存目录确认是否已安装。
    _chromium_exists = False
    try:
        from playwright._impl._driver import compute_driver_executable
        _playwright_root = os.path.join(os.path.dirname(compute_driver_executable()), "..", "..", ".local-browsers")
    except Exception:
        _playwright_root = os.path.join(
            os.path.expandvars(r"%LOCALAPPDATA%\ms-playwright")
            if _system == "Windows" else os.path.expanduser("~/.cache/ms-playwright"),
        )
    if _playwright_root and os.path.isdir(_playwright_root):
        for entry in os.listdir(_playwright_root):
            if entry.startswith("chromium-"):
                _chromium_exists = True
                break
    if _chromium_exists:
        print("使用 Playwright 内置 Chromium")
        return "chromium", {}

    # 2. 系统浏览器
    found = _probe_browser_executables()

    # Chromium 内核的浏览器（Edge/Chrome）可用 channel 参数直接驱动
    if "msedge" in found:
        print(f"检测到系统浏览器: Microsoft Edge ({found['msedge']})")
        return "chromium", {"channel": "msedge"}
    if "chrome" in found:
        print(f"检测到系统浏览器: Google Chrome ({found['chrome']})")
        return "chromium", {"channel": "chrome"}

    # Firefox 需指定可执行文件路径
    if "firefox" in found:
        print(f"检测到系统浏览器: Firefox ({found['firefox']})")
        return "firefox", {"executable_path": found["firefox"]}

    # Safari 仅 macOS，通过 webkit 指定路径
    if "webkit" in found:
        print(f"检测到系统浏览器: Safari ({found['webkit']})")
        return "webkit", {"executable_path": found["webkit"]}

    # 3. 全都没有 → 报错
    raise RuntimeError(
        "未找到任何可用的浏览器。请执行 `playwright install chromium` 下载内置 Chromium，"
        "或安装 Edge / Chrome / Firefox / Safari 其中之一。"
    )


# ========== Playwright 异步截图 ==========
async def capture_html(html_str: str, output_path: str, width: int = 590, browser_choice: str = None):
    """用 Playwright 渲染 HTML 并截图。

    浏览器优先级（可被 browser_choice 显式覆盖）：
      Playwright 内置 Chromium → Edge → Chrome → Firefox → Safari。
    全部不可用时抛出 RuntimeError。
    """
    browser_name, launch_kwargs = _resolve_browser(browser_choice)
    async with async_playwright() as p:
        browser_launcher = getattr(p, browser_name)
        browser = await browser_launcher.launch(**launch_kwargs)
        page = await browser.new_page(viewport={"width": width, "height": 2000})
        await page.set_content(html_str)
        await page.wait_for_load_state("networkidle")
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(500)
        await page.wait_for_function(
            """() => {
                const imgs = document.querySelectorAll('img');
                for (const img of imgs) {
                    if (img.src && img.src !== '') {
                        if (!img.complete) return false;
                    }
                }
                return true;
            }""",
            timeout=10000
        )
        await page.wait_for_timeout(300)
        body = page.locator("body")
        await body.screenshot(path=output_path)
        await browser.close()


# ========== 主函数 ==========
def _parse_opus_id(raw: str):
    """从 opus 链接 / 动态链接 / 纯数字 id 中提取图文 id；非图文输入返回 None"""
    import re
    text = raw.strip()
    m = re.search(r"(?:opus/|t\.bilibili\.com/)(\d+)", text)
    if m:
        return int(m.group(1))
    if re.fullmatch(r"\d{10,}", text):
        return int(text)
    return None


async def _resolve_short_link(url: str) -> str:
    """解析 b23.tv 短链，返回跳转后的真实 URL"""
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(url, allow_redirects=True) as resp:
                return str(resp.url)
    except Exception as e:
        print(f"aiohttp 短链解析失败: {e}，尝试 urllib 兜底...")
    try:
        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.geturl()
    except Exception as e:
        print(f"短链解析失败: {e}")
        return url


async def run(target: str, keep_html: bool = False, browser_choice=None) -> None:
    if "b23.tv" in target:
        print("解析 b23.tv 短链...")
        target = await _resolve_short_link(target)

    opus_id = _parse_opus_id(target)
    # 若链接最终指向视频页（含 BV 号），提取 BV 号作为目标
    if opus_id is None:
        import re as _re
        _bv_match = _re.search(r'([Bb][Vv][0-9A-Za-z]{10})', target)
        if _bv_match:
            target = _bv_match.group(1)
    if opus_id is None and "://" in target and "bilibili.com" in target:
        print("无法识别链接类型，仅支持: BV号、opus/图文链接、t.bilibili.com 动态链接")
        return

    if opus_id is not None:
        data = OpusIntroData(opus_id)
        item_id = f"opus_{opus_id}"
        default_title = f"opus_{opus_id}"
    else:
        data = BiliIntroData(target)
        item_id = data.bv_id
        default_title = "unknown"

    await data.fetch_all()

    print("生成 HTML 模板...")
    html_str = await generate_html(data)

    # 按月归档输出：output/yyyymm/{temp,intro}/
    month_dir = setup_output_directory()
    temp_dir = month_dir / "temp"
    intro_dir = month_dir / "intro"

    temp_html = temp_dir / f"{item_id}_temp.html"
    with open(temp_html, "w", encoding="utf-8") as f:
        f.write(html_str)

    if opus_id is not None:
        safe_title = sanitize_filename(data.title or data.author.get("name", default_title))[:40]
    else:
        safe_title = sanitize_filename(data.info.get("title", default_title))[:40]
    output_png = intro_dir / f"{item_id}_{safe_title}.png"

    print("使用 Playwright 渲染截图...")
    await capture_html(html_str, str(output_png), width=530, browser_choice=browser_choice)

    if keep_html:
        print(f"临时 HTML 文件已保留: {temp_html}")
    else:
        try:
            temp_html.unlink()
        except Exception:
            pass

    print(f"简介图已保存: {output_png}")
