# -*- coding: utf-8 -*-
"""统一配置中心：所有配置合并到项目根的 config.yml（模板见 config.example.yml）。

分区:
  llm            — 弹幕 AI 分类（可选；key 可来自明文或 api_key_env 指定的环境变量）
  danmaku_filter — 弹幕过滤词
  detector       — 下载难度检测阈值

config.yml 不存在时会自动用内置默认值创建一份带注释的模板。
各分区支持只写需要覆盖的项，其余项自动回落到默认值（递归合并）。
"""

import os
from copy import deepcopy

import yaml

from .paths import PROJECT_ROOT

CONFIG_FILE = PROJECT_ROOT / "config.yml"

# 历史模板 / 示例文件中的占位符，视为“未配置”，避免误触发 LLM 请求
_API_KEY_PLACEHOLDERS = {
    "在这里填入你的 DeepSeek API Key",
    "在此填入你的 DeepSeek API Key",
    "your api key",
    "YOUR_API_KEY",
}

DEFAULTS = {
    "llm": {
        "provider": "deepseek",
        "api_key": "",
        "api_key_env": "BILI_INTRO_API_KEY",  # 环境变量名（优先级高于 api_key，可在 config 中改）
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
    },
    "danmaku_filter": {
        "exact_match": ["", "。", "."],
        "contain": [],
    },
    "detector": {
        "max_single_video_duration": 2000,   # 单P最大时长（秒）
        "max_total_duration": 2400,          # 总时长上限（秒）
        "max_part_count": 5,                 # 最大分P数
        "difficulty_weights": {
            "duration_weight": 0.8,
            "part_count_weight": 0.2,
        },
        "difficulty_threshold": 7.0,         # 综合难度阈值（0-10）
        "cache_ttl": 86400,                  # 缓存有效期（秒）
        "min_request_interval": 2.0,         # 最小请求间隔（秒）
        "timeout": 15,                       # API 请求超时（秒）
        "max_retries": 1,                    # 最大尝试次数（至少 1）
    },
}

_TEMPLATE = """# ==================== bilibili-intro-generator 统一配置 ====================
# 使用说明：复制本文件为 config.yml 后填写（config.yml 已被 gitignore，不会泄露密钥）。
# 三个分区均可只写需要覆盖的项，其余自动使用内置默认值。

# ===== LLM 弹幕分类（可选）=====
# 不填 api_key 时跳过 AI 分类，简介图仍正常生成（弹幕使用关键词规则着色）。
llm:
  provider: deepseek
  # 方式一：直接填明文（本文件已被 gitignore，不会提交）
  api_key: ""  # 留空则跳过 AI 弹幕分类（简介图仍正常生成）
  # 方式二：从环境变量读取（优先级高于 api_key），变量名在这里自定义
  api_key_env: "BILI_INTRO_API_KEY"
  base_url: "https://api.deepseek.com"
  model: "deepseek-chat"

# ===== 弹幕过滤 =====
# exact_match: 完全等于这些内容的弹幕不显示
# contain:     包含这些子串的弹幕不显示
danmaku_filter:
  exact_match: ["", "。", "."]
  contain: []

# ===== 下载难度检测 =====
# 下载前评估视频时长/分P数，超过阈值自动驳回，避免下载超大视频。
detector:
  # 单P最大时长（秒）
  max_single_video_duration: 2000
  # 总时长上限（秒）
  max_total_duration: 2400
  # 最大分P数
  max_part_count: 5
  # 难度权重（两项之和应为 1.0）
  difficulty_weights:
    duration_weight: 0.8
    part_count_weight: 0.2
  # 综合难度阈值（0-10），超过则驳回
  difficulty_threshold: 7.0
  # 缓存有效期（秒）
  cache_ttl: 86400
  # 最小请求间隔（秒），防止请求过快被封
  min_request_interval: 2.0
  # API 请求超时（秒）
  timeout: 15
  # 最大尝试次数（至少 1；1 表示只尝试一次、不重试）
  max_retries: 1
"""


def _deep_merge(base: dict, override: dict) -> dict:
    """递归合并：override 中的值覆盖 base，未覆盖的项保留 base 默认值。"""
    merged = dict(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _resolve_llm_api_key(llm: dict) -> None:
    """确定最终的 llm.api_key（就地写回 llm 字典）。

    优先级：环境变量（变量名由 llm.api_key_env 指定） > config.yml 的 llm.api_key。
    占位符 / 纯空白一律视为未配置，避免误触发 LLM 请求。
    """
    key = (llm.get("api_key") or "").strip()
    key = "" if key in _API_KEY_PLACEHOLDERS else key

    env_name = (llm.get("api_key_env") or "").strip()
    if env_name:
        env_value = (os.environ.get(env_name) or "").strip()
        if env_value:
            key = env_value

    llm["api_key"] = key


def load_config() -> dict:
    """加载 config.yml 并与内置默认值合并；文件不存在时自动创建模板。"""
    if not CONFIG_FILE.exists():
        try:
            CONFIG_FILE.write_text(_TEMPLATE, encoding="utf-8")
            print(f"已创建默认配置文件: {CONFIG_FILE}")
        except Exception as e:
            print(f"创建配置文件失败: {e}")
        user_cfg = {}
    else:
        try:
            user_cfg = yaml.safe_load(CONFIG_FILE.read_text(encoding="utf-8")) or {}
        except Exception as e:
            print(f"配置文件加载失败，使用默认配置: {e}")
            user_cfg = {}

    merged = deepcopy(DEFAULTS)
    for section in DEFAULTS:
        if isinstance(user_cfg.get(section), dict):
            merged[section] = _deep_merge(DEFAULTS[section], user_cfg[section])

    llm = merged.get("llm")
    if isinstance(llm, dict):
        _resolve_llm_api_key(llm)

    return merged


CONFIG = load_config()
