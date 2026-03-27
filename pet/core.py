"""
017Pet — 宠物引擎 + 消息路由（Phase 2: 多属性养成）
"""

import json
import os
import threading
import random

from config import (
    PET_DATA_FILE, now_str, today_str, now,
    HUNGER_DECAY_RATE, HUNGER_ALERT_THRESHOLD, FEED_AMOUNT,
    STAT_CONFIG, PLAY_STAMINA_COST, HEALTH_DECAY_RATE, HEALTH_RESTORE_AMOUNT,
    XP_REWARDS, GROWTH_STAGES, SLEEP_DURATION_MIN, EXPLORE_DURATION_MIN,
)

SCHEMA_VERSION = 2


# ============================================================
# 数据层
# ============================================================
class PetStore:
    """宠物数据存储，线程安全"""

    def __init__(self, data_file=None):
        self.data_file = data_file or PET_DATA_FILE
        self._lock = threading.Lock()
        self.pet = None
        self.owner = {}
        self.history = []
        self.chat_history = []  # 对话记忆
        self._load()

    def _load(self):
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.pet = data.get("pet")
                self.owner = data.get("owner", {})
                self.history = data.get("history", [])
                self.chat_history = data.get("chat_history", [])
            except (json.JSONDecodeError, KeyError):
                print("  \u26a0\ufe0f pet_data.json 损坏，使用空数据")
        self._migrate()

    def _migrate(self):
        """v1 数据自动升级到 v2"""
        if self.pet is None:
            return
        defaults = {
            "cleanliness": 80, "mood": 80, "stamina": 100, "health": 100,
            "xp": 0, "level": 1,
            "last_bathed_at": None, "last_played_at": None,
            "last_slept_at": None, "last_healed_at": None,
            "_decay_tick": 0,
            "is_sleeping": False, "sleep_until": None,
            "is_exploring": False, "explore_until": None, "explore_location": None,
        }
        changed = False
        for key, default in defaults.items():
            if key not in self.pet:
                self.pet[key] = default
                changed = True
        if changed:
            self._save()

    def _save(self):
        with self._lock:
            data = {
                "schema_version": SCHEMA_VERSION,
                "pet": self.pet,
                "owner": self.owner,
                "history": self.history,
                "chat_history": self.chat_history[-40:],  # 保留最近20轮
            }
            tmp_file = self.data_file + ".tmp"
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_file, self.data_file)

    # --- 宠物操作 ---

    def create_egg(self, user_id, user_name):
        """创建蛋，返回 True/False"""
        if self.pet is not None:
            return False
        self.pet = {
            "name": None, "stage": "egg",
            "hunger": 100, "cleanliness": 100, "mood": 100, "stamina": 100, "health": 100,
            "xp": 0, "level": 1,
            "hatched_at": None, "last_fed_at": None, "last_bathed_at": None,
            "last_played_at": None, "last_slept_at": None, "last_healed_at": None,
            "last_decay_at": None, "_decay_tick": 0,
            "created_at": now_str(),
        }
        self.owner = {"user_id": user_id, "name": user_name}
        self._add_history("create_egg", {"by": user_name})
        self._save()
        return True

    def hatch(self, name):
        """孵化：蛋→宝宝"""
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
        """喂食，返回 (old, new) 或 None"""
        if not self.pet or self.pet["stage"] == "egg":
            return None
        old = self.pet["hunger"]
        self.pet["hunger"] = min(100, old + FEED_AMOUNT)
        self.pet["last_fed_at"] = now_str()
        self._add_xp("feed")
        self._check_health()
        self._add_history("feed", {"old": old, "new": self.pet["hunger"]})
        self._save()
        return (old, self.pet["hunger"])

    def bathe(self):
        """洗澡，返回 (old, new) 或 None"""
        if not self.pet or self.pet["stage"] == "egg":
            return None
        old = self.pet["cleanliness"]
        self.pet["cleanliness"] = min(100, old + STAT_CONFIG["cleanliness"]["restore_amount"])
        self.pet["last_bathed_at"] = now_str()
        self._add_xp("bathe")
        self._check_health()
        self._add_history("bathe", {"old": old, "new": self.pet["cleanliness"]})
        self._save()
        return (old, self.pet["cleanliness"])

    def play(self):
        """逗乐/玩耍，返回 (old_mood, new_mood) 或 None 或 "no_stamina" """
        if not self.pet or self.pet["stage"] == "egg":
            return None
        if self.pet["stamina"] < PLAY_STAMINA_COST:
            return "no_stamina"
        old = self.pet["mood"]
        self.pet["mood"] = min(100, old + STAT_CONFIG["mood"]["restore_amount"])
        self.pet["stamina"] = max(0, self.pet["stamina"] - PLAY_STAMINA_COST)
        self.pet["last_played_at"] = now_str()
        self._add_xp("play")
        self._check_health()
        self._add_history("play", {"old": old, "new": self.pet["mood"], "stamina_cost": PLAY_STAMINA_COST})
        self._save()
        return (old, self.pet["mood"])

    def sleep(self):
        """睡觉，进入睡眠状态。返回 sleep_until 字符串或 None"""
        if not self.pet or self.pet["stage"] == "egg":
            return None
        if self.pet.get("is_sleeping"):
            return "already_sleeping"
        from datetime import timedelta
        wake_time = now() + timedelta(minutes=SLEEP_DURATION_MIN)
        self.pet["is_sleeping"] = True
        self.pet["sleep_until"] = wake_time.strftime("%Y-%m-%dT%H:%M:%S")
        self.pet["last_slept_at"] = now_str()
        self._add_xp("sleep")
        self._add_history("sleep", {"duration": SLEEP_DURATION_MIN})
        self._save()
        return self.pet["sleep_until"]

    def wake_up(self):
        """唤醒宠物，体力回满"""
        if not self.pet or not self.pet.get("is_sleeping"):
            return False
        self.pet["is_sleeping"] = False
        self.pet["sleep_until"] = None
        self.pet["stamina"] = 100
        self._add_history("wake_up", {"stamina": 100})
        self._save()
        return True

    def is_sleeping(self):
        """检查是否在睡觉，如果到时间了自动醒来"""
        if not self.pet or not self.pet.get("is_sleeping"):
            return False
        sleep_until = self.pet.get("sleep_until")
        if sleep_until:
            from datetime import datetime
            from config import TZ
            wake_time = datetime.strptime(sleep_until, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=TZ)
            if now() >= wake_time:
                self.wake_up()
                return False
        return True

    def sleep_remaining_min(self):
        """返回剩余睡眠分钟数"""
        if not self.pet or not self.pet.get("sleep_until"):
            return 0
        from datetime import datetime
        from config import TZ
        wake_time = datetime.strptime(self.pet["sleep_until"], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=TZ)
        remaining = (wake_time - now()).total_seconds() / 60
        return max(0, int(remaining))

    # --- 探险 ---

    EXPLORE_LOCATIONS = ["海边", "森林", "山顶", "小镇集市", "花园", "湖边", "雪山", "沙漠绿洲", "古老图书馆", "神秘洞穴"]

    def start_explore(self):
        """出发探险，返回 (location, explore_until) 或 None 或 "no_stamina" 或 "busy" """
        if not self.pet or self.pet["stage"] == "egg":
            return None
        if self.pet.get("is_sleeping"):
            return "sleeping"
        if self.pet.get("is_exploring"):
            return "already_exploring"
        if self.pet.get("stamina", 0) < 20:
            return "no_stamina"
        from datetime import timedelta
        location = random.choice(self.EXPLORE_LOCATIONS)
        return_time = now() + timedelta(minutes=EXPLORE_DURATION_MIN)
        self.pet["is_exploring"] = True
        self.pet["explore_until"] = return_time.strftime("%Y-%m-%dT%H:%M:%S")
        self.pet["explore_location"] = location
        self.pet["stamina"] = max(0, self.pet["stamina"] - 20)
        self._add_xp("explore")
        self._add_history("explore_start", {"location": location})
        self._save()
        return (location, self.pet["explore_until"])

    def finish_explore(self):
        """探险结束，返回 location 或 None"""
        if not self.pet or not self.pet.get("is_exploring"):
            return None
        location = self.pet.get("explore_location", "未知之地")
        self.pet["is_exploring"] = False
        self.pet["explore_until"] = None
        self.pet["explore_location"] = None
        self.pet["mood"] = min(100, self.pet.get("mood", 50) + 15)  # 探险回来心情变好
        self._add_history("explore_end", {"location": location})
        self._save()
        return location

    def is_exploring(self):
        """检查是否在探险，到时间自动返回"""
        if not self.pet or not self.pet.get("is_exploring"):
            return False
        explore_until = self.pet.get("explore_until")
        if explore_until:
            from datetime import datetime
            from config import TZ
            return_time = datetime.strptime(explore_until, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=TZ)
            if now() >= return_time:
                return False  # 到时间了，但不自动 finish（由 scheduler 处理）
        return True

    def explore_remaining_min(self):
        if not self.pet or not self.pet.get("explore_until"):
            return 0
        from datetime import datetime
        from config import TZ
        return_time = datetime.strptime(self.pet["explore_until"], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=TZ)
        remaining = (return_time - now()).total_seconds() / 60
        return max(0, int(remaining))

    def heal(self):
        """治疗，返回 (old, new) 或 None"""
        if not self.pet or self.pet["stage"] == "egg":
            return None
        old = self.pet["health"]
        self.pet["health"] = min(100, old + HEALTH_RESTORE_AMOUNT)
        self.pet["last_healed_at"] = now_str()
        self._add_xp("heal")
        self._add_history("heal", {"old": old, "new": self.pet["health"]})
        self._save()
        return (old, self.pet["health"])

    def decay_hunger(self):
        """Phase 1 兼容：单属性衰减"""
        if not self.pet or self.pet["stage"] == "egg":
            return None
        old = self.pet["hunger"]
        self.pet["hunger"] = max(0, old - HUNGER_DECAY_RATE)
        self.pet["last_decay_at"] = now_str()
        self._save()
        return self.pet["hunger"]

    def decay_all(self):
        """统一衰减（Phase 2），返回 {stat: (old, new)} 或 None"""
        if not self.pet or self.pet["stage"] == "egg":
            return None
        tick = self.pet.get("_decay_tick", 0) + 1
        self.pet["_decay_tick"] = tick
        results = {}
        is_sick = self.pet.get("health", 100) < 20
        mult = 1.5 if is_sick else 1.0

        for stat in ("hunger", "cleanliness", "mood"):
            cfg = STAT_CONFIG[stat]
            if tick % cfg["tick_mod"] == 0:
                old = self.pet[stat]
                self.pet[stat] = max(0, old - int(cfg["decay_rate"] * mult))
                results[stat] = (old, self.pet[stat])

        # 体力回复
        cfg = STAT_CONFIG["stamina"]
        if tick % cfg["tick_mod"] == 0:
            old = self.pet["stamina"]
            self.pet["stamina"] = min(100, old + cfg["regen_rate"])
            results["stamina"] = (old, self.pet["stamina"])

        self._check_health()
        self.pet["last_decay_at"] = now_str()
        self._save()
        return results

    def is_hungry(self):
        if not self.pet:
            return False
        return self.pet["hunger"] < HUNGER_ALERT_THRESHOLD

    def rename(self, new_name):
        if not self.pet:
            return False
        old_name = self.pet["name"]
        self.pet["name"] = new_name
        self._add_history("rename", {"old": old_name, "new": new_name})
        self._save()
        return True

    def _add_xp(self, action):
        """加经验值，升级时返回新等级"""
        xp_gain = XP_REWARDS.get(action, 0)
        self.pet["xp"] = self.pet.get("xp", 0) + xp_gain
        new_level = 1
        for i, (threshold, stage_key, _) in enumerate(GROWTH_STAGES):
            if self.pet["xp"] >= threshold:
                new_level = i + 1
        if new_level > self.pet.get("level", 1):
            self.pet["level"] = new_level
            self.pet["stage"] = GROWTH_STAGES[new_level - 1][1]
            return new_level
        return None

    def _check_health(self):
        """2+ 属性危险时健康下降"""
        critical = sum(1 for s in ("hunger", "cleanliness", "mood")
                       if self.pet.get(s, 100) < STAT_CONFIG[s]["alert_threshold"])
        if critical >= 2:
            self.pet["health"] = max(0, self.pet["health"] - HEALTH_DECAY_RATE)

    def _add_history(self, event_type, detail):
        self.history.append({"type": event_type, "detail": detail, "time": now_str()})
        if len(self.history) > 100:
            self.history = self.history[-100:]


