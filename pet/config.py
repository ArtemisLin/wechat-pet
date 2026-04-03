"""017Pet — 配置文件（从 .env 加载，不硬编码任何密钥）"""

import os
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

# === 加载 .env ===
BASE_DIR = Path(__file__).parent
_env_file = BASE_DIR / ".env"

if _env_file.exists():
    with open(_env_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())

# === AI 模型 ===
AI_API_KEY = os.environ.get("AI_API_KEY", "")
AI_BASE_URL = os.environ.get("AI_BASE_URL", "")
AI_MODEL = os.environ.get("AI_MODEL", "")

# === 时区 ===
TIMEZONE = os.environ.get("TIMEZONE", "Asia/Shanghai")
TZ = ZoneInfo(TIMEZONE)


def now():
    """获取当前时间（配置时区），返回 datetime"""
    return datetime.now(TZ)


def today():
    """获取今天日期（配置时区），返回 date"""
    return now().date()


def today_str():
    """获取今天日期字符串 YYYY-MM-DD"""
    return today().strftime("%Y-%m-%d")


def now_str():
    """获取当前时间字符串 YYYY-MM-DDTHH:MM:SS"""
    return now().strftime("%Y-%m-%dT%H:%M:%S")


def parse_date(s):
    """解析日期字符串，返回 date 对象"""
    if not s:
        return None
    return datetime.strptime(s, "%Y-%m-%d").date()


# === 宠物参数 ===
HUNGER_DECAY_RATE = int(os.environ.get("HUNGER_DECAY_RATE", "5"))
HUNGER_DECAY_INTERVAL_MIN = int(os.environ.get("HUNGER_DECAY_INTERVAL_MIN", "30"))
HUNGER_ALERT_THRESHOLD = int(os.environ.get("HUNGER_ALERT_THRESHOLD", "20"))
# === 多属性参数 ===
STAT_CONFIG = {
    "hunger":      {"decay_rate": 5, "restore_amount": (20, 40), "alert_threshold": 20, "tick_mod": 2},  # 30min
    "cleanliness": {"decay_rate": 3, "restore_amount": (25, 45), "alert_threshold": 20, "tick_mod": 4},  # 60min
    "mood":        {"decay_rate": 4, "restore_amount": (30, 50), "alert_threshold": 20, "tick_mod": 3},  # 45min
    "stamina":     {"regen_rate": 3, "restore_amount": 100, "alert_threshold": 15, "tick_mod": 2}, # 30min (睡觉直接回满)
}
PLAY_STAMINA_COST = 15
HEALTH_DECAY_RATE = 5
HEALTH_RESTORE_AMOUNT = (30, 50)
DECAY_INTERVAL_MIN = 15  # scheduler 间隔（各属性 GCD）
SLEEP_DURATION_MIN = 30  # 睡眠持续时间（分钟）
EXPLORE_DURATION_MIN = 30  # 探险持续时间（分钟）

# === 经验值 ===
XP_REWARDS = {"feed": 5, "bathe": 3, "play": 8, "sleep": 2, "heal": 2, "explore": 10}
GROWTH_STAGES = [
    (0,    "baby",  "宝宝"),
    (100,  "child", "幼年"),
    (500,  "teen",  "少年"),
    (2000, "adult", "成年"),
]

# === 探险纪念品 ===
SOUVENIRS = {
    "海边":     ["贝壳", "珊瑚碎片", "海星", "漂流瓶"],
    "森林":     ["松果", "羽毛", "四叶草", "蘑菇"],
    "山顶":     ["奇石", "雪绒花", "老鹰羽毛", "山泉水"],
    "小镇集市": ["小帽子", "风铃", "糖葫芦", "手绘明信片"],
    "花园":     ["花种子", "蝴蝶标本", "花冠", "蜂蜜罐"],
    "湖边":     ["彩色鹅卵石", "荷叶", "小鱼干", "蜻蜓翅膀"],
    "雪山":     ["冰晶", "雪花标本", "暖手石", "白色围巾"],
    "沙漠绿洲": ["仙人掌花", "沙漏", "绿宝石", "驼铃"],
    "古老图书馆": ["旧书签", "魔法卷轴", "水晶球", "羊皮纸地图"],
    "神秘洞穴": ["发光水晶", "化石", "洞穴蘑菇", "宝石碎片"],
}

# === 碎碎念（主动触达） ===
CHITCHAT_SCHEDULE = {
    # 时段: (最早分钟, 最晚分钟, 消息类型)
    # 分钟数 = 小时 * 60 + 分钟，表示一天中的时刻
    "morning":   (7 * 60, 9 * 60,    "早安问候"),
    "noon":      (12 * 60, 13 * 60,  "午饭提醒"),
    "afternoon": (14 * 60, 17 * 60,  "随机碎碎念"),
    "evening":   (19 * 60, 21 * 60,  "晚间关心"),
    "night":     (22 * 60, 23 * 60,  "晚安"),
}
CHITCHAT_COOLDOWN_MIN = 60  # 用户互动后的冷却期（分钟）

# === 文件路径 ===
PET_DATA_FILE = str(BASE_DIR / "pet_data.json")
ILINK_STATE_FILE = str(BASE_DIR / "ilink_state.json")
