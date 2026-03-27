"""
017Pet — 宠物引擎 + 消息路由
"""

import json
import os
import threading
import random

from config import (
    PET_DATA_FILE, now_str, today_str,
    HUNGER_DECAY_RATE, HUNGER_ALERT_THRESHOLD, FEED_AMOUNT,
)

SCHEMA_VERSION = 1


# ============================================================
# 数据层
# ============================================================
class PetStore:
    """宠物数据存储，线程安全"""

    def __init__(self, data_file=None):
        self.data_file = data_file or PET_DATA_FILE
        self._lock = threading.Lock()
        self.pet = None       # dict or None
        self.owner = {}       # {"user_id": ..., "name": ...}
        self.history = []     # 事件日志
        self._load()

    def _load(self):
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.pet = data.get("pet")
                self.owner = data.get("owner", {})
                self.history = data.get("history", [])
            except (json.JSONDecodeError, KeyError):
                print("  ⚠️ pet_data.json 损坏，使用空数据")

    def _save(self):
        with self._lock:
            data = {
                "schema_version": SCHEMA_VERSION,
                "pet": self.pet,
                "owner": self.owner,
                "history": self.history,
            }
            tmp_file = self.data_file + ".tmp"
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_file, self.data_file)

    # --- 宠物操作 ---

    def create_egg(self, user_id, user_name):
        """创建蛋，返回 True/False（已存在则 False）"""
        if self.pet is not None:
            return False
        self.pet = {
            "name": None,
            "stage": "egg",
            "hunger": 100,
            "hatched_at": None,
            "last_fed_at": None,
            "last_decay_at": None,
            "created_at": now_str(),
        }
        self.owner = {"user_id": user_id, "name": user_name}
        self._add_history("create_egg", {"by": user_name})
        self._save()
        return True

    def hatch(self, name):
        """孵化：蛋→宝宝，返回 True/False"""
        if not self.pet or self.pet["stage"] != "egg":
            return False
        self.pet["name"] = name
        self.pet["stage"] = "baby"
        self.pet["hatched_at"] = now_str()
        self.pet["last_decay_at"] = now_str()
        self._add_history("hatch", {"name": name})
        self._save()
        return True

    def feed(self):
        """喂食，返回 (old_hunger, new_hunger) 或 None（无宠物/未孵化）"""
        if not self.pet or self.pet["stage"] == "egg":
            return None
        old = self.pet["hunger"]
        self.pet["hunger"] = min(100, old + FEED_AMOUNT)
        self.pet["last_fed_at"] = now_str()
        self._add_history("feed", {"old": old, "new": self.pet["hunger"]})
        self._save()
        return (old, self.pet["hunger"])

    def decay_hunger(self):
        """饥饿衰减（由 scheduler 调用），返回新饱腹值"""
        if not self.pet or self.pet["stage"] == "egg":
            return None
        old = self.pet["hunger"]
        self.pet["hunger"] = max(0, old - HUNGER_DECAY_RATE)
        self.pet["last_decay_at"] = now_str()
        self._save()
        return self.pet["hunger"]

    def is_hungry(self):
        if not self.pet:
            return False
        return self.pet["hunger"] < HUNGER_ALERT_THRESHOLD

    def rename(self, new_name):
        """改名"""
        if not self.pet:
            return False
        old_name = self.pet["name"]
        self.pet["name"] = new_name
        self._add_history("rename", {"old": old_name, "new": new_name})
        self._save()
        return True

    def _add_history(self, event_type, detail):
        self.history.append({
            "type": event_type,
            "detail": detail,
            "time": now_str(),
        })
        if len(self.history) > 100:
            self.history = self.history[-100:]


# ============================================================
# 状态显示
# ============================================================
def _progress_bar(value, total=100, length=10):
    filled = round(value / total * length)
    return "\u2588" * filled + "\u2591" * (length - filled)


def _hunger_face(hunger):
    if hunger >= 80:
        return "\U0001f606"   # 😆
    if hunger >= 50:
        return "\U0001f60a"   # 😊
    if hunger >= 20:
        return "\U0001f610"   # 😐
    return "\U0001f623"       # 😣