# ============================================================
# 状态显示
# ============================================================
def _progress_bar(value, total=100, length=10):
    filled = round(value / total * length)
    return "\u2588" * filled + "\u2591" * (length - filled)


def _stat_face(value):
    if value >= 80: return "\U0001f606"
    if value >= 50: return "\U0001f60a"
    if value >= 20: return "\U0001f610"
    return "\U0001f623"


STAT_DISPLAY = [
    ("hunger",      "\U0001f356", "饱腹"),
    ("cleanliness", "\U0001f6c1", "清洁"),
    ("mood",        "\u2764\ufe0f", "心情"),
    ("stamina",     "\u26a1",     "体力"),
    ("health",      "\U0001f49a", "健康"),
]


def format_status(pet):
    """格式化宠物状态仪表盘（5 属性）"""
    if not pet:
        return "还没有宠物呢~ 发送「孵蛋」领养一只吧！"
    if pet["stage"] == "egg":
        return "\U0001f95a 蛋正在孵化中... 给它起个名字吧！"

    name = pet["name"] or "???"
    level = pet.get("level", 1)
    xp = pet.get("xp", 0)

    stage_name = "宝宝"
    for threshold, _, cn_name in GROWTH_STAGES:
        if xp >= threshold:
            stage_name = cn_name

    lines = [f"\U0001f427 {name}  Lv.{level} {stage_name}"]

    for stat_key, emoji, label in STAT_DISPLAY:
        value = pet.get(stat_key, 0)
        face = _stat_face(value)
        bar = _progress_bar(value)
        lines.append(f"{emoji} {label}：{face} {bar} {value}%")

    warnings = []
    if pet.get("hunger", 100) < 20:
        warnings.append("\u26a0\ufe0f 好饿啊... 快喂我！")
    if pet.get("cleanliness", 100) < 20:
        warnings.append("\u26a0\ufe0f 脏兮兮的... 该洗澡啦！")
    if pet.get("mood", 100) < 20:
        warnings.append("\u26a0\ufe0f 好无聊... 陪我玩嘛~")
    if pet.get("health", 100) < 20:
        warnings.append("\U0001f6a8 生病了... 需要治疗！")

    all_high = all(pet.get(s, 0) >= 80 for s, _, _ in STAT_DISPLAY)
    if all_high:
        warnings.append("\U0001f31f 状态全满！超级开心！\u30fd(>\u2200<\u2606)\uff89")

    if warnings:
        lines.append("")
        lines.extend(warnings)

    return "\n".join(lines)


