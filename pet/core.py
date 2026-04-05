"""
017Pet — 宠物引擎 + 消息路由（Phase 2: 多属性养成）
"""

import json
import os
import threading
import random

from config import (
    now_str, today_str, now,
    HUNGER_DECAY_RATE, HUNGER_ALERT_THRESHOLD,
    STAT_CONFIG, PLAY_STAMINA_COST, HEALTH_DECAY_RATE, HEALTH_RESTORE_AMOUNT,
    XP_REWARDS, GROWTH_STAGES, SLEEP_DURATION_MIN, EXPLORE_DURATION_MIN,
    SOUVENIRS,
)

SCHEMA_VERSION = 3

# ============================================================
# 成就定义
# ============================================================
ACHIEVEMENTS = {
    # 养成
    "first_feed":    {"name": "第一口饭",  "desc": "首次喂食", "xp": 10, "cat": "养成"},
    "first_bathe":   {"name": "干干净净",  "desc": "首次洗澡", "xp": 10, "cat": "养成"},
    "first_play":    {"name": "快乐时光",  "desc": "首次玩耍", "xp": 10, "cat": "养成"},
    "first_sleep":   {"name": "美梦成真",  "desc": "首次睡觉", "xp": 10, "cat": "养成"},
    "first_heal":    {"name": "妙手回春",  "desc": "首次治疗", "xp": 10, "cat": "养成"},
    "feed_50":       {"name": "吃货达人",  "desc": "累计喂食50次", "xp": 30, "cat": "养成"},
    "streak_3":      {"name": "每日坚持",  "desc": "连续3天互动", "xp": 20, "cat": "养成"},
    "streak_7":      {"name": "一周陪伴",  "desc": "连续7天互动", "xp": 50, "cat": "养成"},
    # 成长
    "level_2":       {"name": "初出茅庐",  "desc": "升到Lv.2", "xp": 20, "cat": "成长"},
    "level_3":       {"name": "少年出道",  "desc": "升到Lv.3", "xp": 30, "cat": "成长"},
    "level_4":       {"name": "成年礼",   "desc": "升到Lv.4", "xp": 50, "cat": "成长"},
    # 探险
    "first_explore": {"name": "第一次远行", "desc": "首次探险", "xp": 15, "cat": "探险"},
    "explore_10":    {"name": "环游世界",  "desc": "探险10次", "xp": 40, "cat": "探险"},
    "explore_5loc":  {"name": "收藏家",   "desc": "探索5个不同地点", "xp": 30, "cat": "探险"},
    # 特殊
    "all_max":       {"name": "满血状态",  "desc": "所有属性>90", "xp": 20, "cat": "特殊"},
    "revive":        {"name": "绝处逢生",  "desc": "健康从<10恢复到>80", "xp": 25, "cat": "特殊"},
    "chatty":        {"name": "话唠",     "desc": "单日发送20条消息", "xp": 15, "cat": "特殊"},
    "night_owl":     {"name": "夜猫子",   "desc": "凌晨2-4点互动", "xp": 10, "cat": "特殊"},
}


# ============================================================
# 探险地点（模块级，store.py 也会 import）
# ============================================================
EXPLORE_LOCATIONS = {
    "花园":       (20, 40),
    "湖边":       (20, 40),
    "小镇集市":   (40, 70),
    "森林":       (40, 70),
    "海边":       (60, 90),
    "山顶":       (60, 90),
    "雪山":       (80, 120),
    "沙漠绿洲":   (80, 120),
    "古老图书馆": (90, 120),
    "神秘洞穴":   (90, 120),
}


