"""多用户存储层。

UserPetStore: per-user 的宠物数据管理（替代 core.py 中 PetStore 的持久化部分）
PetRegistry: 全局注册表，管理所有用户的 store 实例（懒加载 + 启动扫描）

存储结构:
  data/
    {user_id}/
      pet.json   — 宠物数据（schema v4）
      images/    — AI 生成的图片缓存（Phase 3 使用）
"""

import json
import os
import threading
from pathlib import Path

SCHEMA_VERSION = 4


def _default_pet(species):
    """创建默认的 pet 数据结构（egg 阶段）。"""
    from config import now_str
    return {
        "name": None,
        "species": species,
        "stage": "egg",
        "hunger": 100,
        "cleanliness": 100,
        "mood": 100,
        "stamina": 100,
        "health": 100,
        "xp": 0,
        "level": 1,
        "created_at": now_str(),
        "hatched_at": None,
        "last_fed_at": None,
        "last_bathed_at": None,
        "last_played_at": None,
        "last_slept_at": None,
        "last_healed_at": None,
        "last_decay_at": None,
        "_decay_tick": 0,
        "is_sleeping": False,
        "sleep_until": None,
        "is_exploring": False,
        "explore_until": None,
        "explore_location": None,
        "achievements": {},
        "stats": {
            "total_feeds": 0,
            "total_baths": 0,
            "total_plays": 0,
            "total_sleeps": 0,
            "total_heals": 0,
            "total_explores": 0,
            "explore_locations": [],
            "consecutive_days": 0,
            "last_active_date": None,
            "daily_messages": 0,
            "daily_messages_date": None,
            "active_dates": [],
        },
    }