# ============================================================
# 回复文案
# ============================================================
def _happy_kaomoji():
    return random.choice(["(\u30ce\u00b4\u30ee`)\u30ce*:\u30fb\u309a\u2727", "(*\u226b\u25bd\u226a)", "(\u00b4\u0e51\u0301)\u2661", "\u30fd(>\u2200<\u2606)\uff89"])


def _feed_reply(old, new, pet_name):
    name = pet_name or "小企鹅"
    k = _happy_kaomoji()
    if new >= 90:
        return f"{name}吃得好饱！{k}\n\U0001f356 饱腹：{_progress_bar(new)} {new}%"
    elif new >= 50:
        return f"谢谢投喂！{name}开心~ {k}\n\U0001f356 饱腹：{_progress_bar(new)} {new}%"
    else:
        return f"吃到了一点东西... 但是还饿 (\u00b4;\u03c9;`)\n\U0001f356 饱腹：{_progress_bar(new)} {new}%"


def _bathe_reply(old, new, pet_name):
    name = pet_name or "小企鹅"
    k = _happy_kaomoji()
    if new >= 90:
        return f"{name}洗得干干净净！{k}\n\U0001f6c1 清洁：{_progress_bar(new)} {new}%"
    return f"{name}舒舒服服洗了个澡~ {k}\n\U0001f6c1 清洁：{_progress_bar(new)} {new}%"