# ============================================================
# 数据层
# ============================================================
class PetStore:
    """V1 遗留类，仅用于数据迁移和本地测试。新代码请使用 store.py 的 UserPetStore。

    DEPRECATED: 将在 Phase 1 完成后移除。
    """

    def __init__(self, data_file=None):
        self.data_file = data_file or PET_DATA_FILE
        self._lock = threading.RLock()
        self.pet = None
        self.owner = {}
        self.history = []
        self.chat_history = []  # 对话记忆
        self.diary = []  # 宠物日记
        self.collection = []  # 探险收藏品
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
                self.diary = data.get("diary", [])
                self.collection = data.get("collection", [])
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
            "achievements": {}, "stats": {
                "total_feeds": 0, "total_baths": 0, "total_plays": 0,
                "total_sleeps": 0, "total_heals": 0, "total_explores": 0,
                "explore_locations": [], "consecutive_days": 0,
                "last_active_date": None, "daily_messages": 0,
                "daily_messages_date": None, "active_dates": [],
            },
        }
        changed = False
        for key, default in defaults.items():
            if key not in self.pet:
                self.pet[key] = default
                changed = True
        # 种子填充 active_dates
        stats = self.pet.setdefault("stats", {})
        active_dates = stats.setdefault("active_dates", [])
        if not active_dates:
            created_at = self.pet.get("created_at", "")
            if created_at:
                active_dates.append(created_at[:10])
            last_active = stats.get("last_active_date")
            if last_active and last_active not in active_dates:
                active_dates.append(last_active)
            if active_dates:
                changed = True
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
                "diary": self.diary[-30:],  # 保留最近30天日记
                "collection": self.collection,
            }
            tmp_file = self.data_file + ".tmp"
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_file, self.data_file)

    # --- 宠物操作 ---

    def create_egg(self, user_id, user_name):
        """创建蛋，返回 True/False"""
        with self._lock:
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
        with self._lock:
            if not self.pet or self.pet["stage"] != "egg":
                return False
            self.pet["name"] = name
            self.pet["stage"] = "baby"
            self.pet["hatched_at"] = now_str()
            self.pet["last_decay_at"] = now_str()
            self._add_history("hatch", {"name": name})
            self._save()
            return True

    @staticmethod
    def _rand_restore(amount):
        """restore_amount 可以是固定值或 (min, max) 范围"""
        if isinstance(amount, tuple):
            return random.randint(amount[0], amount[1])
        return amount

    def feed(self):
        """喂食，返回 (old, new) 或 None"""
        with self._lock:
            if not self.pet or self.pet["stage"] == "egg":
                return None
            old = self.pet["hunger"]
            restore = self._rand_restore(STAT_CONFIG["hunger"]["restore_amount"])
            self.pet["hunger"] = min(100, old + restore)
            self.pet["last_fed_at"] = now_str()
            self._add_xp("feed")
            self._check_health()
            self._add_history("feed", {"old": old, "new": self.pet["hunger"]})
            self._save()
            return (old, self.pet["hunger"])

    def bathe(self):
        """洗澡，返回 (old, new) 或 None"""
        with self._lock:
            if not self.pet or self.pet["stage"] == "egg":
                return None
            old = self.pet["cleanliness"]
            restore = self._rand_restore(STAT_CONFIG["cleanliness"]["restore_amount"])
            self.pet["cleanliness"] = min(100, old + restore)
            self.pet["last_bathed_at"] = now_str()
            self._add_xp("bathe")
            self._check_health()
            self._add_history("bathe", {"old": old, "new": self.pet["cleanliness"]})
            self._save()
            return (old, self.pet["cleanliness"])

    def play(self):
        """逗乐/玩耍，返回 (old_mood, new_mood) 或 None 或 "no_stamina" """
        with self._lock:
            if not self.pet or self.pet["stage"] == "egg":
                return None
            if self.pet["stamina"] < PLAY_STAMINA_COST:
                return "no_stamina"
            old = self.pet["mood"]
            restore = self._rand_restore(STAT_CONFIG["mood"]["restore_amount"])
            self.pet["mood"] = min(100, old + restore)
            self.pet["stamina"] = max(0, self.pet["stamina"] - PLAY_STAMINA_COST)
            self.pet["last_played_at"] = now_str()
            self._add_xp("play")
            self._check_health()
            self._add_history("play", {"old": old, "new": self.pet["mood"], "stamina_cost": PLAY_STAMINA_COST})
            self._save()
            return (old, self.pet["mood"])

    def sleep(self):
        """睡觉，进入睡眠状态。返回 sleep_until 字符串或 None"""
        with self._lock:
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
        with self._lock:
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

    def start_explore(self):
        """出发探险，返回 (location, explore_until, duration_min) 或 None 或 "no_stamina" 或 "busy" """
        with self._lock:
            if not self.pet or self.pet["stage"] == "egg":
                return None
            if self.pet.get("is_sleeping"):
                return "sleeping"
            if self.pet.get("is_exploring"):
                return "already_exploring"
            if self.pet.get("stamina", 0) < 20:
                return "no_stamina"
            from datetime import timedelta
            location = random.choice(list(EXPLORE_LOCATIONS.keys()))
            min_dur, max_dur = EXPLORE_LOCATIONS[location]
            duration = random.randint(min_dur, max_dur)
            return_time = now() + timedelta(minutes=duration)
            self.pet["is_exploring"] = True
            self.pet["explore_until"] = return_time.strftime("%Y-%m-%dT%H:%M:%S")
            self.pet["explore_location"] = location
            self.pet["stamina"] = max(0, self.pet["stamina"] - 20)
            self._add_xp("explore")
            self._add_history("explore_start", {"location": location, "duration": duration})
            self._save()
            return (location, self.pet["explore_until"], duration)

    def finish_explore(self):
        """探险结束，返回 (location, souvenir) 或 None"""
        with self._lock:
            if not self.pet or not self.pet.get("is_exploring"):
                return None
            location = self.pet.get("explore_location", "未知之地")
            self.pet["is_exploring"] = False
            self.pet["explore_until"] = None
            self.pet["explore_location"] = None
            self.pet["mood"] = min(100, self.pet.get("mood", 50) + 15)
            souvenir = None
            pool = SOUVENIRS.get(location, [])
            if pool:
                souvenir = random.choice(pool)
                if souvenir not in self.collection:
                    self.collection.append(souvenir)
            self._add_history("explore_end", {"location": location, "souvenir": souvenir})
            self._save()
            return (location, souvenir)

    def format_collection(self):
        """格式化收藏品列表"""
        if not self.collection:
            return "\U0001f392 背包空空的~ 去探险收集纪念品吧！"
        total_possible = sum(len(v) for v in SOUVENIRS.values())
        lines = [f"\U0001f392 收藏品 ({len(self.collection)}/{total_possible})\n"]
        for item in self.collection:
            lines.append(f"  \u2728 {item}")
        return "\n".join(lines)

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
        with self._lock:
            if not self.pet or self.pet["stage"] == "egg":
                return None
            old = self.pet["health"]
            restore = self._rand_restore(HEALTH_RESTORE_AMOUNT)
            self.pet["health"] = min(100, old + restore)
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
        with self._lock:
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

    # --- 日记系统 ---

    def get_today_events(self):
        """提取今天的事件摘要，用于生成日记"""
        today = today_str()
        events = [h for h in self.history if h["time"].startswith(today)]
        summary = {"feeds": 0, "baths": 0, "plays": 0, "sleeps": 0, "heals": 0, "explores": [], "chats": 0}
        for e in events:
            t = e["type"]
            if t == "feed": summary["feeds"] += 1
            elif t == "bathe": summary["baths"] += 1
            elif t == "play": summary["plays"] += 1
            elif t == "sleep": summary["sleeps"] += 1
            elif t == "heal": summary["heals"] += 1
            elif t == "explore_end":
                loc = e.get("detail", {}).get("location", "")
                if loc: summary["explores"].append(loc)
        summary["chats"] = len([h for h in self.chat_history if True])  # approximate
        return summary

    def add_diary_entry(self, date_str, content):
        """添加日记条目"""
        self.diary.append({"date": date_str, "content": content})
        if len(self.diary) > 30:
            self.diary = self.diary[-30:]
        self._save()

    def format_diary(self, days=7):
        """格式化最近N天日记"""
        if not self.diary:
            return "日记本还是空的呢~ 明天就开始写日记！"
        recent = self.diary[-days:]
        lines = ["\U0001f4d6 宠物日记\n"]
        for entry in reversed(recent):
            lines.append(f"\u2500\u2500 {entry['date']} \u2500\u2500")
            lines.append(entry["content"])
            lines.append("")
        return "\n".join(lines)

    # --- 成就系统 ---

    def _get_stats(self):
        return self.pet.setdefault("stats", {
            "total_feeds": 0, "total_baths": 0, "total_plays": 0,
            "total_sleeps": 0, "total_heals": 0, "total_explores": 0,
            "explore_locations": [], "consecutive_days": 0,
            "last_active_date": None, "daily_messages": 0,
            "daily_messages_date": None, "active_dates": [],
        })

    def _get_achievements(self):
        return self.pet.setdefault("achievements", {})

    def _unlock(self, ach_id):
        """解锁成就，返回成就信息 dict 或 None（已解锁）"""
        achs = self._get_achievements()
        if ach_id in achs:
            return None
        if ach_id not in ACHIEVEMENTS:
            return None
        achs[ach_id] = now_str()
        ach = ACHIEVEMENTS[ach_id]
        self.pet["xp"] = self.pet.get("xp", 0) + ach["xp"]
        self._add_history("achievement", {"id": ach_id, "name": ach["name"]})
        return ach

    def record_action(self, action):
        """记录操作统计+检查成就，返回新解锁的成就列表"""
        with self._lock:
            return self._record_action_locked(action)

    def _record_action_locked(self, action):
        stats = self._get_stats()
        unlocked = []

        # 更新每日活跃
        today = today_str()
        if stats.get("last_active_date") != today:
            if stats.get("last_active_date"):
                from datetime import datetime, timedelta
                from config import parse_date
                last = parse_date(stats["last_active_date"])
                if last and (parse_date(today) - last).days == 1:
                    stats["consecutive_days"] = stats.get("consecutive_days", 0) + 1
                else:
                    stats["consecutive_days"] = 1
            else:
                stats["consecutive_days"] = 1
            stats["last_active_date"] = today
            stats["daily_messages"] = 0
            stats["daily_messages_date"] = today

        # 维护 active_dates 列表
        active_dates = stats.setdefault("active_dates", [])
        if today not in active_dates:
            active_dates.append(today)

        stats["daily_messages"] = stats.get("daily_messages", 0) + 1

        # 操作计数
        count_map = {
            "feed": "total_feeds", "bathe": "total_baths", "play": "total_plays",
            "sleep": "total_sleeps", "heal": "total_heals", "explore": "total_explores",
        }
        if action in count_map:
            stats[count_map[action]] = stats.get(count_map[action], 0) + 1

        # 首次成就
        first_map = {
            "feed": "first_feed", "bathe": "first_bathe", "play": "first_play",
            "sleep": "first_sleep", "heal": "first_heal", "explore": "first_explore",
        }
        if action in first_map:
            ach = self._unlock(first_map[action])
            if ach:
                unlocked.append(ach)

        # 累计成就
        if stats.get("total_feeds", 0) >= 50:
            ach = self._unlock("feed_50")
            if ach: unlocked.append(ach)
        if stats.get("total_explores", 0) >= 10:
            ach = self._unlock("explore_10")
            if ach: unlocked.append(ach)

        # 连续天数
        if stats.get("consecutive_days", 0) >= 3:
            ach = self._unlock("streak_3")
            if ach: unlocked.append(ach)
        if stats.get("consecutive_days", 0) >= 7:
            ach = self._unlock("streak_7")
            if ach: unlocked.append(ach)

        # 等级成就
        level = self.pet.get("level", 1)
        if level >= 2:
            ach = self._unlock("level_2")
            if ach: unlocked.append(ach)
        if level >= 3:
            ach = self._unlock("level_3")
            if ach: unlocked.append(ach)
        if level >= 4:
            ach = self._unlock("level_4")
            if ach: unlocked.append(ach)

        # 探险地点
        if action == "explore" and self.pet.get("explore_location"):
            locs = stats.setdefault("explore_locations", [])
            loc = self.pet["explore_location"]
            if loc not in locs:
                locs.append(loc)
            if len(locs) >= 5:
                ach = self._unlock("explore_5loc")
                if ach: unlocked.append(ach)

        # 特殊成就
        if all(self.pet.get(s, 0) > 90 for s in ("hunger", "cleanliness", "mood", "stamina", "health")):
            ach = self._unlock("all_max")
            if ach: unlocked.append(ach)

        if stats.get("daily_messages", 0) >= 20:
            ach = self._unlock("chatty")
            if ach: unlocked.append(ach)

        hour = now().hour
        if 2 <= hour < 4:
            ach = self._unlock("night_owl")
            if ach: unlocked.append(ach)

        self._save()
        return unlocked

    def check_health_achievement(self):
        """健康恢复成就（治疗后调用）"""
        if self.pet.get("health", 0) > 80:
            # 检查历史是否有健康<10的记录
            for h in reversed(self.history[-20:]):
                if h.get("type") == "heal" and h.get("detail", {}).get("old", 100) < 10:
                    return self._unlock("revive")
        return None

    def format_achievements(self):
        """格式化成就列表"""
        achs = self._get_achievements()
        if not achs:
            return "还没有解锁任何成就哦~ 继续加油！"
        lines = ["\U0001f3c6 成就列表\n"]
        by_cat = {}
        for ach_id, unlock_time in achs.items():
            info = ACHIEVEMENTS.get(ach_id, {})
            cat = info.get("cat", "其他")
            by_cat.setdefault(cat, []).append((info.get("name", ach_id), info.get("desc", "")))
        for cat in ("养成", "成长", "探险", "特殊"):
            items = by_cat.get(cat, [])
            if items:
                lines.append(f"\n【{cat}】")
                for name, desc in items:
                    lines.append(f"  \u2705 {name} — {desc}")
        # 未解锁数
        total = len(ACHIEVEMENTS)
        done = len(achs)
        lines.append(f"\n进度：{done}/{total}")
        return "\n".join(lines)


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


