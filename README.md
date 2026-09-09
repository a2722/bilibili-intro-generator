<p align="center">
  <img src="assets/intro_preview.png" alt="bilibili-intro-generator 简介图效果预览" width="440">
</p>

# bilibili-intro-generator

**B站简介图生成器** —— 一条命令，把视频 / 图文动态的封面、标题、数据、热门弹幕、热门评论渲染成一张精美的简介卡片图（PNG），直接可发动态、群聊分享。

> 另附带一个按月归档的 B站视频下载小工具，见下方「附带功能」。

## ✨ 主功能：简介图生成

```bash
python main.py intro BV1jY8t6JE9K
```

- 支持 **BV号** / **图文动态（opus）链接** / **b23.tv 短链**
- 自动抓取：封面、标题、UP主与粉丝数、点赞 / 投币 / 收藏 / 分享、热门弹幕、热门评论
- 弹幕 **AI 分类着色**（玩梗 / 共鸣 / 吐槽 / 硬核 四种配色）；未配置 LLM 时自动降级为关键词规则，不影响出图
- 无头浏览器渲染：自动探测系统浏览器（Edge → Chrome → Firefox），**无需额外下载浏览器内核**
- 输出按月归档到 `output/yyyyMM/intro/`，6 个月自动清理

## 📥 附带功能：视频下载

```bash
python main.py download BV1jY8t6JE9K
```

- 下载前进行 **时长 / 分P 难度检测**，超过阈值自动驳回（阈值可配置），避免误下超大视频
- DASH 流下载 + **ffmpeg 自动合并音轨**
- 输出按月归档到 `output/yyyyMM/video/`，过程文件隔离在 `temp/`，3 个月自动清理

## 目录结构

```
bilibili-intro-generator/
├─ main.py                 # 唯一命令行入口
├─ pyproject.toml
├─ requirements.txt
├─ config.example.yml      # 统一配置模板（复制为 config.yml 后填写）
├─ assets/                 # README 效果图
└─ src/
   └─ bilibili_tool/       # 核心实现包
      ├─ cli.py            # 子命令解析
      ├─ intro_generator.py# 简介图 HTML 模板 + 截图渲染
      ├─ data_fetcher.py   # 视频/图文/弹幕/评论数据抓取 + LLM 弹幕分类
      ├─ bili_config.py    # 过滤配置、LLM 配置、SVG 图标
      ├─ settings.py       # 统一配置加载（config.yml）
      ├─ paths.py          # 路径锚点集中管理
      ├─ detector.py       # 视频难度检测（下载前拦截超大视频）
      ├─ downloader.py     # 视频下载与音轨合并
      └─ wrapper.py        # 下载调度（检测 → 下载 → 记录）
```

## 安装

```bash
pip install -r requirements.txt
```

截图渲染会自动探测系统已安装的浏览器（Edge → Chrome → Firefox）。
仅当系统没有任何可用浏览器时才需要：`playwright install chromium`。

## 使用

```bash
# 生成简介图（主功能；支持 BV号 / opus 图文链接 / b23.tv 短链）
python main.py intro BV1GJ411x7h7
python main.py intro BV1GJ411x7h7 --browser edge
python main.py intro https://www.bilibili.com/opus/1056353752004427792 --keep-html

# 下载视频（附带功能；含难度检测）
python main.py download BV1GJ411x7h7
```

安装为命令行工具后也可直接使用 `bili-intro-generator` 命令（`pip install -e .`）。

## 配置

所有配置集中在 `config.yml`（首次运行自动生成，或从 `config.example.yml` 复制；已被 gitignore，不会泄露密钥）。各分区支持只写需要覆盖的项，其余自动使用默认值。

| 分区 | 用途 |
|---|---|
| `llm` | 弹幕 AI 分类的 API Key / 模型（不填则跳过 AI 分类，不影响出图） |
| `danmaku_filter` | 弹幕过滤规则（精确匹配 / 包含子串） |
| `detector` | 下载难度阈值（最大时长 / 分P数 / 难度分数） |

## 输出

所有产物统一归档到 `output/yyyyMM/`（按月分文件夹）：

```
output/202609/
├─ intro/   # 简介图（6 个月自动清理）
├─ video/   # 下载的视频（3 个月自动清理）
└─ temp/    # 过程临时文件（合并/截图用，正常结束后自动删除）
```

## 🙏 致谢

本项目的实现离不开以下开源项目：

| 项目 | 许可证 | 用途 |
|---|---|---|
| [bilibili-api-python](https://github.com/Nemo2011/bilibili-api)（作者 [Nemo2011](https://github.com/Nemo2011)，维护者 MoyuScript） | GPL-3.0-or-later | B站 API 调用的核心依赖：视频 / 图文 / 弹幕 / 评论的数据抓取与**视频下载**均基于该库实现 |
| [Playwright for Python](https://github.com/microsoft/playwright-python) | Apache-2.0 | 无头浏览器渲染截图 |
| [aiohttp](https://github.com/aio-libs/aiohttp) / [aiofiles](https://github.com/Tinche/aiofiles) | Apache-2.0 / MIT | 异步 HTTP 请求与文件写入 |
| [PyYAML](https://github.com/yaml/pyyaml) | MIT | 配置文件解析 |
| [FFmpeg](https://ffmpeg.org) | LGPL/GPL | 音视频合并（`ffmpeg.exe` 未随仓库分发，请自行下载） |

> 特别说明：**视频下载**功能依赖 GPL-3.0 协议的 bilibili-api-python；**简介图生成**为本项目原创实现。

## License

本项目自身代码以 [MIT](LICENSE) 协议发布；所依赖的开源库各自遵循其原始许可证（见上方致谢表）。