def _play_reply(old_mood, new_mood, pet_name, stamina):
    name = pet_name or "小企鹅"
    k = _happy_kaomoji()
    return f"{name}玩得好开心！{k}\n\u2764\ufe0f 心情：{_progress_bar(new_mood)} {new_mood}%\n\u26a1 体力：{_progress_bar(stamina)} {stamina}%"


def _sleep_reply(pet_name):
    name = pet_name or "小企鹅"
    return f"{name}美美地睡了一觉~ (\u02d8\u03c9\u02d8) zzZ\n\u26a1 体力：{_progress_bar(100)} 100%"


def _heal_reply(old, new, pet_name):
    name = pet_name or "小企鹅"
    if new >= 80:
        return f"{name}恢复健康了！(\uff89\u25d5\u30ee\u25d5)\uff89\n\U0001f49a 健康：{_progress_bar(new)} {new}%"
    return f"吃了药，{name}好多了~ (\u00b4-\u03c9-`)\n\U0001f49a 健康：{_progress_bar(new)} {new}%"


def _no_stamina_reply(pet_name, stamina):
    name = pet_name or "小企鹅"
    return f"{name}太累了，玩不动了... (\u00b4;\u03c9;`)\n\u26a1 体力：{_progress_bar(stamina)} {stamina}%\n发送「睡觉」让它休息一下吧！"