def _xp_for_next_stage(xp):
    """返回 (当前阶段名, 当前阶段起始XP, 下一阶段XP) 用于进度计算"""
    current_name = "宝宝"
    current_threshold = 0
    next_threshold = None
    for i, (threshold, _, cn_name) in enumerate(GROWTH_STAGES):
        if xp >= threshold:
            current_name = cn_name
            current_threshold = threshold
            if i + 1 < len(GROWTH_STAGES):
                next_threshold = GROWTH_STAGES[i + 1][0]
            else:
                next_threshold = None  # 已满级
    return current_name, current_threshold, next_threshold


def format_status(pet):
    """格式化宠物状态卡（小Q风格）"""
    if not pet:
        return "还没有宠物呢~ 发送「孵蛋」领养一只吧！"
    if pet["stage"] == "egg":
        return "\U0001f95a 蛋正在孵化中... 给它起个名字吧！"

    name = pet["name"] or "???"
    level = pet.get("level", 1)
    xp = pet.get("xp", 0)
    stage_name, stage_start, next_stage_xp = _xp_for_next_stage(xp)

    # 头部：名字 + 等级 + 阶段
    lines = [f"\U0001f427 {name}  Lv.{level} · {stage_name}"]
    lines.append("─" * 18)

    # 5 属性进度条
    for stat_key, emoji, label in STAT_DISPLAY:
        value = pet.get(stat_key, 0)
        bar = _progress_bar(value)
        lines.append(f"{emoji} {label} {bar} {value}%")

    # 经验进度
    lines.append("─" * 18)
    if next_stage_xp:
        xp_progress = xp - stage_start
        xp_needed = next_stage_xp - stage_start
        xp_bar = _progress_bar(xp_progress, xp_needed, 8)
        lines.append(f"\u2b50 经验 {xp_bar} {xp}/{next_stage_xp}")
    else:
        lines.append(f"\u2b50 经验 {xp} （已满级！）")

    # 性格标签（Phase 2）
    traits = pet.get("traits", {})
    if traits:
        tags = _trait_tags(traits)
        lines.append(f"🎭 性格：{tags}")

    intimacy = pet.get("intimacy", 0.3)
    hearts = "❤️" * int(intimacy * 5)
    if not hearts:
        hearts = "🤍"
    lines.append(f"💕 亲密度：{hearts}")

    # 成就统计
    achs = pet.get("achievements", {})
    done = len(achs)
    total = len(ACHIEVEMENTS)
    lines.append(f"\U0001f3c6 成就 {done}/{total}")

    # 在一起的天数
    stats = pet.get("stats", {})
    if stats.get("active_dates"):
        from config import now as _now
        first_day = min(stats["active_dates"])
        today = _now().strftime("%Y-%m-%d")
        from datetime import datetime
        days = (datetime.strptime(today, "%Y-%m-%d") - datetime.strptime(first_day, "%Y-%m-%d")).days + 1
        lines.append(f"\U0001f4c5 在一起 {days} 天")

    # 额度信息（Phase 4）
    from quota import QuotaManager
    qm = QuotaManager.from_dict(pet.get("quota", {}))
    lines.append("")
    lines.append(qm.format_status())

    # 当前状态提示
    lines.append("─" * 18)
    if pet.get("is_sleeping"):
        lines.append("\U0001f4a4 正在睡觉...")
    elif pet.get("is_exploring"):
        loc = pet.get("explore_location", "外面")
        lines.append(f"\U0001f30d 正在{loc}探险...")
    else:
        # 综合评语
        avg = sum(pet.get(s, 0) for s, _, _ in STAT_DISPLAY) / 5
        if avg >= 80:
            lines.append("\U0001f31f 状态超棒！开心得转圈圈~")
        elif avg >= 50:
            lines.append("\U0001f60a 状态还不错~")
        elif avg >= 20:
            lines.append("\U0001f610 有点疲惫，需要照顾一下...")
        else:
            lines.append("\U0001f622 状态很差！快来照顾我...")

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


