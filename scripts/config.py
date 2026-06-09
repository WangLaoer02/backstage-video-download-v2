"""
配置管理模块 - 统一管理所有配置
"""
import os
from pathlib import Path

# ============ 路径配置 ============
SAVE_DIR = Path(os.getenv(
    "BACKSTAGE_SAVE_DIR",
    "/Volumes/美术AI龙虾"
))
ASSETS_DIR = Path(os.getenv(
    "BACKSTAGE_ASSETS_DIR",
    "/Volumes/美术AI龙虾/assets"
))

# ============ API 配置 ============
API_BASE = "http://adopenplatform.rongyao666.com/app/data/api/ApiGetJrttVideoByCategory.php"
IPv6_ROOT = os.getenv("IPv6_ROOT", "http://[2408:8256:4c87:f19c::c42]:9092")

# ============ 飞书配置 ============
# 写表默认禁用；如需临时写表，必须通过环境变量显式指定目标表和凭据。
BITABLE_APP_TOKEN = os.getenv("BACKSTAGE_BITABLE_APP_TOKEN") or os.getenv("BITABLE_APP_TOKEN", "")
BITABLE_TABLE_ID = os.getenv("BACKSTAGE_BITABLE_TABLE_ID") or os.getenv("BITABLE_TABLE_ID", "")
FEISHU_ACCESS_TOKEN = os.getenv("BACKSTAGE_FEISHU_ACCESS_TOKEN") or os.getenv("FEISHU_ACCESS_TOKEN", "")
FEISHU_APP_ID = os.getenv("BACKSTAGE_FEISHU_APP_ID") or os.getenv("FEISHU_APP_ID", "")
FEISHU_APP_SECRET = os.getenv("BACKSTAGE_FEISHU_APP_SECRET") or os.getenv("FEISHU_APP_SECRET", "")

# ============ Vision API 配置 ============
VISION_API_KEY = os.getenv("VISION_API_KEY", "")
VISION_API_URL = os.getenv(
    "VISION_API_URL",
    "https://api.jiekou.ai/openai/v1/chat/completions"
)

# ============ 日志配置 ============
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_DIR = Path(os.getenv("LOG_DIR", SAVE_DIR / ".logs"))

# ============ 序号分配文件 ============
SEQ_FILE = SAVE_DIR / "sequences.json"

# 创建必要的目录
for d in [SAVE_DIR, ASSETS_DIR, LOG_DIR]:
    d.mkdir(parents=True, exist_ok=True)