# ============================================================
# 消息路由
# ============================================================
def _extract_rename(text):
    import re
    for prefix in ("改名", "叫你", "你叫", "改名叫", "名字改成", "以后叫你"):
        if text.startswith(prefix):
            name = text[len(prefix):].strip()
            if name:
                return name
    patterns = [
        r"(?:改个?名字?|换个?名字?).*?(?:叫|改成|改为)\s*(.+?)(?:吧|呀|哦|啦|了)?$",
        r"(?:不叫了|不要叫.+了)[，,]?\s*(?:你?叫|改成|改为)\s*(.+?)(?:吧|呀|哦|啦|了)?$",
        r"(?:都说了)?你叫\s*(.+?)(?:吧|呀|哦|啦|了)?(?:[，,].+)?$",
    ]
    for p in patterns:
        m = re.search(p, text)
        if m:
            name = m.group(1).strip()
            if 1 <= len(name) <= 10:
                return name
    return None


def _rule_route(text):
    """规则路由，返回 {action, ...} 或 None。使用关键词包含匹配。"""
    text = text.strip()

    if text in ("孵蛋", "领养", "养一只", "我要宠物"):
        return {"action": "hatch"}

    # 关键词包含匹配（只要文本里出现关键词就触发）
    for kw in ("喂食", "喂饭", "投喂", "吃东西", "吃饭"):
        if kw in text:
            return {"action": "feed"}
    if text in ("喂",):
        return {"action": "feed"}

    # 探险（必须在玩耍之前，否则"出去玩"会匹配到玩耍）
    for kw in ("探险", "出去玩", "去冒险", "出门逛", "去探索", "出去逛逛"):
        if kw in text:
            return {"action": "explore"}

    for kw in ("洗澡", "洗洗", "洗个澡", "清洁"):
        if kw in text:
            return {"action": "bathe"}

    for kw in ("玩耍", "陪玩", "玩游戏", "逗乐", "陪我玩"):
        if kw in text:
            return {"action": "play"}
    if text in ("玩", "去玩"):
        return {"action": "play"}

    for kw in ("睡觉", "休息", "去睡"):
        if kw in text:
            return {"action": "sleep"}
    if text in ("睡",):
        return {"action": "sleep"}

    for kw in ("治疗", "看医生", "治病", "吃药", "看病"):
        if kw in text:
            return {"action": "heal"}

    for kw in ("看看", "状态", "怎么样", "你好吗", "你还好吗", "你饿吗"):
        if kw in text:
            return {"action": "status"}

    name = _extract_rename(text)
    if name:
        return {"action": "rename", "name": name}

    return None