PLAY_ACTIVITIES = [
    ("{name}在草地上追着小球跑来跑去！", "playing"),
    ("{name}拿起小吉他弹了一首歌~ 🎸", "happy"),
    ("{name}和蝴蝶玩起了追逐游戏~", "playing"),
    ("{name}堆了一个小沙堡，好有成就感！", "happy"),
    ("{name}在地上画画，画了一幅自画像~", "happy"),
    ("{name}玩起了捉迷藏，躲在桌子底下偷笑~", "playing"),
    ("{name}在水坑里踩水玩，溅了一身水花！", "playing"),
    ("{name}找到一根树枝当宝剑，挥来挥去~", "playing"),
    ("{name}对着镜子做鬼脸，自己笑得前仰后合~", "happy"),
    ("{name}叼着飞盘跑了好几圈！", "playing"),
    ("{name}在阳台上看云，发现一朵像鱼的云~", "idle"),
    ("{name}跟蚂蚁赛跑，结果蚂蚁赢了~", "playing"),
]


def _play_reply(old_mood, new_mood, pet_name, stamina):
    name = pet_name or "小企鹅"
    activity, img = random.choice(PLAY_ACTIVITIES)
    return (
        f"{activity.format(name=name)}\n"
        f"\u2764\ufe0f 心情：{_progress_bar(new_mood)} {new_mood}%\n"
        f"\u26a1 体力：{_progress_bar(stamina)} {stamina}%",
        img
    )


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


def _is_question(text):
    """检测是否为问句，避免问句误触发操作"""
    question_endings = ("吗", "没", "呢", "吗？", "吗?", "没有", "了没", "了吗", "？", "?")
    return any(text.endswith(q) for q in question_endings)


def _calc_days_together(pet):
    """计算在一起天数。"""
    stats = pet.get("stats", {})
    if stats.get("active_dates"):
        first_day = min(stats["active_dates"])
        from datetime import datetime as _dt
        today = now().strftime("%Y-%m-%d")
        return (_dt.strptime(today, "%Y-%m-%d") - _dt.strptime(first_day, "%Y-%m-%d")).days + 1
    return 0


def _rule_route(text):
    """规则路由，返回 {action, ...} 或 None。使用关键词包含匹配。"""
    text = text.strip()

    if text in ("孵蛋", "领养", "养一只", "我要宠物"):
        return {"action": "hatch"}

    # 关键词包含匹配（只要文本里出现关键词就触发）
    # 治疗（必须在喂食之前，否则"吃药"会被喂食抢走）
    for kw in ("治疗", "去医生", "治病", "吃药", "看病"):
        if kw in text:
            return {"action": "heal"}

    for kw in ("喂食", "喂宠物", "投喂"):
        if kw in text:
            return {"action": "feed"}
    if (text.startswith("吃") or text.startswith("喂")) and not _is_question(text):
        return {"action": "feed"}

    # 探险（只有明确说"探险/冒险/探索"才触发远征）
    for kw in ("探险", "去冒险", "去探索"):
        if kw in text:
            return {"action": "explore"}

    for kw in ("洗澡", "洗洗", "洗个澡", "清洁"):
        if kw in text:
            return {"action": "bathe"}

    # 玩耍（包括"出去玩"——本地随机活动）
    for kw in ("玩耍", "陪玩", "玩游戏", "逗乐", "陪我玩", "出去玩", "出门逛", "出去逛逛"):
        if kw in text:
            return {"action": "play"}
    if text in ("玩", "去玩"):
        return {"action": "play"}

    for kw in ("睡觉", "休息", "去睡"):
        if kw in text:
            return {"action": "sleep"}
    if text in ("睡",):
        return {"action": "sleep"}

    for kw in ("成就", "成就列表", "奖杯"):
        if kw in text:
            return {"action": "achievements"}

    for kw in ("日记", "看日记", "日记本"):
        if kw in text:
            return {"action": "diary"}

    for kw in ("收藏", "背包", "纪念品", "收集"):
        if kw in text:
            return {"action": "collection"}

    for kw in ("邀请码", "邀请"):
        if kw in text:
            return {"action": "invite_code"}

    for kw in ("名片", "我的卡片"):
        if kw in text:
            return {"action": "profile_card"}

    for kw in ("充值", "买星星", "补充星星"):
        if kw in text:
            return {"action": "recharge"}

    for kw in ("看看", "状态", "你好吗", "你还好吗", "你饿吗"):
        if kw in text:
            return {"action": "status"}

    name = _extract_rename(text)
    if name:
        return {"action": "rename", "name": name}

    # 主人自报姓名
    import re as _re
    m = _re.match(r"(?:我(?:的名字)?(?:是|叫)|叫我)(.{1,10})", text)
    if m:
        return {"action": "set_owner_name", "owner_name": m.group(1).strip()}

    return None