class UserPetStore:
    """单个用户的宠物数据存储。

    数据存放在 {data_dir}/{user_id}/pet.json。
    所有写操作通过 _save() 原子写入。
    线程安全：所有状态修改需要持有 _lock。

    与 V1 PetStore 的区别：
    - 不再是单例，每个用户一个实例
    - data_file 路径由 data_dir + user_id 决定
    - pet 数据增加 species 字段
    - schema_version 升到 4
    """

    def __init__(self, user_id, data_dir):
        self.user_id = user_id
        self.user_dir = os.path.join(data_dir, user_id)
        self.data_file = os.path.join(self.user_dir, "pet.json")
        self._lock = threading.RLock()

        # 确保用户目录存在
        os.makedirs(self.user_dir, exist_ok=True)

        # 数据字段（与 V1 PetStore 保持一致的接口）
        self.pet = None
        self.owner = {}
        self.history = []
        self.chat_history = []
        self.diary = []
        self.collection = []

        self._load()

    def _load(self):
        """从文件加载数据。文件不存在则保持空状态。"""
        if not os.path.exists(self.data_file):
            return
        try:
            with open(self.data_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError):
            print(f"[store] WARNING: corrupt data for {self.user_id}, starting fresh")
            return

        self.pet = data.get("pet")
        self.owner = data.get("owner", {})
        self.history = data.get("history", [])
        self.chat_history = data.get("chat_history", [])
        self.diary = data.get("diary", [])
        self.collection = data.get("collection", [])

        self._migrate(data.get("schema_version", 1))

    def _migrate(self, from_version):
        """数据迁移。V3 → V4: 添加 species 字段。"""
        if self.pet is None:
            return
        # v3 → v4: 添加 species（旧数据默认 penguin）
        if from_version < 4:
            if "species" not in self.pet:
                self.pet["species"] = "penguin"
            self._save()

    def _save(self):
        """原子写入：先写 .tmp 再 os.replace()。"""
        data = {
            "schema_version": SCHEMA_VERSION,
            "pet": self.pet,
            "owner": self.owner,
            "history": self.history[-100:],
            "chat_history": self.chat_history[-40:],
            "diary": self.diary[-30:],
            "collection": self.collection,
        }
        tmp = self.data_file + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.data_file)

    def create_egg(self, user_id, user_name, species):
        """创建宠物蛋。species 是品种 ID（如 'penguin'、'fox'）。"""
        with self._lock:
            if self.pet is not None:
                return False
            self.pet = _default_pet(species)
            self.owner = {
                "user_id": user_id,
                "name": user_name,
                "display_name": "主人",
            }
            self.history = [{
                "type": "create_egg",
                "detail": {"species": species},
                "time": self.pet["created_at"],
            }]
            self._save()
            return True

    def hatch(self, name):
        """孵化：egg → baby，设置宠物名字。"""
        with self._lock:
            if self.pet is None or self.pet["stage"] != "egg":
                return False
            from config import now_str
            self.pet["name"] = name
            self.pet["stage"] = "baby"
            self.pet["hatched_at"] = now_str()
            self.history.append({
                "type": "hatch",
                "detail": {"name": name},
                "time": now_str(),
            })
            self._save()
            return True

    def feed(self):
        """喂食。返回 (old, new) 或 None。"""
        import random
        from config import STAT_CONFIG, now_str
        with self._lock:
            if self.pet is None or self.pet["stage"] == "egg":
                return None
            cfg = STAT_CONFIG["hunger"]
            old = self.pet["hunger"]
            lo, hi = cfg["restore_amount"]
            amt = random.randint(lo, hi)
            self.pet["hunger"] = min(100, old + amt)
            self.pet["last_fed_at"] = now_str()
            self._save()
            return (old, self.pet["hunger"])

    def bathe(self):
        """洗澡。返回 (old, new) 或 None。"""
        import random
        from config import STAT_CONFIG, now_str
        with self._lock:
            if self.pet is None or self.pet["stage"] == "egg":
                return None
            cfg = STAT_CONFIG["cleanliness"]
            old = self.pet["cleanliness"]
            lo, hi = cfg["restore_amount"]
            amt = random.randint(lo, hi)
            self.pet["cleanliness"] = min(100, old + amt)
            self.pet["last_bathed_at"] = now_str()
            self._save()
            return (old, self.pet["cleanliness"])

    def play(self):
        """玩耍。返回 (old_mood, new_mood) 或 "no_stamina" 或 None。"""
        import random
        from config import STAT_CONFIG, PLAY_STAMINA_COST, now_str
        with self._lock:
            if self.pet is None or self.pet["stage"] == "egg":
                return None
            if self.pet["stamina"] < PLAY_STAMINA_COST:
                return "no_stamina"
            cfg = STAT_CONFIG["mood"]
            old = self.pet["mood"]
            lo, hi = cfg["restore_amount"]
            amt = random.randint(lo, hi)
            self.pet["mood"] = min(100, old + amt)
            self.pet["stamina"] = max(0, self.pet["stamina"] - PLAY_STAMINA_COST)
            self.pet["last_played_at"] = now_str()
            self._save()
            return (old, self.pet["mood"])

    def heal(self):
        """治疗。返回 (old, new) 或 None。"""
        import random
        from config import HEALTH_RESTORE_AMOUNT, now_str
        with self._lock:
            if self.pet is None or self.pet["stage"] == "egg":
                return None
            old = self.pet["health"]
            lo, hi = HEALTH_RESTORE_AMOUNT
            amt = random.randint(lo, hi)
            self.pet["health"] = min(100, old + amt)
            self.pet["last_healed_at"] = now_str()
            self._save()
            return (old, self.pet["health"])

    def sleep(self):
        """睡觉。返回 sleep_until ISO 字符串，或 "already_sleeping"。"""
        from config import SLEEP_DURATION_MIN, now, now_str
        from datetime import timedelta
        with self._lock:
            if self.pet is None or self.pet["stage"] == "egg":
                return None
            if self.pet.get("is_sleeping"):
                return "already_sleeping"
            wake_time = now() + timedelta(minutes=SLEEP_DURATION_MIN)
            self.pet["is_sleeping"] = True
            self.pet["sleep_until"] = wake_time.isoformat()
            self.pet["last_slept_at"] = now_str()
            self._save()
            return wake_time.isoformat()

    def wake_up(self):
        """醒来。返回 True/False。"""
        with self._lock:
            if self.pet is None or not self.pet.get("is_sleeping"):
                return False
            self.pet["is_sleeping"] = False
            self.pet["sleep_until"] = None
            self.pet["stamina"] = 100
            self._save()
            return True

    def is_sleeping(self):
        """检查是否在睡觉。如果已过 sleep_until 自动醒来。"""
        from config import now
        from datetime import datetime
        from zoneinfo import ZoneInfo
        with self._lock:
            if self.pet is None or not self.pet.get("is_sleeping"):
                return False
            until = self.pet.get("sleep_until")
            if until:
                t = datetime.fromisoformat(until)
                if t.tzinfo is None:
                    from config import TIMEZONE
                    t = t.replace(tzinfo=ZoneInfo(TIMEZONE))
                if now() >= t:
                    self.wake_up()
                    return False
            return True

    def start_explore(self):
        """开始探险。返回 (location, until_iso, duration_min) 或错误字符串。"""
        import random
        from config import now, now_str
        from datetime import timedelta
        with self._lock:
            if self.pet is None or self.pet["stage"] == "egg":
                return None
            if self.pet.get("is_sleeping"):
                return "sleeping"
            if self.pet.get("is_exploring"):
                return "already_exploring"
            from core import EXPLORE_LOCATIONS
            loc = random.choice(list(EXPLORE_LOCATIONS.keys()))
            lo, hi = EXPLORE_LOCATIONS[loc]
            dur = random.randint(lo, hi)
            until = now() + timedelta(minutes=dur)
            self.pet["is_exploring"] = True
            self.pet["explore_until"] = until.isoformat()
            self.pet["explore_location"] = loc
            self._save()
            return (loc, until.isoformat(), dur)

    def finish_explore(self):
        """结束探险。返回 (location, souvenir_or_None) 或 None。"""
        import random
        from config import SOUVENIRS
        with self._lock:
            if self.pet is None or not self.pet.get("is_exploring"):
                return None
            loc = self.pet.get("explore_location", "未知")
            self.pet["is_exploring"] = False
            self.pet["explore_until"] = None
            self.pet["explore_location"] = None
            # Mood bonus
            self.pet["mood"] = min(100, self.pet["mood"] + 15)
            # Souvenir
            souvenir = None
            candidates = SOUVENIRS.get(loc, [])
            available = [s for s in candidates if s not in self.collection]
            if available and random.random() < 0.6:
                souvenir = random.choice(available)
                self.collection.append(souvenir)
            self._save()
            return (loc, souvenir)

    def is_exploring(self):
        """检查是否在探险。如果已过 explore_until 返回 False。"""
        from config import now
        from datetime import datetime
        from zoneinfo import ZoneInfo
        with self._lock:
            if self.pet is None or not self.pet.get("is_exploring"):
                return False
            until = self.pet.get("explore_until")
            if until:
                t = datetime.fromisoformat(until)
                if t.tzinfo is None:
                    from config import TIMEZONE
                    t = t.replace(tzinfo=ZoneInfo(TIMEZONE))
                if now() >= t:
                    return False
            return True

    def decay_all(self):
        """属性衰减 tick。返回 {stat: (old, new)}。"""
        from config import STAT_CONFIG, HEALTH_DECAY_RATE
        with self._lock:
            if self.pet is None or self.pet["stage"] == "egg":
                return {}
            if self.pet.get("is_sleeping") or self.pet.get("is_exploring"):
                return {}

            self.pet["_decay_tick"] = self.pet.get("_decay_tick", 0) + 1
            tick = self.pet["_decay_tick"]
            results = {}
            sick_mult = 1.5 if self.pet["health"] < 20 else 1.0

            for stat, cfg in STAT_CONFIG.items():
                if stat == "stamina":
                    if tick % cfg["tick_mod"] == 0:
                        old = self.pet["stamina"]
                        self.pet["stamina"] = min(100, old + cfg["regen_rate"])
                        if self.pet["stamina"] != old:
                            results["stamina"] = (old, self.pet["stamina"])
                else:
                    if tick % cfg["tick_mod"] == 0:
                        old = self.pet[stat]
                        decay = int(cfg["decay_rate"] * sick_mult)
                        self.pet[stat] = max(0, old - decay)
                        if self.pet[stat] != old:
                            results[stat] = (old, self.pet[stat])

            # Health meta-decay
            critical = sum(1 for s in ["hunger", "cleanliness", "mood"]
                          if self.pet[s] < 20)
            if critical >= 2:
                old_h = self.pet["health"]
                self.pet["health"] = max(0, old_h - HEALTH_DECAY_RATE)
                if self.pet["health"] != old_h:
                    results["health"] = (old_h, self.pet["health"])

            from config import now_str
            self.pet["last_decay_at"] = now_str()
            self._save()
            return results

    def add_xp(self, amount):
        """增加经验值，检查升级。返回 new_stage 或 None。"""
        from config import GROWTH_STAGES
        with self._lock:
            if self.pet is None:
                return None
            self.pet["xp"] = self.pet.get("xp", 0) + amount
            old_level = self.pet.get("level", 1)
            for threshold, stage_id, stage_name in GROWTH_STAGES:
                if self.pet["xp"] >= threshold:
                    new_level = GROWTH_STAGES.index((threshold, stage_id, stage_name)) + 1
                    if new_level > old_level:
                        self.pet["level"] = new_level
                        self.pet["stage"] = stage_id
                        self._save()
                        return stage_id
            self._save()
            return None

    def get_species_id(self):
        """返回当前宠物的品种 ID，无宠物返回 None。"""
        if self.pet is None:
            return None
        return self.pet.get("species", "penguin")

    def get_pet_name(self):
        """返回宠物名字，未命名返回品种名。"""
        if self.pet is None:
            return "宠物"
        name = self.pet.get("name")
        if name:
            return name
        from species import get_species
        spec = get_species(self.get_species_id())
        return spec["name"] if spec else "宠物"

    def sleep_remaining_min(self):
        """返回剩余睡眠分钟数。"""
        if not self.pet or not self.pet.get("sleep_until"):
            return 0
        from datetime import datetime
        from config import now, TZ
        wake_str = self.pet["sleep_until"]
        wake_time = datetime.fromisoformat(wake_str)
        if wake_time.tzinfo is None:
            wake_time = wake_time.replace(tzinfo=TZ)
        remaining = (wake_time - now()).total_seconds() / 60
        return max(0, int(remaining))

    def explore_remaining_min(self):
        """返回剩余探险分钟数。"""
        if not self.pet or not self.pet.get("explore_until"):
            return 0
        from datetime import datetime
        from config import now, TZ
        until_str = self.pet["explore_until"]
        return_time = datetime.fromisoformat(until_str)
        if return_time.tzinfo is None:
            return_time = return_time.replace(tzinfo=TZ)
        remaining = (return_time - now()).total_seconds() / 60
        return max(0, int(remaining))

    # --- 成就系统（从 core.py PetStore 迁移） ---

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
        """解锁成就，返回成就信息 dict 或 None（已解锁）。"""
        from core import ACHIEVEMENTS
        achs = self._get_achievements()
        if ach_id in achs:
            return None
        if ach_id not in ACHIEVEMENTS:
            return None
        from config import now_str
        achs[ach_id] = now_str()
        ach = ACHIEVEMENTS[ach_id]
        self.pet["xp"] = self.pet.get("xp", 0) + ach["xp"]
        self.history.append({"type": "achievement", "detail": {"id": ach_id, "name": ach["name"]}, "time": now_str()})
        return ach

    def record_action(self, action):
        """记录操作统计+检查成就，返回新解锁的成就列表。"""
        from config import now_str, today_str, now, parse_date
        from core import ACHIEVEMENTS
        with self._lock:
            stats = self._get_stats()
            unlocked = []

            today = today_str()
            if stats.get("last_active_date") != today:
                if stats.get("last_active_date"):
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

            active_dates = stats.setdefault("active_dates", [])
            if today not in active_dates:
                active_dates.append(today)

            stats["daily_messages"] = stats.get("daily_messages", 0) + 1

            count_map = {
                "feed": "total_feeds", "bathe": "total_baths", "play": "total_plays",
                "sleep": "total_sleeps", "heal": "total_heals", "explore": "total_explores",
            }
            if action in count_map:
                stats[count_map[action]] = stats.get(count_map[action], 0) + 1

            first_map = {
                "feed": "first_feed", "bathe": "first_bathe", "play": "first_play",
                "sleep": "first_sleep", "heal": "first_heal", "explore": "first_explore",
            }
            if action in first_map:
                ach = self._unlock(first_map[action])
                if ach:
                    unlocked.append(ach)

            if stats.get("total_feeds", 0) >= 50:
                ach = self._unlock("feed_50")
                if ach: unlocked.append(ach)
            if stats.get("total_explores", 0) >= 10:
                ach = self._unlock("explore_10")
                if ach: unlocked.append(ach)

            if stats.get("consecutive_days", 0) >= 3:
                ach = self._unlock("streak_3")
                if ach: unlocked.append(ach)
            if stats.get("consecutive_days", 0) >= 7:
                ach = self._unlock("streak_7")
                if ach: unlocked.append(ach)

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

            if action == "explore" and self.pet.get("explore_location"):
                locs = stats.setdefault("explore_locations", [])
                loc = self.pet["explore_location"]
                if loc not in locs:
                    locs.append(loc)
                if len(locs) >= 5:
                    ach = self._unlock("explore_5loc")
                    if ach: unlocked.append(ach)

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
        """健康恢复成就（治疗后调用）。"""
        if self.pet.get("health", 0) > 80:
            for h in reversed(self.history[-20:]):
                if h.get("type") == "heal" and h.get("detail", {}).get("old", 100) < 10:
                    return self._unlock("revive")
        return None

    def format_achievements(self):
        """格式化成就列表。"""
        from core import ACHIEVEMENTS
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
        total = len(ACHIEVEMENTS)
        done = len(achs)
        lines.append(f"\n进度：{done}/{total}")
        return "\n".join(lines)

    # --- 日记系统 ---

    def get_today_events(self):
        """提取今天的事件摘要。"""
        from config import today_str
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
        summary["chats"] = len(self.chat_history)
        return summary

    def add_diary_entry(self, date_str, content):
        """添加日记条目。"""
        self.diary.append({"date": date_str, "content": content})
        if len(self.diary) > 30:
            self.diary = self.diary[-30:]
        self._save()

    def format_diary(self, days=7):
        """格式化最近N天日记。"""
        if not self.diary:
            return "日记本还是空的呢~ 明天就开始写日记！"
        recent = self.diary[-days:]
        lines = ["\U0001f4d6 宠物日记\n"]
        for entry in reversed(recent):
            lines.append(f"\u2500\u2500 {entry['date']} \u2500\u2500")
            lines.append(entry["content"])
            lines.append("")
        return "\n".join(lines)

    def format_collection(self):
        """格式化收藏品列表。"""
        from config import SOUVENIRS
        if not self.collection:
            return "\U0001f392 背包空空的~ 去探险收集纪念品吧！"
        total_possible = sum(len(v) for v in SOUVENIRS.values())
        lines = [f"\U0001f392 收藏品 ({len(self.collection)}/{total_possible})\n"]
        for item in self.collection:
            lines.append(f"  \u2728 {item}")
        return "\n".join(lines)