def format_status(pet):
    """格式化宠物状态仪表盘"""
    if not pet:
        return "还没有宠物呢~ 发送「孵蛋」领养一只吧！"
    if pet["stage"] == "egg":
        return "🥚 蛋正在孵化中... 给它起个名字吧！"

    name = pet["name"] or "???"
    hunger = pet["hunger"]
    bar = _progress_bar(hunger)
    face = _hunger_face(hunger)

    lines = [
        f"\U0001f427 {name}",
        f"\U0001f356 饱腹：{face} {bar} {hunger}%",
    ]

    if hunger < 20:
        lines.append("\u26a0\ufe0f 好饿啊... 快喂我！")
    elif hunger >= 80:
        lines.append("\U0001f60a 吃饱饱，心情好~")
    elif hunger >= 50:
        lines.append("还不错，但是再吃点就更好了~")

    return "\n".join(lines)


def _feed_reply(old_hunger, new_hunger, pet_name):
    """生成喂食后的回复"""
    name = pet_name or "小企鹅"
    diff = new_hunger - old_hunger

    kaomoji_happy = random.choice([
        "(ノ´ヮ`)ノ*:・゚✧",
        "(*≧▽≦)",
        "(´꒳`)♡",
        "ヽ(>∀<☆)ノ",
    ])

    if new_hunger >= 90:
        return f"{name}吃得好饱！{kaomoji_happy}\n\U0001f356 饱腹：{_progress_bar(new_hunger)} {new_hunger}%"
    elif new_hunger >= 50:
        return f"谢谢投喂！{name}开心~ {kaomoji_happy}\n\U0001f356 饱腹：{_progress_bar(new_hunger)} {new_hunger}%"
    else:
        return f"吃到了一点东西... 但是还饿 (´;ω;`)\n\U0001f356 饱腹：{_progress_bar(new_hunger)} {new_hunger}%"


# ============================================================
# 消息路由
# ============================================================
def _rule_route(text):
    """规则路由，返回 {action, ...} 或 None（交给 AI）"""
    text = text.strip()

    # 孵蛋
    if text in ("孵蛋", "领养", "养一只", "我要宠物"):
        return {"action": "hatch"}

    # 喂食
    if text in ("喂食", "喂", "吃饭", "投喂", "喂饭", "吃东西"):
        return {"action": "feed"}

    # 查看状态
    if text in ("看看", "状态", "怎么样", "你好吗", "你还好吗", "你饿吗"):
        return {"action": "status"}

    # 改名
    for prefix in ("改名", "叫你", "你叫"):
        if text.startswith(prefix):
            name = text[len(prefix):].strip()
            if name:
                return {"action": "rename", "name": name}

    return None