# ============================================================
# 性格标签（Phase 2）
# ============================================================
TRAIT_LABELS = {
    "extrovert": {"high": "活泼", "mid": "", "low": "安静"},
    "brave": {"high": "勇敢", "mid": "", "low": "谨慎"},
    "greedy": {"high": "嘴馋", "mid": "", "low": "克制"},
    "curious": {"high": "好奇", "mid": "", "low": "安逸"},
    "blunt": {"high": "直球", "mid": "", "low": "委婉"},
}


def _trait_tags(traits):
    """从性格值生成最显著的标签（最多 3 个）。"""
    from personality import get_trait_band
    tags = []
    for key, value in traits.items():
        band = get_trait_band(value)
        label = TRAIT_LABELS.get(key, {}).get(band, "")
        if label:
            tags.append(label)
    if not tags:
        tags = ["中庸"]
    return "·".join(tags[:3])


class MessageHandler:
    def __init__(self, registry=None, store=None):
        # V2: 优先使用 registry（多用户），兼容 V1 store（本地测试）
        self._registry = registry
        self._legacy_store = store
        self._user_state = {}

    def _get_store(self, user_id):
        """获取 user 对应的 store 实例"""
        if self._registry:
            return self._registry.get_or_create(user_id)
        return self._legacy_store

    def handle_message(self, user_id, text, is_voice=False):
        text = text.strip()
        if not text:
            return None
        store = self._get_store(user_id)
        # 重启恢复：检测未完成的孵蛋/起名流程
        if user_id not in self._user_state and store.pet is not None:
            if store.pet.get("stage") == "egg" and not store.pet.get("name"):
                self._user_state[user_id] = "ask_name_v2"
                return (
                    "🥚 上次还没给宠物起名字呢~ 给它取个名字吧！",
                    "hatching"
                )
            elif not store.owner.get("display_name"):
                self._user_state[user_id] = "ask_owner_name"
                pet_name = store.get_pet_name() if hasattr(store, 'get_pet_name') else store.pet.get("name", "宠物")
                return f"{pet_name}歪着头看着你：你希望我叫你什么呀？"
        if user_id in self._user_state:
            return self._handle_state(user_id, text)
        if store.pet is None:
            return self._handle_no_pet(user_id, text)
        # 睡眠状态检查
        if store.is_sleeping():
            remaining = store.sleep_remaining_min() if hasattr(store, 'sleep_remaining_min') else 0
            name = store.get_pet_name() if hasattr(store, 'get_pet_name') else store.pet.get("name", "宠物")
            return (f"{name}正在睡觉呢 (\u02d8\u03c9\u02d8) zzZ\n还要 {remaining} 分钟才醒哦~\n轻点，别吵醒宝宝~", "sleeping")
        # 探险状态检查：允许照顾类操作，只拦截冲突操作
        if store.is_exploring():
            route = _rule_route(text)
            if route and route["action"] in ("explore", "sleep"):
                remaining = store.explore_remaining_min() if hasattr(store, 'explore_remaining_min') else 0
                name = store.get_pet_name() if hasattr(store, 'get_pet_name') else store.pet.get("name", "宠物")
                location = store.pet.get("explore_location", "外面")
                if route["action"] == "explore":
                    return f"{name}已经在{location}探险了~ 还有 {remaining} 分钟回来"
                else:
                    return f"{name}在{location}探险呢，回来了再睡吧~"
        # 探险已过期但 scheduler 还没结算 → 立即结算
        if store.pet.get("is_exploring") and not store.is_exploring():
            result = store.finish_explore()
            name = store.get_pet_name() if hasattr(store, 'get_pet_name') else store.pet.get("name", "宠物")
            if result:
                location, souvenir = result
                souvenir_text = f"\n\U0001f381 还带回了纪念品：{souvenir}！" if souvenir else ""
                return f"{name}刚从{location}回来！\u2728 玩得好开心~\n（正好收到你的消息啦！）{souvenir_text}"
        return self._handle_normal(user_id, text)

    def _handle_no_pet(self, user_id, text):
        route = _rule_route(text)
        if route and route["action"] == "hatch":
            return self._start_hatch(user_id)

        # 检查是否输入了邀请码（4位字母数字）
        import re as _re
        if _re.match(r'^[A-Za-z0-9]{4}$', text.strip()):
            try:
                store = self._get_store(user_id)
                data_dir = os.path.dirname(store.user_dir)
                from invite import InviteManager
                mgr = InviteManager(data_dir)
                code = text.strip().upper()
                result = mgr.validate_code(code)
                if result and not result.get("used_by"):
                    mgr.use_code(code, user_id)
                    # 给邀请者奖励星星
                    if self._registry:
                        inviter_id = result["inviter"]
                        inviter_store = self._registry.get_or_create(inviter_id)
                        if inviter_store.pet:
                            from quota import QuotaManager
                            qm = QuotaManager.from_dict(inviter_store.pet.get("quota", {}))
                            qm.recharge_stars(10)
                            inviter_store.pet["quota"] = qm.to_dict()
                            inviter_store._save()
                    # 进入领养流程
                    return self._start_hatch(user_id)
                elif result and result.get("used_by"):
                    return "这个邀请码已经被使用啦~\n再找朋友要一个新的吧！"
            except Exception as e:
                print(f"[invite] Validation error: {e}")

        return "还没有宠物呢~ 发送「孵蛋」领养一只吧！"

    # 孵化塑形选项
    HATCHING_OPTIONS = {
        "1": {"label": "轻轻跟它说话", "offsets": {"extrovert": 0.03, "blunt": 0.02}},
        "2": {"label": "安抚它，给它温暖", "offsets": {"brave": -0.02, "curious": -0.01}},
        "3": {"label": "鼓励它去看看外面的世界", "offsets": {"brave": 0.03, "curious": 0.03}},
    }

    def _start_hatch(self, user_id):
        store = self._get_store(user_id)
        from species import random_species, get_species
        species_id = random_species()
        try:
            store.create_egg(user_id, "", species_id)
        except TypeError:
            store.create_egg(user_id, "")
        self._user_state[user_id] = "hatching_1"
        return (
            "🥚 你获得了一颗神秘的蛋！\n\n"
            "蛋壳上隐约有花纹在闪烁... 你想对它做什么？\n\n"
            "1️⃣ 轻轻跟它说话\n"
            "2️⃣ 安抚它，给它温暖\n"
            "3️⃣ 鼓励它去看看外面的世界",
            "hatching"
        )

    def _handle_state(self, user_id, text):
        store = self._get_store(user_id)
        state = self._user_state.get(user_id)

        # 孵化塑形流程（3 步互动）
        if state and state.startswith("hatching_"):
            return self._handle_hatching_step(user_id, text, store)

        # 揭示品种后等待命名
        if state == "ask_name_v2":
            return self._handle_naming(user_id, text, store)

        # V1 遗留：直接起名
        if state == "ask_name":
            name = text.strip()
            if len(name) > 10:
                return "名字太长啦，10个字以内哦~"
            if not name:
                return "名字不能为空哦，再试试？"
            store.hatch(name)
            store.owner["name"] = name
            self._user_state[user_id] = "ask_owner_name"
            species_emoji = "🐧"
            if hasattr(store, 'get_species_id'):
                from species import get_species
                spec = get_species(store.get_species_id())
                if spec:
                    species_emoji = spec["emoji"]
            return f"{species_emoji} {name} 诞生了！\n\n{name}歪着头看着你：你希望我叫你什么呀？"

        if state == "ask_owner_name":
            owner_name = text.strip()
            if len(owner_name) > 10:
                return "名字太长啦，10个字以内哦~"
            if not owner_name:
                return "告诉我你的名字嘛~"
            pet_name = store.get_pet_name() if hasattr(store, 'get_pet_name') else store.pet.get("name", "宠物")
            store.owner["display_name"] = owner_name
            store._save()
            del self._user_state[user_id]
            return f"好的{owner_name}！以后就这么叫你啦~ ❤️\n\n{pet_name}肚子咕咕叫~ 发送「喂食」来喂它，发送「看看」查看状态！"

        del self._user_state[user_id]
        return None

    def _handle_hatching_step(self, user_id, text, store):
        """处理孵化塑形的 3 步互动。"""
        state = self._user_state[user_id]
        step = int(state.split("_")[1])

        choice = text.strip()
        if choice not in ("1", "2", "3"):
            return (
                "请输入 1、2 或 3 来选择哦~\n\n"
                "1️⃣ 轻轻跟它说话\n"
                "2️⃣ 安抚它，给它温暖\n"
                "3️⃣ 鼓励它去看看外面的世界"
            )

        # 累积孵化偏移
        offsets = self.HATCHING_OPTIONS[choice]["offsets"]
        accumulated = self._user_state.get(f"{user_id}_hatching", {})
        for k, v in offsets.items():
            accumulated[k] = accumulated.get(k, 0) + v
        self._user_state[f"{user_id}_hatching"] = accumulated

        action_label = self.HATCHING_OPTIONS[choice]["label"]

        if step < 3:
            self._user_state[user_id] = f"hatching_{step + 1}"
            egg_responses = [
                (
                    f"你选择了「{action_label}」\n\n"
                    "蛋轻轻晃动了一下... 好像有反应呢！✨\n\n"
                    "要继续吗？\n"
                    "1️⃣ 轻轻跟它说话\n"
                    "2️⃣ 安抚它，给它温暖\n"
                    "3️⃣ 鼓励它去看看外面的世界"
                ),
                (
                    f"你选择了「{action_label}」\n\n"
                    "蛋裂开了一条小缝！能隐约看到里面在动！🥚💫\n\n"
                    "最后一次，你想对它...\n"
                    "1️⃣ 轻轻跟它说话\n"
                    "2️⃣ 安抚它，给它温暖\n"
                    "3️⃣ 鼓励它去看看外面的世界"
                ),
            ]
            return egg_responses[step - 1]
        else:
            # 第 3 次互动完成，揭示品种
            from species import get_species
            species_id = store.get_species_id()
            spec = get_species(species_id)
            species_name = spec["name"]
            species_emoji = spec["emoji"]

            self._user_state[user_id] = "ask_name_v2"
            return (
                f"你选择了「{action_label}」\n\n"
                f"蛋壳碎了！✨🎉\n\n"
                f"一只{species_emoji} **{species_name}** 从蛋里探出了头！\n"
                f"它好奇地看着你，眨了眨眼睛~\n\n"
                f"给它起个名字吧！"
            )

    def _handle_naming(self, user_id, text, store):
        """揭示品种后的命名流程。"""
        name = text.strip()
        if len(name) > 10:
            return "名字太长啦，10 个字以内吧~"
        if not name:
            return "名字不能为空哦，再想一个吧~"

        from species import get_species
        from personality import compute_initial_traits

        species_id = store.get_species_id()
        spec = get_species(species_id)
        baselines = spec["baseline_traits"]
        hatching_offsets = self._user_state.pop(f"{user_id}_hatching", {})

        initial_traits = compute_initial_traits(baselines, hatching_offsets=hatching_offsets)

        store.hatch(name)

        # 写入性格
        store.pet["traits"] = initial_traits
        store.pet["trait_offsets"] = {k: 0.0 for k in initial_traits}
        store.pet["trait_daily_used"] = {k: 0.0 for k in initial_traits}
        store._save()

        # 触发异步生图（不阻塞用户）— 检查星星额度
        from quota import QuotaManager, COST_IMAGE_GEN
        qm = QuotaManager.from_dict(store.pet.get("quota", {}))
        hatch_images = ["base", "idle", "happy", "sleeping"]
        total_cost = len(hatch_images) * COST_IMAGE_GEN
        if qm.can_spend_stars(total_cost):
            qm.spend_stars(total_cost)
            store.pet["quota"] = qm.to_dict()
            store._save()
            self._async_gen_hatch_images(store.user_dir, species_id, initial_traits, user_id)
        else:
            print(f"[quota] Not enough stars for hatching images, using fallback")

        # 生成性格签卡（异步，不阻塞）
        self._async_gen_sign_card(store, species_id, initial_traits, name, spec)

        # 孵化完成时赠送 1 个邀请码
        try:
            data_dir = os.path.dirname(store.user_dir)
            from invite import InviteManager
            mgr = InviteManager(data_dir)
            invite_code = mgr.generate_code(user_id)
            print(f"[invite] Generated code {invite_code} for {user_id[:15]}")
        except Exception as e:
            print(f"[invite] Code generation failed: {e}")
            invite_code = None

        self._user_state[user_id] = "ask_owner_name"

        species_name = spec["name"]
        species_emoji = spec["emoji"]
        trait_tags = _trait_tags(initial_traits)

        return (
            f"{species_emoji} **{name}** 开心地叫了一声！\n\n"
            f"品种：{species_name}\n"
            f"性格：{trait_tags}\n\n"
            f"{name}歪着头看着你：你希望我叫你什么呀？"
        )

    def _async_gen_hatch_images(self, user_dir, species_id, traits, user_id):
        """孵化完成后异步生成初始图片（base/idle/happy/sleeping）。"""
        import threading

        def _gen():
            try:
                from image_gen import build_prompt, generate_image, save_cached_image, save_gen_metadata
                from config import now_str
                for key in ["base", "idle", "happy", "sleeping"]:
                    prompt = build_prompt(species_id, key, traits=traits)
                    result = generate_image(prompt)
                    if result.success and result.image_bytes:
                        save_cached_image(user_dir, key, result.image_bytes)
                        save_gen_metadata(user_dir, key, {
                            "prompt": prompt,
                            "model": result.model,
                            "seed": result.seed,
                            "species": species_id,
                            "action": key,
                            "generated_at": now_str(),
                        })
                        print(f"[image_gen] Generated {key} for {user_id[:15]}")
                    else:
                        print(f"[image_gen] Failed {key}: {result.error}")
            except Exception as e:
                print(f"[image_gen] Error: {e}")

        threading.Thread(target=_gen, daemon=True).start()

    def _async_gen_sign_card(self, store, species_id, traits, pet_name, spec):
        """孵化完成后异步生成性格签卡。"""
        import threading

        def _gen():
            try:
                from cards import personality_sign_card, card_to_bytes
                from assets_manager import resolve_image
                from image_gen import save_cached_image

                char_path = resolve_image(store.user_dir, species_id, "base")
                trait_tags_str = _trait_tags(traits)
                trait_desc = f"这是一只{trait_tags_str}的{spec['name']}，它的世界因为有你而变得特别。"
                card = personality_sign_card(
                    char_path, pet_name, spec["name"], spec["emoji"],
                    trait_tags_str, trait_desc
                )
                card_bytes = card_to_bytes(card)
                save_cached_image(store.user_dir, "sign_card", card_bytes)
                print(f"[cards] Sign card generated for {store.user_id[:15]}")
            except Exception as e:
                print(f"[cards] Sign card generation failed: {e}")

        threading.Thread(target=_gen, daemon=True).start()

    def _with_achievements(self, store, reply, action):
        """在回复后附加成就通知"""
        unlocked = store.record_action(action)
        if not unlocked:
            return reply
        ach_text = "\n".join(f"\n\U0001f3c6 成就解锁：{a['name']}！（{a['desc']}）+{a['xp']}XP" for a in unlocked)
        if isinstance(reply, tuple):
            return (reply[0] + ach_text, reply[1])
        return reply + ach_text

    def _handle_normal(self, user_id, text):
        """返回 str 或 (str, image_key) 元组"""
        store = self._get_store(user_id)
        route = _rule_route(text)
        pet = store.pet
        name = store.get_pet_name() if hasattr(store, 'get_pet_name') else pet.get("name", "宠物")

        if route:
            action = route["action"]

            if action == "hatch":
                return f"你已经有 {name} 了呀~ (\u30fb\u03c9\u30fb)"

            if action == "feed":
                result = store.feed()
                if result is None:
                    return "宠物还在蛋里呢~"
                return self._with_achievements(store, (_feed_reply(result[0], result[1], name), "eating"), "feed")

            if action == "bathe":
                result = store.bathe()
                if result is None:
                    return "宠物还在蛋里呢~"
                return self._with_achievements(store, (_bathe_reply(result[0], result[1], name), "bathing"), "bathe")

            if action == "play":
                result = store.play()
                if result is None:
                    return "宠物还在蛋里呢~"
                if result == "no_stamina":
                    return (_no_stamina_reply(name, pet.get("stamina", 0)), "tired")
                return self._with_achievements(store, _play_reply(result[0], result[1], name, pet.get("stamina", 0)), "play")

            if action == "sleep":
                result = store.sleep()
                if result is None:
                    return "宠物还在蛋里呢~"
                if result == "already_sleeping":
                    remaining = store.sleep_remaining_min() if hasattr(store, 'sleep_remaining_min') else 0
                    return (f"{name}已经在睡觉了~ 还有 {remaining} 分钟醒来", "sleeping")
                return self._with_achievements(store, (f"{name}打了个哈欠，钻进被窝睡着了~ (\u02d8\u03c9\u02d8) zzZ\n{SLEEP_DURATION_MIN}分钟后醒来~", "sleeping"), "sleep")

            if action == "heal":
                result = store.heal()
                if result is None:
                    return "宠物还在蛋里呢~"
                reply = self._with_achievements(store, (_heal_reply(result[0], result[1], name), "healing"), "heal")
                # 绝处逢生成就
                revive = store.check_health_achievement()
                if revive:
                    ach_text = f"\n\U0001f3c6 成就解锁：{revive['name']}！（{revive['desc']}）+{revive['xp']}XP"
                    if isinstance(reply, tuple):
                        reply = (reply[0] + ach_text, reply[1])
                    else:
                        reply = reply + ach_text
                return reply

            if action == "explore":
                result = store.start_explore()
                if result is None:
                    return "宠物还在蛋里呢~"
                if result == "sleeping":
                    return f"{name}在睡觉呢，醒了再出去吧~"
                if result == "already_exploring":
                    remaining = store.explore_remaining_min() if hasattr(store, 'explore_remaining_min') else 0
                    return f"{name}已经在外面探险了~ 还有 {remaining} 分钟回来"
                if result == "no_stamina":
                    return (_no_stamina_reply(name, pet.get("stamina", 0)), "tired")
                location, until, duration = result
                if duration >= 60:
                    time_desc = f"大约{duration // 60}小时{'多' if duration % 60 > 15 else ''}"
                else:
                    time_desc = f"大约{duration}分钟"
                return self._with_achievements(store, (f"{name}背上小书包，向{location}出发了！\u2728\n{location}{'有点远呢' if duration >= 60 else '不算太远'}，{time_desc}后回来，会带故事回来哦~", "idle"), "explore")

            if action == "achievements":
                return store.format_achievements()

            if action == "diary":
                return store.format_diary()

            if action == "collection":
                return store.format_collection()

            if action == "invite_code":
                from invite import InviteManager
                data_dir = os.path.dirname(store.user_dir)
                mgr = InviteManager(data_dir)
                available = mgr.get_available_codes(user_id)
                if available:
                    codes_text = "\n".join([f"  📮 {c['code']}" for c in available])
                    return f"你的邀请码：\n{codes_text}\n\n把邀请码分享给朋友，让他们也来领养一只宠物吧！"
                else:
                    return "你暂时没有可用的邀请码哦~\n继续养宠物，达成成就就能获得新的邀请码！"

            if action == "profile_card":
                from cards import pet_profile_card, card_to_bytes
                from assets_manager import resolve_image
                species_id = store.get_species_id() or "penguin"
                char_path = resolve_image(store.user_dir, species_id, "base")
                trait_tags_str = _trait_tags(pet.get("traits", {}))
                days = _calc_days_together(pet)
                from species import get_species as _gs
                spec = _gs(species_id)
                card = pet_profile_card(
                    char_path, name, spec["name"] if spec else "宠物",
                    spec["emoji"] if spec else "🐾",
                    trait_tags_str, "", days
                )
                card_bytes = card_to_bytes(card)
                # 保存卡片到缓存
                from image_gen import save_cached_image
                save_cached_image(store.user_dir, "profile_card", card_bytes)
                return (f"这是{name}的名片~ ✨", "profile_card")

            if action == "recharge":
                return "想要更多星星吗？✨\n\n目前是内测阶段，请联系谷雨充值~\n💰 ¥2 = 100 星星\n💰 ¥5 = 280 星星\n💰 ¥10 = 600 星星"

            if action == "status":
                # 根据综合状态选图
                avg = sum(pet.get(s, 0) for s, _, _ in STAT_DISPLAY) / 5
                if pet.get("health", 100) < 20:
                    img = "sick"
                elif avg >= 70:
                    img = "happy"
                elif avg >= 40:
                    img = "idle"
                else:
                    img = "hungry"
                return (format_status(pet), img)

            if action == "rename":
                return "暂时不支持改名哦~"

            if action == "set_owner_name":
                owner_name = route["owner_name"]
                store.owner["display_name"] = owner_name
                store._save()
                return f"知道啦！以后叫你{owner_name}~ \u2764\ufe0f"

        # AI 兜底（带对话记忆）— 额度检查
        from quota import QuotaManager, DegradationLevel, COST_AI_CHAT
        qm = QuotaManager.from_dict(pet.get("quota", {}))
        level = qm.degradation_level()

        if level == DegradationLevel.DEEP:
            replies = [
                f"{name}打了个哈欠... zzZ",
                f"{name}迷迷糊糊地蹭了蹭你~",
                f"今天有点困... 先陪你待着，等补充点星星再跟你好好聊~",
            ]
            return random.choice(replies)

        if qm.can_spend_companion(COST_AI_CHAT):
            qm.spend_companion(COST_AI_CHAT)
            store.pet["quota"] = qm.to_dict()
            store._save()
        else:
            return f"{name}有点累了，明天能量恢复了再聊吧~"

        try:
            from ai import parse_message
            # 计算在一起天数
            days_together = 0
            stats = pet.get("stats", {})
            if stats.get("active_dates"):
                first_day = min(stats["active_dates"])
                from datetime import datetime as _dt
                days_together = (_dt.strptime(today_str(), "%Y-%m-%d") - _dt.strptime(first_day, "%Y-%m-%d")).days + 1
            species_id = store.get_species_id() if hasattr(store, 'get_species_id') else "penguin"
            pet_context = {
                "name": name, "hunger": pet.get("hunger", 50),
                "cleanliness": pet.get("cleanliness", 50), "mood": pet.get("mood", 50),
                "stamina": pet.get("stamina", 50), "health": pet.get("health", 50),
                "stage": pet.get("stage", "baby"), "level": pet.get("level", 1),
                "is_exploring": pet.get("is_exploring", False),
                "explore_location": pet.get("explore_location"),
                "days_together": days_together,
                "owner_name": store.owner.get("display_name", ""),
                "traits": pet.get("traits", {}),
                "intimacy": pet.get("intimacy", 0.3),
            }
            result = parse_message(text, pet_context, history=store.chat_history,
                                      species_id=species_id, degradation=level.value)
            if result and result.get("reply"):
                reply_text = result["reply"]
                store.chat_history.append({"role": "user", "content": text})
                store.chat_history.append({"role": "assistant", "content": reply_text})
                if len(store.chat_history) > 40:
                    store.chat_history = store.chat_history[-40:]
                store._save()
                return reply_text
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

    def _text(r):
        """提取回复文本（兼容 str 和 (text, img_key) tuple）"""
        return r[0] if isinstance(r, tuple) else r

    print("=== 017Pet Phase 2 测试 ===\n")

    # 孵蛋→取名→主人称呼
    r = handler.handle_message("u1", "孵蛋")
    print(f"孵蛋: {r}")
    r = handler.handle_message("u1", "小雪")
    print(f"取名: {r}")
    assert "叫你什么" in _text(r)  # 应该追问主人称呼
    assert store.pet["stage"] == "baby"
    r = handler.handle_message("u1", "谷雨")
    print(f"主人称呼: {r}")
    assert store.owner.get("display_name") == "谷雨"
    assert "谷雨" in _text(r)
    assert store.pet["cleanliness"] == 100

    # 喂食（恢复量随机 20-40）
    store.pet["hunger"] = 40
    store._save()
    r = handler.handle_message("u1", "喂食")
    print(f"喂食: {r}")
    assert 60 <= store.pet["hunger"] <= 80
    assert store.pet["xp"] > 0

    # 洗澡（恢复量随机 25-45）
    store.pet["cleanliness"] = 50
    store._save()
    r = handler.handle_message("u1", "洗澡")
    print(f"洗澡: {r}")
    assert 75 <= store.pet["cleanliness"] <= 95
    assert "清洁" in _text(r)

    # 玩耍
    r = handler.handle_message("u1", "玩")
    print(f"玩耍: {r}")
    assert "心情" in _text(r)
    assert store.pet["stamina"] < 100

    # 睡觉（体力在醒来后才恢复，此处只检查进入睡眠状态）
    r = handler.handle_message("u1", "睡觉")
    print(f"睡觉: {r}")
    assert store.pet["is_sleeping"] is True

    # 手动唤醒以继续测试
    store.pet["is_sleeping"] = False
    store.pet["stamina"] = 100
    store._save()

    # 体力不足
    store.pet["stamina"] = 10
    store._save()
    r = handler.handle_message("u1", "玩")
    print(f"体力不足: {r}")
    assert "累" in _text(r) or "睡觉" in _text(r)

    # 治疗（恢复量随机 30-50）
    store.pet["health"] = 30
    store._save()
    r = handler.handle_message("u1", "治疗")
    print(f"治疗: {r}")
    assert 60 <= store.pet["health"] <= 80
    assert "健康" in _text(r)

    # 状态显示
    r = handler.handle_message("u1", "看看")
    print(f"状态:\n{_text(r)}")
    assert "饱腹" in _text(r) and "清洁" in _text(r) and "心情" in _text(r)
    assert "Lv." in _text(r)

    # 改名（已禁用）
    r = handler.handle_message("u1", "改名小冰")
    print(f"改名: {r}")
    assert "不支持" in _text(r)
    assert store.pet["name"] == "小雪"  # 名字不变

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