class MessageHandler:
    def __init__(self, store=None):
        self.store = store or PetStore()
        self._user_state = {}

    def handle_message(self, user_id, text, is_voice=False):
        text = text.strip()
        if not text:
            return None
        if user_id in self._user_state:
            return self._handle_state(user_id, text)
        owner_id = self.store.owner.get("user_id")
        if owner_id and owner_id != user_id:
            return "我已经有主人啦~ (\u30fb\u03c9\u30fb)"
        if self.store.pet is None:
            return self._handle_no_pet(user_id, text)
        # 睡眠状态检查
        if self.store.is_sleeping():
            remaining = self.store.sleep_remaining_min()
            name = self.store.pet.get("name", "小企鹅")
            return (f"{name}正在睡觉呢 (\u02d8\u03c9\u02d8) zzZ\n还要 {remaining} 分钟才醒哦~\n轻点，别吵醒宝宝~", "sleeping")
        # 探险状态检查
        if self.store.is_exploring():
            remaining = self.store.explore_remaining_min()
            name = self.store.pet.get("name", "小企鹅")
            location = self.store.pet.get("explore_location", "外面")
            return f"{name}正在{location}探险呢~ \u2728\n还有 {remaining} 分钟回来，等我带礼物哦！"
        return self._handle_normal(user_id, text)

    def _handle_no_pet(self, user_id, text):
        route = _rule_route(text)
        if route and route["action"] == "hatch":
            return self._start_hatch(user_id)
        return "还没有宠物呢~ 发送「孵蛋」领养一只吧！"

    def _start_hatch(self, user_id):
        self.store.create_egg(user_id, "")
        self._user_state[user_id] = "ask_name"
        return ("\U0001f95a 蛋裂开了！一只小企鹅探出了头~\n\n给它起个名字吧！", "hatching")

    def _handle_state(self, user_id, text):
        state = self._user_state.get(user_id)
        if state == "ask_name":
            name = text.strip()
            if len(name) > 10:
                return "名字太长啦，10个字以内哦~"
            if not name:
                return "名字不能为空哦，再试试？"
            self.store.hatch(name)
            self.store.owner["name"] = name
            del self._user_state[user_id]
            return f"\U0001f427 {name} 诞生了！\n\n它正好奇地看着你，肚子咕咕叫~\n发送「喂食」来喂它，发送「看看」查看状态！"
        del self._user_state[user_id]
        return None

    def _handle_normal(self, user_id, text):
        """返回 str 或 (str, image_key) 元组"""
        route = _rule_route(text)
        pet = self.store.pet
        name = pet.get("name", "小企鹅")

        if route:
            action = route["action"]

            if action == "hatch":
                return f"你已经有 {name} 了呀~ (\u30fb\u03c9\u30fb)"

            if action == "feed":
                result = self.store.feed()
                if result is None:
                    return "宠物还在蛋里呢~"
                return (_feed_reply(result[0], result[1], name), "eating")

            if action == "bathe":
                result = self.store.bathe()
                if result is None:
                    return "宠物还在蛋里呢~"
                return (_bathe_reply(result[0], result[1], name), "bathing")

            if action == "play":
                result = self.store.play()
                if result is None:
                    return "宠物还在蛋里呢~"
                if result == "no_stamina":
                    return (_no_stamina_reply(name, pet.get("stamina", 0)), "tired")
                return (_play_reply(result[0], result[1], name, pet.get("stamina", 0)), "playing")

            if action == "sleep":
                result = self.store.sleep()
                if result is None:
                    return "宠物还在蛋里呢~"
                if result == "already_sleeping":
                    remaining = self.store.sleep_remaining_min()
                    return (f"{name}已经在睡觉了~ 还有 {remaining} 分钟醒来", "sleeping")
                return (f"{name}打了个哈欠，钻进被窝睡着了~ (\u02d8\u03c9\u02d8) zzZ\n{SLEEP_DURATION_MIN}分钟后醒来~", "sleeping")

            if action == "heal":
                result = self.store.heal()
                if result is None:
                    return "宠物还在蛋里呢~"
                return (_heal_reply(result[0], result[1], name), "healing")

            if action == "explore":
                result = self.store.start_explore()
                if result is None:
                    return "宠物还在蛋里呢~"
                if result == "sleeping":
                    return f"{name}在睡觉呢，醒了再出去吧~"
                if result == "already_exploring":
                    remaining = self.store.explore_remaining_min()
                    return f"{name}已经在外面探险了~ 还有 {remaining} 分钟回来"
                if result == "no_stamina":
                    return (_no_stamina_reply(name, pet.get("stamina", 0)), "tired")
                location, until = result
                return f"{name}背上小书包，向{location}出发了！\u2728\n{EXPLORE_DURATION_MIN}分钟后回来，会带故事回来哦~"

            if action == "status":
                return format_status(pet)

            if action == "rename":
                new_name = route["name"]
                old_name = pet.get("name", "???")
                self.store.rename(new_name)
                return f"好的！从现在起叫 {new_name} 啦~ (之前叫{old_name})"

        # AI 兜底（带对话记忆）
        try:
            from ai import parse_message
            pet_context = {
                "name": name, "hunger": pet.get("hunger", 50),
                "cleanliness": pet.get("cleanliness", 50), "mood": pet.get("mood", 50),
                "stamina": pet.get("stamina", 50), "health": pet.get("health", 50),
                "stage": pet.get("stage", "baby"), "level": pet.get("level", 1),
            }
            result = parse_message(text, pet_context, history=self.store.chat_history)
            if result and result.get("reply"):
                reply_text = result["reply"]
                # 记录对话历史
                self.store.chat_history.append({"role": "user", "content": text})
                self.store.chat_history.append({"role": "assistant", "content": reply_text})
                if len(self.store.chat_history) > 40:
                    self.store.chat_history = self.store.chat_history[-40:]
                self.store._save()
                return (reply_text, "idle")
        except Exception as e:
            print(f"  AI 调用失败: {e}")

        kaomoji = random.choice(["(\u30fb\u2200\u30fb)", "(=^\u30fb\u03c9\u30fb^=)", "(>_<)", "(\u00b4\u30fb\u03c9\u30fb\uff40)"])
        return f"（歪了歪头）{kaomoji}"


