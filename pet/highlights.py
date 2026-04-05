"""高光时刻检测与分级。

每次互动后调用 check_highlights() 检测是否触发了高光事件。
返回触发的事件列表及其级别。
"""

from enum import Enum


class HighlightLevel(Enum):
    S = "S"  # 分镜+卡片+分享提示
    A = "A"  # 轻提醒+记录
    B = "B"  # 只记录


# 高光事件定义
HIGHLIGHTS = {
    # S 级
    "first_name_call": {
        "level": HighlightLevel.S,
        "name": "第一次叫你的名字",
        "desc": "{pet_name}第一次叫了你的名字！这个瞬间值得纪念~",
        "check": lambda pet, action, detail: (
            action == "intimacy_threshold" and
            pet.get("intimacy", 0) >= 0.5 and
            "first_name_call" not in pet.get("highlights_triggered", [])
        ),
    },
    "monthly_anniversary": {
        "level": HighlightLevel.S,
        "name": "满月纪念",
        "desc": "你和{pet_name}在一起满 30 天啦！",
        "check": lambda pet, action, detail: (
            action == "daily_check" and
            _days_together(pet) == 30 and
            "monthly_anniversary" not in pet.get("highlights_triggered", [])
        ),
    },
    "adult_ceremony": {
        "level": HighlightLevel.S,
        "name": "成年礼",
        "desc": "{pet_name}长大成年了！从蛋到现在，一路有你~",
        "check": lambda pet, action, detail: (
            action == "level_up" and
            detail.get("new_stage") == "adult" and
            "adult_ceremony" not in pet.get("highlights_triggered", [])
        ),
    },
    "ssr_souvenir": {
        "level": HighlightLevel.S,
        "name": "SSR 纪念品",
        "desc": "{pet_name}带回了超稀有的纪念品！",
        "check": lambda pet, action, detail: (
            action == "explore_end" and
            detail.get("souvenir") and
            detail.get("is_rare", False) and
            "ssr_souvenir" not in pet.get("highlights_triggered", [])
        ),
    },

    # A 级
    "personality_shift": {
        "level": HighlightLevel.A,
        "name": "性格变化",
        "desc": "{pet_name}的性格发生了变化~",
        "check": lambda pet, action, detail: action == "band_crossing",
    },
    "first_explore": {
        "level": HighlightLevel.A,
        "name": "第一次探险",
        "desc": "{pet_name}第一次出门探险！勇敢迈出了第一步~",
        "check": lambda pet, action, detail: (
            action == "explore_start" and
            pet.get("stats", {}).get("total_explores", 0) == 1 and
            "first_explore" not in pet.get("highlights_triggered", [])
        ),
    },
    "first_collection": {
        "level": HighlightLevel.A,
        "name": "第一件收藏",
        "desc": "{pet_name}第一次带回了纪念品！",
        "check": lambda pet, action, detail: (
            action == "explore_end" and
            detail.get("souvenir") and
            len(pet.get("_collection_ref", [])) == 1 and
            "first_collection" not in pet.get("highlights_triggered", [])
        ),
    },

    # B 级（普通成就触发时记录）
    "achievement_unlock": {
        "level": HighlightLevel.B,
        "name": "成就解锁",
        "desc": "解锁了新成就！",
        "check": lambda pet, action, detail: action == "achievement",
    },
}


def _days_together(pet):
    """计算在一起天数。"""
    from datetime import datetime
    from config import now
    created = pet.get("created_at")
    if not created:
        return 0
    try:
        created_dt = datetime.fromisoformat(created)
        return (now().date() - created_dt.date()).days
    except (ValueError, TypeError):
        return 0


def check_highlights(pet, action, detail=None, collection=None):
    """检查当前互动是否触发了高光事件。

    Args:
        pet: pet dict
        action: 互动类型字符串
        detail: 额外信息 dict
        collection: 当前收藏列表（用于判断第一件收藏）

    Returns:
        list of (highlight_id, highlight_def) 触发的高光事件
    """
    detail = detail or {}
    if collection is not None:
        pet["_collection_ref"] = collection

    triggered = []
    for hid, hdef in HIGHLIGHTS.items():
        try:
            if hdef["check"](pet, action, detail):
                triggered.append((hid, hdef))
        except Exception:
            pass

    # 清理临时引用
    pet.pop("_collection_ref", None)
    return triggered


def mark_triggered(pet, highlight_id):
    """标记高光事件为已触发（防止重复触发）。"""
    if "highlights_triggered" not in pet:
        pet["highlights_triggered"] = []
    if highlight_id not in pet["highlights_triggered"]:
        pet["highlights_triggered"].append(highlight_id)


def get_share_prompt(level):
    """根据级别返回分享提示文案。"""
    if level == HighlightLevel.S:
        prompts = [
            "这个瞬间我帮你存成卡片啦~ ✨",
            "这张卡好像很适合发给朋友看看~",
            "这么珍贵的时刻，要不要留个纪念？",
        ]
        import random
        return random.choice(prompts)
    return None