class MessageHandler:
    """消息处理器"""

    def __init__(self, store=None):
        self.store = store or PetStore()
        self._user_state = {}  # {user_id: "ask_name"}

    def handle_message(self, user_id, text, is_voice=False):
        text = text.strip()
        if not text:
            return None

        # 检查状态机（孵蛋取名流程）
        if user_id in self._user_state:
            return self._handle_state(user_id, text)

        # 单主人限制
        owner_id = self.store.owner.get("user_id")
        if owner_id and owner_id != user_id:
            return "我已经有主人啦~ (\u30fb\u03c9\u30fb)"

        # 无宠物
        if self.store.pet is None:
            return self._handle_no_pet(user_id, text)

        # 规则路由
        return self._handle_normal(user_id, text)

    def _handle_no_pet(self, user_id, text):
        """没有宠物时的处理"""
        route = _rule_route(text)
        if route and route["action"] == "hatch":
            return self._start_hatch(user_id)

        return "还没有宠物呢~ 发送「孵蛋」领养一只吧！"

    def _start_hatch(self, user_id):
        """开始孵蛋流程"""
        # 先创建蛋
        self.store.create_egg(user_id, "")
        self._user_state[user_id] = "ask_name"
        return "🥚 蛋裂开了！一只小企鹅探出了头~\n\n给它起个名字吧！"

    def _handle_state(self, user_id, text):
        """处理状态机流程"""
        state = self._user_state.get(user_id)

        if state == "ask_name":
            name = text.strip()
            if len(name) > 10:
                return "名字太长啦，10个字以内哦~"
            if not name:
                return "名字不能为空哦，再试试？"
            self.store.hatch(name)
            self.store.owner["name"] = name  # 先临时用宠物名，后续可改
            del self._user_state[user_id]
            return f"\U0001f427 {name} 诞生了！\n\n它正好奇地看着你，肚子咕咕叫~\n发送「喂食」来喂它，发送「看看」查看状态！"

        # 未知状态，清除
        del self._user_state[user_id]
        return None

    def _handle_normal(self, user_id, text):
        """正常消息处理"""
        route = _rule_route(text)

        if route:
            action = route["action"]

            if action == "hatch":
                name = self.store.pet.get("name", "小企鹅")
                return f"你已经有 {name} 了呀~ (\u30fb\u03c9\u30fb)"

            if action == "feed":
                result = self.store.feed()
                if result is None:
                    return "宠物还在蛋里呢，先孵化吧~"
                old, new = result
                return _feed_reply(old, new, self.store.pet.get("name"))

            if action == "status":
                return format_status(self.store.pet)

            if action == "rename":
                new_name = route["name"]
                old_name = self.store.pet.get("name", "???")
                self.store.rename(new_name)
                return f"好的！从现在起叫 {new_name} 啦~ (之前叫{old_name})"

        # AI 兜底
        try:
            from ai import parse_message
            pet_context = {
                "name": self.store.pet.get("name", "小企鹅"),
                "hunger": self.store.pet.get("hunger", 50),
                "stage": self.store.pet.get("stage", "baby"),
            }
            result = parse_message(text, pet_context)
            if result and result.get("reply"):
                return result["reply"]
        except Exception as e:
            print(f"  AI 调用失败: {e}")

        # 最终兜底
        kaomoji = random.choice([
            "(\u30fb\u2200\u30fb)",
            "(=^\u30fb\u03c9\u30fb^=)",
            "(>_<)",
            "(\u00b4\u30fb\u03c9\u30fb\uff40)",
        ])
        return f"（歪了歪头）{kaomoji}"


# ============================================================
# 本地测试
# ============================================================
if __name__ == "__main__":
    import sys
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
    import tempfile

    # 用临时文件测试
    tmp = tempfile.mktemp(suffix=".json")
    store = PetStore(data_file=tmp)
    handler = MessageHandler(store=store)

    print("=== 017Pet core.py 测试 ===\n")

    # 无宠物时
    r = handler.handle_message("u1", "看看")
    print(f"无宠物看看: {r}")
    assert "孵蛋" in r

    # 孵蛋
    r = handler.handle_message("u1", "孵蛋")
    print(f"孵蛋: {r}")
    assert "名字" in r

    # 取名
    r = handler.handle_message("u1", "小雪")
    print(f"取名: {r}")
    assert "小雪" in r
    assert store.pet["stage"] == "baby"

    # 状态
    r = handler.handle_message("u1", "看看")
    print(f"状态: {r}")
    assert "100%" in r

    # 喂食（已满）
    r = handler.handle_message("u1", "喂食")
    print(f"喂食: {r}")
    assert "100%" in r

    # 衰减
    store.pet["hunger"] = 40
    store._save()
    r = handler.handle_message("u1", "喂食")
    print(f"饿了喂食: {r}")
    assert store.pet["hunger"] == 70

    # 改名
    r = handler.handle_message("u1", "改名小冰")
    print(f"改名: {r}")
    assert store.pet["name"] == "小冰"

    # 单主人限制
    r = handler.handle_message("u2", "看看")
    print(f"其他用户: {r}")
    assert "主人" in r

    # 衰减测试
    old_h = store.pet["hunger"]
    new_h = store.decay_hunger()
    print(f"衰减: {old_h} -> {new_h}")
    assert new_h == old_h - 5

    # 清理
    os.unlink(tmp)
    print("\n✅ 全部测试通过！")