# ============================================================
# 本地测试
# ============================================================
if __name__ == "__main__":
    import sys
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
    import tempfile

    tmp = tempfile.mktemp(suffix=".json")
    store = PetStore(data_file=tmp)
    handler = MessageHandler(store=store)

    print("=== 017Pet Phase 2 测试 ===\n")

    # 孵蛋→取名
    r = handler.handle_message("u1", "孵蛋")
    print(f"孵蛋: {r}")
    r = handler.handle_message("u1", "小雪")
    print(f"取名: {r}")
    assert store.pet["stage"] == "baby"
    assert store.pet["cleanliness"] == 100

    # 喂食
    store.pet["hunger"] = 40
    store._save()
    r = handler.handle_message("u1", "喂食")
    print(f"喂食: {r}")
    assert store.pet["hunger"] == 70
    assert store.pet["xp"] > 0

    # 洗澡
    store.pet["cleanliness"] = 50
    store._save()
    r = handler.handle_message("u1", "洗澡")
    print(f"洗澡: {r}")
    assert store.pet["cleanliness"] == 85
    assert "清洁" in r

    # 玩耍
    r = handler.handle_message("u1", "玩")
    print(f"玩耍: {r}")
    assert "心情" in r
    assert store.pet["stamina"] < 100

    # 睡觉
    r = handler.handle_message("u1", "睡觉")
    print(f"睡觉: {r}")
    assert store.pet["stamina"] == 100

    # 体力不足
    store.pet["stamina"] = 10
    store._save()
    r = handler.handle_message("u1", "玩")
    print(f"体力不足: {r}")
    assert "累" in r or "睡觉" in r

    # 治疗
    store.pet["health"] = 30
    store._save()
    r = handler.handle_message("u1", "治疗")
    print(f"治疗: {r}")
    assert store.pet["health"] == 70
    assert "健康" in r

    # 状态显示
    r = handler.handle_message("u1", "看看")
    print(f"状态:\n{r}")
    assert "饱腹" in r and "清洁" in r and "心情" in r and "体力" in r and "健康" in r
    assert "Lv." in r

    # 改名
    r = handler.handle_message("u1", "改名小冰")
    print(f"改名: {r}")
    assert store.pet["name"] == "小冰"

    # 单主人
    r = handler.handle_message("u2", "看看")
    assert "主人" in r

    # decay_all tick 机制
    store.pet["hunger"] = 80
    store.pet["cleanliness"] = 80
    store.pet["mood"] = 80
    store.pet["stamina"] = 50
    store.pet["_decay_tick"] = 11  # next=12, 12%2=0, 12%3=0, 12%4=0 → all fire
    store._save()
    results = store.decay_all()
    print(f"decay_all: {results}")
    assert "hunger" in results
    assert "cleanliness" in results
    assert "mood" in results
    assert "stamina" in results

    # 健康检查
    store.pet["hunger"] = 10
    store.pet["cleanliness"] = 10
    store.pet["health"] = 50
    store._save()
    store._check_health()
    print(f"健康检查: health={store.pet['health']}")
    assert store.pet["health"] == 45  # -5

    # Schema 迁移
    v1_data = {"pet": {"name": "迁移", "stage": "baby", "hunger": 42}, "owner": {}, "history": []}
    tmp2 = tempfile.mktemp(suffix=".json")
    with open(tmp2, "w") as f:
        json.dump(v1_data, f)
    s2 = PetStore(data_file=tmp2)
    assert s2.pet["hunger"] == 42
    assert s2.pet["cleanliness"] == 80
    assert s2.pet["health"] == 100
    os.unlink(tmp2)
    print("迁移测试通过")

    # 路由测试
    assert _rule_route("洗澡")["action"] == "bathe"
    assert _rule_route("玩")["action"] == "play"
    assert _rule_route("睡觉")["action"] == "sleep"
    assert _rule_route("治疗")["action"] == "heal"
    assert _rule_route("看看状态")["action"] == "status"
    print("路由测试通过")

    os.unlink(tmp)
    print("\n\u2705 Phase 2 全部测试通过！")