class PetRegistry:
    """全局注册表：管理所有用户的 UserPetStore 实例。

    启动时扫描 data_dir 下已有的用户目录（有 pet.json 的），懒加载实例。
    线程安全。
    """

    def __init__(self, data_dir):
        self.data_dir = data_dir
        self._stores = {}
        self._lock = threading.RLock()
        os.makedirs(data_dir, exist_ok=True)
        self._scan_existing()

    def _scan_existing(self):
        """扫描已有用户目录，预加载 store 实例。"""
        if not os.path.isdir(self.data_dir):
            return
        for name in os.listdir(self.data_dir):
            user_dir = os.path.join(self.data_dir, name)
            pet_file = os.path.join(user_dir, "pet.json")
            if os.path.isdir(user_dir) and os.path.exists(pet_file):
                self._stores[name] = UserPetStore(name, self.data_dir)

    def get_or_create(self, user_id):
        """获取或创建用户的 store 实例。"""
        with self._lock:
            if user_id not in self._stores:
                self._stores[user_id] = UserPetStore(user_id, self.data_dir)
            return self._stores[user_id]

    def all_stores(self):
        """返回所有已激活的 store 实例列表。"""
        with self._lock:
            return list(self._stores.values())

    def all_active_stores(self):
        """返回所有有宠物的 store 实例。"""
        with self._lock:
            return [s for s in self._stores.values() if s.pet is not None]
