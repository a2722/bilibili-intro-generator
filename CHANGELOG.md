# 更新日志

本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)。更新日志格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)。

## [0.2.2] - 2026-09-10

### 新增
- 支持从环境变量读取 LLM API Key：新增 `llm.api_key_env` 配置项（默认 `BILI_INTRO_API_KEY`，变量名可自定义），取值优先级为「环境变量 > config.yml 明文」；占位符 / 纯空白仍视为未配置
- README 新增「API Key 的两种填法」章节（明文 / 环境变量，含 Linux、macOS、Windows PowerShell 设置示例）

### 变更
- `.gitignore` 忽略本地 `backup/` 目录，避免完整目录备份被误提交

## [0.2.1] - 2026-09-10

### 修复
- 修正 LLM 弹幕分类提示词中「吐槽/戏谑」与「硬核/科普」的类别描述写反的问题
- 配置模板中 `api_key` 占位符不再被当作有效值；占位符或纯空白一律视为未配置，避免每次运行都误触发 LLM 请求
- 简介图数据抓取失败时改为输出具体错误提示（视频不存在 / 访问受限 / 风控 / 网络错误等），不再抛出原始异常栈；保持不重试
- 视频下载分别校验视频流与音频流的下载结果，任一失败立即中止并清理残留分片文件，避免合并空文件
- 修复 `detector.max_retries: 0` 导致 `info` 变量未赋值而报错的问题（钳制为至少 1）
- 发送给 LLM 的弹幕改用原始文本（渲染仍使用 HTML 转义文本），避免 HTML 实体干扰分类
- 评论接口由两次调用改为单次调用，减少请求量与风控风险
- `-v` 遇到非 BV 号目标时跳过视频下载并给出提示（暂不支持 opus / 短链解析）
- 修复 `requirements.txt` 非 ASCII 注释在 Windows 下被 pip 以 GBK 解码失败的问题
- 修复超长标题在 Windows 触及 260 字符路径上限导致下载失败的问题
- 评论抓取与临时文件清理不再静默吞掉异常
- 粉丝数接口（`x/relation/stat`）失败时输出显式降级提示（降级为 0，不影响出图）

### 变更
- 统一 BV 号前缀大小写处理：新增 `paths.normalize_bvid()`，大小写不敏感，支持补/去前缀及重复前缀
- 移除导入时对 `sys.stdout/stderr` 的全局替换，改为在 CLI 入口用 `reconfigure` 原地设置为 UTF-8
- 短链解析仅对 `b23.tv` / `bili2233.cn` 域名生效，收紧 SSRF 面
- 视频难度检测缓存改为原子写入（临时文件 + `os.replace`）
- 清理无用导入

### 其他
- 修复 `__init__.py` 版本号与 `pyproject.toml` 不一致的问题

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
