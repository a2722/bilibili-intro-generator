# 更新日志

本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)。更新日志格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)。

## [0.2.0] - 2026-09-10

### 新增
- 命令行默认执行简介图：`python main.py <BV号>` 无需再写 `intro` 子命令
- 新增 `-v/--video` 参数：`python main.py <BV号> -v` 在生成简介图后同时下载视频
- 补充下载功能对 `ffmpeg` 的依赖说明（读取项目根目录 `ffmpeg.exe` 或系统 PATH 中的 `ffmpeg`）

### 保留
- 原有 `python main.py intro <BV号>`（仅简介图）与 `python main.py download <BV号>`（仅视频）用法不变

## [0.1.0] - 2026-09-09

### 新增
- 简介图生成（主功能）：输入 BV号 / opus 图文链接 / b23.tv 短链，自动抓取封面、标题、UP主与粉丝数、点赞 / 投币 / 收藏 / 分享、热门弹幕、热门评论并渲染为 PNG
- 弹幕 AI 分类着色（玩梗 / 共鸣 / 吐槽 / 硬核），未配置 LLM 时自动降级为关键词规则
- 无头浏览器截图渲染，自动探测系统浏览器（Edge → Chrome → Firefox），无需额外下载内核
- 视频下载（附带功能）：下载前时长 / 分P 难度检测，DASH 流下载 + ffmpeg 音轨合并
- 统一配置 `config.yml`（LLM / 弹幕过滤 / 下载难度阈值）
- 按月归档的输出目录结构（`output/yyyyMM/{intro,video,temp}`）与自动清理策略
- 首次发布，项目名 `bilibili-intro-generator`（原 `bilibili-tool`）
