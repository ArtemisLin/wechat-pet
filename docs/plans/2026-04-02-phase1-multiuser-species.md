# Phase 1: 多用户基础 + 品种数据模型 — 施工计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 N 个用户各自领养一只随机品种的宠物，所有 V1 功能按用户隔离正常工作。

**Architecture:** 从单文件 PetStore 单例重构为目录制多用户存储（`data/{user_id}/pet.json`）。引入 `PetRegistry` 注册表管理所有用户实例。品种作为一等概念，影响 AI system prompt 和素材路径。

**Tech Stack:** Python 3.13, APScheduler, threading.RLock, json, pathlib

**设计文档:** `017Pet/docs/2026-04-02-pet-v2-design.md`（完整 V2 需求，本 Phase 只实现多用户 + 品种基础）

---

## 当前代码架构（V1 快速参考）

```
017Pet/pet/
├── config.py    — 常量、时区工具、属性配置（113 行）
├── core.py      — PetStore 类 + MessageHandler 类（1325 行）
├── ai.py        — AI 对话：system prompt 构建 + API 调用（166 行）
├── ilink.py     — 微信 iLink 通信层 + CLI 入口（421 行）
├── scheduler.py — APScheduler 定时任务（471 行）
├── image.py     — 图片加密 + CDN 上传（223 行）
├── pet_data.json       — 单用户宠物数据（运行时生成）
└── ilink_state.json    — iLink 登录态（运行时生成）
```

**关键单用户假设（必须改的地方）：**
- `config.py:9` — `PET_DATA_FILE` 指向单一 json 文件
- `core.py:964-965` — `if owner_id and owner_id != user_id: return "我已经有主人啦~"` 阻止多用户
- `core.py:54-63` — `PetStore.__init__` 加载单一数据文件
- `ai.py:87` — system prompt 硬编码"小企鹅宠物（Penguin）"
- `ilink.py:30` — `ASSETS_DIR` 硬编码 `assets/penguin`
- `scheduler.py` — 所有 job 操作单一 `pet_store` 实例

**数据 Schema（当前 v3）：** 见 `core.py:17-45`，owner 字段只存一个 user_id。

---

## 文件结构规划

### 新建文件
| 文件 | 职责 |
|------|------|
| `pet/species.py` | 6 个品种定义：名称、描述、性格 baseline、语言风格提示词 |
| `pet/store.py` | 多用户存储层：`UserPetStore`（per-user）+ `PetRegistry`（全局注册表） |
| `tests/test_store.py` | 存储层单元测试 |
| `tests/test_species.py` | 品种配置验证测试 |
| `tests/test_core.py` | 核心逻辑集成测试 |

### 修改文件
| 文件 | 变更概要 |
|------|----------|
| `pet/config.py` | 新增 `DATA_DIR`、`SCHEMA_VERSION=4`；移除 `PET_DATA_FILE` |
| `pet/core.py` | `PetStore` 接受外部 data_file 参数；`MessageHandler` 接受 registry；删除单用户拦截；pet 数据增加 `species` 字段 |
| `pet/ai.py` | `_build_system_prompt()` 接受 species 参数，动态生成品种特征描述 |
| `pet/ilink.py` | `ASSETS_DIR` 改为动态解析（按品种）；`start()` 创建 registry 而非单一 store |
| `pet/scheduler.py` | 所有 job 函数改为接受 registry，遍历所有用户 |

---

## Task 1: 测试基础设施

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `requirements-dev.txt`

- [ ] **Step 1: 创建测试目录和依赖**

```bash
cd c:/Users/Aoc/OneDrive/ClaudeCodeP/017Pet
mkdir -p tests
```

Write `requirements-dev.txt`:
```
pytest
```

Write `tests/__init__.py`:
```python
# empty
```

Write `tests/conftest.py`:
```python
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'pet'))
```

- [ ] **Step 2: 验证 pytest 能跑**

```bash
cd c:/Users/Aoc/OneDrive/ClaudeCodeP/017Pet
py -m pytest tests/ -v
```

Expected: 0 tests collected, no errors.

- [ ] **Step 3: Commit**

```bash
git add tests/ requirements-dev.txt
git commit -m "chore: add test infrastructure for Phase 1"
```

---

## Task 2: 创建 species.py — 品种定义

**Files:**
- Create: `pet/species.py`
- Create: `tests/test_species.py`

- [ ] **Step 1: 写 species 测试**

Write `tests/test_species.py`:
```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'pet'))

from species import SPECIES, get_species, ALL_SPECIES_IDS


def test_six_species_defined():
    assert len(SPECIES) == 6


def test_all_species_have_required_fields():
    required = {"name", "emoji", "description", "personality_hint", "baseline_traits"}
    trait_keys = {"extrovert", "brave", "greedy", "curious", "blunt"}
    for sid, spec in SPECIES.items():
        assert required.issubset(spec.keys()), f"{sid} missing fields"
        assert trait_keys == set(spec["baseline_traits"].keys()), f"{sid} bad traits"
        for v in spec["baseline_traits"].values():
            assert 0.1 <= v <= 0.9, f"{sid} trait out of range"


def test_get_species_returns_copy():
    s = get_species("penguin")
    assert s is not None
    s["name"] = "hacked"
    assert get_species("penguin")["name"] != "hacked"


def test_get_species_unknown():
    assert get_species("unicorn") is None


def test_all_species_ids():
    assert len(ALL_SPECIES_IDS) == 6
    assert "penguin" in ALL_SPECIES_IDS
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd c:/Users/Aoc/OneDrive/ClaudeCodeP/017Pet
py -m pytest tests/test_species.py -v
```

Expected: FAIL（species 模块不存在）

- [ ] **Step 3: 实现 species.py**

Write `pet/species.py`:
```python
"""品种定义：6 种宠物的基础配置。

每个品种包含：
- name: 中文名
- emoji: 展示用 emoji
- description: 一句话描述
- personality_hint: 注入 AI system prompt 的语言风格提示
- baseline_traits: 5 维性格基准值（0.0-1.0）
  - extrovert: 外向 ↔ 内向
  - brave: 勇敢 ↔ 谨慎
  - greedy: 嘴馋 ↔ 克制
  - curious: 好奇 ↔ 安定
  - blunt: 直球 ↔ 委婉
"""

import copy
import random

SPECIES = {
    "penguin": {
        "name": "小企鹅",
        "emoji": "🐧",
        "description": "圆滚滚的小企鹅，走路摇摇晃晃，特别爱吃鱼",
        "personality_hint": "说话简短可爱，喜欢用叠词，偶尔发出'噗'的声音",
        "baseline_traits": {
            "extrovert": 0.5,
            "brave": 0.4,
            "greedy": 0.7,
            "curious": 0.5,
            "blunt": 0.6,
        },
    },
    "dinosaur": {
        "name": "小恐龙",
        "emoji": "🦕",
        "description": "迷你小恐龙，看起来凶但其实胆子很小",
        "personality_hint": "偶尔会装凶'吼~'但马上就怂了，喜欢用感叹号",
        "baseline_traits": {
            "extrovert": 0.6,
            "brave": 0.3,
            "greedy": 0.6,
            "curious": 0.7,
            "blunt": 0.7,
        },
    },
    "fox": {
        "name": "小狐狸",
        "emoji": "🦊",
        "description": "毛茸茸的小狐狸，聪明又有点傲娇",
        "personality_hint": "说话带点小傲娇，嘴上说不要身体很诚实，偶尔用'哼'",
        "baseline_traits": {
            "extrovert": 0.4,
            "brave": 0.5,
            "greedy": 0.5,
            "curious": 0.6,
            "blunt": 0.3,
        },
    },
    "rabbit": {
        "name": "小兔子",
        "emoji": "🐰",
        "description": "软乎乎的小兔子，黏人又温柔",
        "personality_hint": "说话温柔软糯，喜欢撒娇，经常用'嘛~'结尾",
        "baseline_traits": {
            "extrovert": 0.6,
            "brave": 0.3,
            "greedy": 0.4,
            "curious": 0.4,
            "blunt": 0.5,
        },
    },
    "owl": {
        "name": "小猫头鹰",
        "emoji": "🦉",
        "description": "睿智的小猫头鹰，安静但观察力超强",
        "personality_hint": "说话慢条斯理有哲理感，偶尔冒出奇怪的冷知识，喜欢用'咕'",
        "baseline_traits": {
            "extrovert": 0.2,
            "brave": 0.5,
            "greedy": 0.3,
            "curious": 0.8,
            "blunt": 0.4,
        },
    },
    "dragon": {
        "name": "小龙",
        "emoji": "🐉",
        "description": "袖珍小龙，会喷小火苗，自认为是世界的守护者",
        "personality_hint": "说话中二但又很认真，偶尔自称'本龙'，喜欢用'哈'表示得意",
        "baseline_traits": {
            "extrovert": 0.7,
            "brave": 0.8,
            "greedy": 0.5,
            "curious": 0.6,
            "blunt": 0.8,
        },
    },
}

ALL_SPECIES_IDS = list(SPECIES.keys())


def get_species(species_id):
    """返回品种配置的深拷贝，不存在返回 None。"""
    spec = SPECIES.get(species_id)
    return copy.deepcopy(spec) if spec else None


def random_species():
    """随机返回一个品种 ID。"""
    return random.choice(ALL_SPECIES_IDS)
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd c:/Users/Aoc/OneDrive/ClaudeCodeP/017Pet
py -m pytest tests/test_species.py -v
```

Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add pet/species.py tests/test_species.py
git commit -m "feat: add species definitions for 6 pet types"
```

---

## Task 3: 创建 store.py — 多用户存储层

**Files:**
- Create: `pet/store.py`
- Create: `tests/test_store.py`

这是 Phase 1 最核心的新文件。它替代 `core.py` 中 `PetStore` 的数据持久化职责。

- [ ] **Step 1: 写 store 测试**

Write `tests/test_store.py`:
```python
import sys, os, json, tempfile, shutil
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'pet'))

from store import UserPetStore, PetRegistry

TEST_USER_A = "user_a@test"
TEST_USER_B = "user_b@test"


class TestUserPetStore:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.store = UserPetStore(TEST_USER_A, self.tmpdir)

    def teardown_method(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_creates_user_directory(self):
        user_dir = os.path.join(self.tmpdir, TEST_USER_A)
        assert os.path.isdir(user_dir)

    def test_initial_state_is_empty(self):
        assert self.store.pet is None
        assert self.store.owner == {}

    def test_create_egg_and_save(self):
        ok = self.store.create_egg(TEST_USER_A, "TestOwner", "penguin")
        assert ok is True
        assert self.store.pet is not None
        assert self.store.pet["species"] == "penguin"
        assert self.store.pet["stage"] == "egg"
        # Verify file written
        data_file = os.path.join(self.tmpdir, TEST_USER_A, "pet.json")
        assert os.path.exists(data_file)
        with open(data_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["schema_version"] == 4
        assert data["pet"]["species"] == "penguin"

    def test_hatch_sets_name(self):
        self.store.create_egg(TEST_USER_A, "TestOwner", "fox")
        ok = self.store.hatch("小七")
        assert ok is True
        assert self.store.pet["name"] == "小七"
        assert self.store.pet["stage"] == "baby"
        assert self.store.pet["species"] == "fox"

    def test_feed_increases_hunger(self):
        self.store.create_egg(TEST_USER_A, "TestOwner", "penguin")
        self.store.hatch("谷谷")
        self.store.pet["hunger"] = 50
        result = self.store.feed()
        assert result is not None
        old, new = result
        assert new > old

    def test_atomic_save(self):
        """验证 save 是原子操作（先写 tmp 再 replace）"""
        self.store.create_egg(TEST_USER_A, "TestOwner", "penguin")
        data_file = os.path.join(self.tmpdir, TEST_USER_A, "pet.json")
        assert os.path.exists(data_file)
        # tmp 文件不应残留
        tmp_file = data_file + ".tmp"
        assert not os.path.exists(tmp_file)


class TestPetRegistry:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.registry = PetRegistry(self.tmpdir)

    def teardown_method(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_get_or_create_returns_store(self):
        store = self.registry.get_or_create(TEST_USER_A)
        assert isinstance(store, UserPetStore)

    def test_same_user_returns_same_instance(self):
        s1 = self.registry.get_or_create(TEST_USER_A)
        s2 = self.registry.get_or_create(TEST_USER_A)
        assert s1 is s2

    def test_different_users_get_different_stores(self):
        sa = self.registry.get_or_create(TEST_USER_A)
        sb = self.registry.get_or_create(TEST_USER_B)
        assert sa is not sb

    def test_all_stores_returns_active(self):
        self.registry.get_or_create(TEST_USER_A)
        self.registry.get_or_create(TEST_USER_B)
        stores = self.registry.all_stores()
        assert len(stores) == 2

    def test_loads_existing_users_on_init(self):
        # Create a user via store
        s = self.registry.get_or_create(TEST_USER_A)
        s.create_egg(TEST_USER_A, "Owner", "penguin")
        # New registry instance should discover the existing user
        registry2 = PetRegistry(self.tmpdir)
        stores = registry2.all_stores()
        assert len(stores) >= 1
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd c:/Users/Aoc/OneDrive/ClaudeCodeP/017Pet
py -m pytest tests/test_store.py -v
```

Expected: FAIL（store 模块不存在）

- [ ] **Step 3: 实现 store.py**

Write `pet/store.py`:
```python
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
        """创建宠物蛋。species 是品种 ID（如 'penguin'、'fox'）。

        与 V1 区别：新增 species 参数。
        """
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
        """喂食。返回 (old, new) 或 None。

        逻辑与 V1 core.py:178-191 完全一致。
        """
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
        """开始探险。返回 (location, until_iso, duration_min) 或错误字符串。

        逻辑与 V1 core.py:295-319 一致。
        """
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
            # 导入探险地点
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
        """结束探险。返回 (location, souvenir_or_None) 或 None。

        逻辑与 V1 core.py:321-339 一致。
        """
        import random
        from config import SOUVENIRS, now_str
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
        """检查是否在探险。如果已过 explore_until 返回 False（由 scheduler 处理结算）。"""
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
        """属性衰减 tick。返回 {stat: (old, new)}。

        逻辑与 V1 core.py:397-425 一致。
        """
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
                    # Stamina regenerates
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
            # Check level up
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
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd c:/Users/Aoc/OneDrive/ClaudeCodeP/017Pet
py -m pytest tests/test_store.py -v
```

Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
git add pet/store.py tests/test_store.py
git commit -m "feat: add multi-user storage layer (UserPetStore + PetRegistry)"
```

---

## Task 4: 修改 config.py — 新增多用户路径配置

**Files:**
- Modify: `pet/config.py`

- [ ] **Step 1: 在 config.py 中新增 DATA_DIR 和 SCHEMA_VERSION**

在 `config.py` 的 `BASE_DIR` 定义之后（约第 8 行），添加：

```python
DATA_DIR = BASE_DIR / "data"
```

删除或注释掉 `PET_DATA_FILE` 行（约第 9 行）：
```python
# PET_DATA_FILE = str(BASE_DIR / "pet_data.json")  # V1 遗留，已迁移到 data/{user_id}/pet.json
```

**注意**：不要删除 `ILINK_STATE_FILE`，它仍然是全局的（iLink 登录态与用户无关）。

- [ ] **Step 2: 验证不影响现有 import**

```bash
cd c:/Users/Aoc/OneDrive/ClaudeCodeP/017Pet
py -c "import sys; sys.path.insert(0,'pet'); from config import DATA_DIR, BASE_DIR; print('DATA_DIR:', DATA_DIR); print('OK')"
```

Expected: 打印 DATA_DIR 路径和 OK

- [ ] **Step 3: Commit**

```bash
git add pet/config.py
git commit -m "refactor: add DATA_DIR for multi-user storage, deprecate PET_DATA_FILE"
```

---

## Task 5: 重构 core.py — 移除单用户限制

**Files:**
- Modify: `pet/core.py`

这是最大的改动。核心原则：**保留 core.py 中的业务逻辑（消息路由、回复模板、成就检查），但让它使用 store.py 提供的 UserPetStore 而非内置的 PetStore。**

策略：
1. `PetStore` 类保留但标记为 deprecated，内部改用 `UserPetStore` 的接口
2. `MessageHandler` 改为接受 `PetRegistry`，根据 user_id 获取对应 store
3. 删除第 964-965 行的单用户拦截
4. 孵化流程增加随机品种分配

- [ ] **Step 1: 修改 MessageHandler 构造函数**

找到 `class MessageHandler`（约第 943 行），将构造函数从：

```python
def __init__(self, store=None):
    self.store = store or PetStore()
    self._user_state = {}
```

改为：

```python
def __init__(self, registry=None):
    self._registry = registry
    self._user_state = {}
```

- [ ] **Step 2: 修改 handle_message 入口——按 user_id 获取 store**

找到 `handle_message` 方法（约第 959 行），在方法最开头添加获取 per-user store 的逻辑：

```python
def handle_message(self, user_id, text, is_voice=False):
    store = self._registry.get_or_create(user_id)
    # ... 后续代码中所有 self.store 替换为 store
```

在整个 `handle_message` 方法内，将所有 `self.store` 替换为 `store`。这包括：
- `self.store.pet` → `store.pet`
- `self.store.owner` → `store.owner`
- `self.store.feed()` → `store.feed()`
- `self.store.bathe()` → `store.bathe()`
- `self.store.play()` → `store.play()`
- `self.store.sleep()` → `store.sleep()`
- `self.store.heal()` → `store.heal()`
- `self.store.start_explore()` → `store.start_explore()`
- `self.store.is_sleeping()` → `store.is_sleeping()`
- `self.store.is_exploring()` → `store.is_exploring()`
- `self.store.format_status()` → `store.format_status()` (如果有)
- `self.store.hatch()` → `store.hatch()`
- `self.store.create_egg()` → `store.create_egg()`
- 等所有 self.store 引用

**重要**：`self._user_state` 需要按 user_id 隔离，当前已经是 dict 以 user_id 为 key，所以不需要改。

- [ ] **Step 3: 删除单用户拦截逻辑**

找到约第 964-965 行（原始版本）的代码：

```python
if self.store.owner.get("user_id") and self.store.owner["user_id"] != user_id:
    return "我已经有主人啦~ 一只小企鹅只能有一个主人哦！"
```

**删除这两行**。多用户模式下每个 user_id 有自己的 store，不需要这个检查。

- [ ] **Step 4: 修改孵化流程——增加随机品种**

找到创建宠物蛋的代码（在 handle_message 中搜索 `create_egg` 调用），将：

```python
store.create_egg(user_id, text)
```

改为：

```python
from species import random_species
species_id = random_species()
store.create_egg(user_id, text, species_id)
```

同时修改孵化成功后的回复文案，将硬编码的"小企鹅"替换为动态品种名：

```python
from species import get_species
spec = get_species(store.get_species_id())
species_name = spec["name"] if spec else "小宠物"
species_emoji = spec["emoji"] if spec else "🐾"
```

在孵化完成回复中使用 `species_name` 和 `species_emoji` 替换硬编码的"🐧"和"小企鹅"。

- [ ] **Step 5: 修改 format_status 和回复模板中的硬编码品种名**

在 core.py 中搜索所有"小企鹅"字符串，替换为 `store.get_pet_name()` 或动态品种名。关键位置：

- `format_status()` 方法（约第 678-740 行）：状态展示标题
- `_feed_reply()` 等回复函数（约第 776-841 行）：宠物名参数已经传入，确认使用的是 `pet_name` 而非硬编码
- 探险、睡觉等回复模板

大部分回复函数已经接受 `pet_name` 参数，主要需要确认调用处传入了正确的名字。

- [ ] **Step 6: 保留旧的 PetStore 类但标记 deprecated**

在 `PetStore` 类定义处添加注释：

```python
class PetStore:
    """V1 遗留类，仅用于数据迁移。新代码请使用 store.py 的 UserPetStore。
    
    DEPRECATED: 将在 Phase 1 完成后移除。
    """
```

不要删除它，因为迁移脚本可能需要用它读取旧数据。

- [ ] **Step 7: 修改 core.py 的 record_action 和成就系统**

`record_action` 方法（约第 524-628 行）直接操作 `self` 上的 `pet`, `history`, `stats` 等。这些方法需要改为操作传入的 `store` 实例。

有两种策略：
- **策略 A**：将 `record_action` 移到 `UserPetStore` 类中
- **策略 B**：保留在 `MessageHandler` 中，但改为接受 `store` 参数

**推荐策略 B**（改动最小）：

将 `record_action(self, action)` 改为 `record_action(self, store, action)`。内部所有 `self.pet` → `store.pet`，`self.history` → `store.history`，`self.stats` → `store.pet["stats"]`，最后调用 `store._save()`。

同样处理 `format_status`, `format_diary`, `format_achievements`, `format_collection` 等方法——添加 `store` 参数或改为 `store` 的方法。

**注意**：这是最繁琐的部分。搜索 core.py 中所有 `self.store.` 和 `self.pet` 引用，确保每个都通过正确的 store 实例访问。

- [ ] **Step 8: 验证修改后能导入不报错**

```bash
cd c:/Users/Aoc/OneDrive/ClaudeCodeP/017Pet
py -c "import sys; sys.path.insert(0,'pet'); from core import MessageHandler; print('OK')"
```

Expected: OK（无 import 错误）

- [ ] **Step 9: Commit**

```bash
git add pet/core.py
git commit -m "refactor: make MessageHandler multi-user via PetRegistry"
```

---

## Task 6: 重构 ai.py — 品种感知的 system prompt

**Files:**
- Modify: `pet/ai.py`

- [ ] **Step 1: 修改 _build_system_prompt 接受 species 参数**

找到 `_build_system_prompt` 函数（约第 38 行），将签名从：

```python
def _build_system_prompt(pet_context):
```

改为：

```python
def _build_system_prompt(pet_context, species_id="penguin"):
```

在函数开头添加品种信息加载：

```python
from species import get_species
spec = get_species(species_id) or get_species("penguin")
species_name = spec["name"]
personality_hint = spec["personality_hint"]
```

- [ ] **Step 2: 替换硬编码的品种和性格描述**

找到约第 87 行的硬编码：

```python
你是一只小企鹅宠物（Penguin）
```

替换为：

```python
你是一只{species_name}宠物
```

找到硬编码的性格描述（约第 88-89 行）：

```python
性格：贪吃、偶尔撒娇、好奇心旺盛、说话简短可爱
```

替换为：

```python
说话风格：{personality_hint}
```

- [ ] **Step 3: 修改 parse_message 传递 species_id**

找到 `parse_message` 函数（约第 112 行），将签名从：

```python
def parse_message(text, pet_context, history=None):
```

改为：

```python
def parse_message(text, pet_context, history=None, species_id="penguin"):
```

在函数内部调用 `_build_system_prompt` 时传入 `species_id`：

```python
system_prompt = _build_system_prompt(pet_context, species_id=species_id)
```

- [ ] **Step 4: 更新 core.py 中对 parse_message 的调用**

在 core.py 的 `handle_message` 中，找到调用 `ai.parse_message()` 的位置，添加 `species_id` 参数：

```python
species_id = store.get_species_id()
result = ai.parse_message(text, pet_context, history=store.chat_history, species_id=species_id)
```

- [ ] **Step 5: 验证**

```bash
cd c:/Users/Aoc/OneDrive/ClaudeCodeP/017Pet
py -c "import sys; sys.path.insert(0,'pet'); from ai import _build_system_prompt; p = _build_system_prompt({'name':'小七','hunger':80,'cleanliness':90,'mood':85,'stamina':70,'health':100,'is_exploring':False,'is_sleeping':False,'days_together':5,'owner_display_name':'谷雨'}, species_id='fox'); print(p[:200])"
```

Expected: 打印包含"小狐狸"和"小傲娇"相关描述的 prompt 片段

- [ ] **Step 6: Commit**

```bash
git add pet/ai.py pet/core.py
git commit -m "feat: species-aware AI system prompt"
```

---

## Task 7: 重构 ilink.py — 多用户消息路由

**Files:**
- Modify: `pet/ilink.py`

- [ ] **Step 1: 修改 ASSETS_DIR 为动态解析**

找到第 30 行：

```python
ASSETS_DIR = Path(__file__).parent.parent / "assets" / "penguin"
```

改为：

```python
ASSETS_BASE = Path(__file__).parent.parent / "assets"

def _get_assets_dir(species_id="penguin"):
    """按品种返回素材目录。如果品种目录不存在，fallback 到 penguin。"""
    species_dir = ASSETS_BASE / species_id
    if species_dir.is_dir():
        return species_dir
    return ASSETS_BASE / "penguin"
```

- [ ] **Step 2: 修改 _resolve_image_path 接受 species_id**

将 `_resolve_image_path` 函数（约第 187 行）从：

```python
def _resolve_image_path(image_key):
```

改为：

```python
def _resolve_image_path(image_key, species_id="penguin"):
    assets_dir = _get_assets_dir(species_id)
    # ... 后续路径解析使用 assets_dir 而非全局 ASSETS_DIR
```

- [ ] **Step 3: 修改 start() 函数——创建 registry 而非单一 store**

找到 `start()` 函数（约第 313 行），当前代码大致是：

```python
def start():
    state = load_state()
    from core import PetStore, MessageHandler
    pet_store = PetStore()
    handler = MessageHandler(pet_store)
    ...
```

改为：

```python
def start():
    state = load_state()
    from config import DATA_DIR
    from store import PetRegistry
    from core import MessageHandler

    registry = PetRegistry(str(DATA_DIR))
    handler = MessageHandler(registry=registry)
    ...
```

- [ ] **Step 4: 修改 on_message 回调——传递 species_id 给图片发送**

在 `start()` 内部的 `on_message` 回调中，发送图片时需要知道用户宠物的品种：

```python
def on_message(user_id, text, is_voice=False):
    reply = handler.handle_message(user_id, text, is_voice)
    if isinstance(reply, tuple):
        text_reply, image_key = reply
        send_message(state, user_id, ctx_token, text_reply)
        # 获取用户宠物的品种
        user_store = registry.get_or_create(user_id)
        species_id = user_store.get_species_id() or "penguin"
        _send_image_by_key(state, user_id, ctx_token, image_key, species_id)
    else:
        send_message(state, user_id, ctx_token, reply)
```

修改 `_send_image_by_key` 接受 `species_id` 参数：

```python
def _send_image_by_key(state, user_id, context_token, image_key, species_id="penguin"):
    path = _resolve_image_path(image_key, species_id)
    if path:
        from image import send_image_file
        send_image_file(state, user_id, context_token, path)
```

- [ ] **Step 5: 修改 scheduler 创建——传递 registry**

在 `start()` 中，scheduler 的创建从传递单一 `pet_store` 改为传递 `registry`：

```python
from scheduler import create_scheduler
sched = create_scheduler(registry, send_fn, send_image_fn)
```

- [ ] **Step 6: 验证 ilink.py 能导入**

```bash
cd c:/Users/Aoc/OneDrive/ClaudeCodeP/017Pet
py -c "import sys; sys.path.insert(0,'pet'); from ilink import _get_assets_dir; print(_get_assets_dir('penguin')); print(_get_assets_dir('fox')); print('OK')"
```

Expected: penguin 路径存在，fox fallback 到 penguin，打印 OK

- [ ] **Step 7: Commit**

```bash
git add pet/ilink.py
git commit -m "refactor: multi-user message routing with PetRegistry in ilink"
```

---

## Task 8: 重构 scheduler.py — 遍历所有用户

**Files:**
- Modify: `pet/scheduler.py`

- [ ] **Step 1: 修改 create_scheduler 签名**

找到 scheduler 的入口函数（约第 24 行的 `create_scheduler` 或类似），将参数从 `(pet_store, send_fn, send_image_fn)` 改为 `(registry, send_fn, send_image_fn)`。

- [ ] **Step 2: 修改 _tick_job——遍历所有用户**

找到 `_tick_job` 函数（约第 74 行），当前操作单一 `pet_store`。改为：

```python
def _tick_job(registry, send_fn, send_image_fn):
    for store in registry.all_active_stores():
        try:
            user_id = store.user_id
            # 睡眠检查
            if store.pet and store.pet.get("is_sleeping"):
                if not store.is_sleeping():
                    # 自动醒来
                    name = store.get_pet_name()
                    send_fn(user_id, f"{name}醒啦！伸了个大懒腰~")

            # 探险检查
            if store.pet and store.pet.get("is_exploring"):
                if not store.is_exploring():
                    result = store.finish_explore()
                    if result:
                        loc, souvenir = result
                        name = store.get_pet_name()
                        # 生成探险故事
                        story = _generate_explore_story(name, loc)
                        msg = f"🎒 {name}从{loc}回来啦！\n\n{story}"
                        if souvenir:
                            msg += f"\n\n✨ 还带回了纪念品：{souvenir}！"
                        send_fn(user_id, msg)

            # 属性衰减
            decayed = store.decay_all()
            if decayed:
                name = store.get_pet_name()
                for stat, (old, new) in decayed.items():
                    if stat in ALERT_INFO and new < STAT_CONFIG.get(stat, {}).get("alert_threshold", 20):
                        alert_msg, img_key = ALERT_INFO[stat]
                        send_fn(user_id, alert_msg.format(name=name))

        except Exception as e:
            print(f"[scheduler] tick error for {store.user_id}: {e}")
```

- [ ] **Step 3: 修改 _chitchat_job——per-user 闲聊状态**

当前 `_chitchat_state` 是全局的（只追踪一个用户）。改为 per-user：

将全局的 `_chitchat_state` 改为 dict of dicts：

```python
_chitchat_states = {}  # {user_id: {"sent_today": set(), "last_date": None, "last_interaction": None}}

def _get_chitchat_state(user_id):
    if user_id not in _chitchat_states:
        _chitchat_states[user_id] = {
            "sent_today": set(),
            "last_date": None,
            "last_interaction": None,
        }
    return _chitchat_states[user_id]
```

修改 `mark_user_interaction` 接受 user_id：

```python
def mark_user_interaction(user_id):
    with _chitchat_lock:
        state = _get_chitchat_state(user_id)
        state["last_interaction"] = now()
```

修改 `_chitchat_job` 遍历所有用户：

```python
def _chitchat_job(registry, send_fn, send_image_fn):
    for store in registry.all_active_stores():
        try:
            _do_chitchat_for_user(store, send_fn, send_image_fn)
        except Exception as e:
            print(f"[scheduler] chitchat error for {store.user_id}: {e}")
```

- [ ] **Step 4: 同样修改 _diary_job, _weekly_report_job, _auto_explore_job**

这些 job 也需要遍历所有用户。模式相同：

```python
def _diary_job(registry, send_fn):
    for store in registry.all_active_stores():
        try:
            name = store.get_pet_name()
            # ... 生成日记逻辑（与 V1 一致，只是操作 store 而非全局 pet_store）
        except Exception as e:
            print(f"[scheduler] diary error for {store.user_id}: {e}")
```

- [ ] **Step 5: 修改 _generate_explore_story 等 AI 函数——传入 species_id**

这些函数调用 `ai.parse_message`，需要传入 `species_id`。找到 `_generate_explore_story`、`_generate_diary`、`_generate_weekly_summary`、`_generate_chitchat`，添加 `species_id` 参数并传递给 AI。

- [ ] **Step 6: 验证 scheduler 能导入**

```bash
cd c:/Users/Aoc/OneDrive/ClaudeCodeP/017Pet
py -c "import sys; sys.path.insert(0,'pet'); from scheduler import create_scheduler; print('OK')"
```

Expected: OK

- [ ] **Step 7: Commit**

```bash
git add pet/scheduler.py
git commit -m "refactor: scheduler iterates all users via PetRegistry"
```

---

## Task 9: 数据迁移脚本

**Files:**
- Create: `pet/migrate_v1.py`

将旧的单文件 `pet_data.json` 迁移到新的目录结构。

- [ ] **Step 1: 写迁移脚本**

Write `pet/migrate_v1.py`:
```python
"""V1 → V2 数据迁移：将 pet_data.json 迁移到 data/{user_id}/pet.json。

用法：py migrate_v1.py
"""
import sys
import io
import json
import os
import shutil

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OLD_FILE = os.path.join(BASE_DIR, "pet_data.json")
DATA_DIR = os.path.join(BASE_DIR, "data")


def migrate():
    if not os.path.exists(OLD_FILE):
        print("没有找到旧的 pet_data.json，无需迁移。")
        return

    with open(OLD_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    owner = data.get("owner", {})
    user_id = owner.get("user_id")
    if not user_id:
        print("旧数据中没有 owner.user_id，无法迁移。")
        return

    # 创建用户目录
    user_dir = os.path.join(DATA_DIR, user_id)
    os.makedirs(user_dir, exist_ok=True)

    # 升级 schema
    pet = data.get("pet", {})
    if "species" not in pet:
        pet["species"] = "penguin"
    data["pet"] = pet
    data["schema_version"] = 4

    # 写入新位置
    new_file = os.path.join(user_dir, "pet.json")
    with open(new_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # 备份旧文件
    backup = OLD_FILE + ".migrated"
    shutil.move(OLD_FILE, backup)

    print(f"迁移完成！")
    print(f"  用户 ID: {user_id}")
    print(f"  品种: {pet.get('species', 'penguin')}")
    print(f"  新位置: {new_file}")
    print(f"  旧文件已备份为: {backup}")


if __name__ == "__main__":
    migrate()
```

- [ ] **Step 2: 测试迁移（如果有旧数据）**

```bash
cd c:/Users/Aoc/OneDrive/ClaudeCodeP/017Pet/pet
py migrate_v1.py
```

Expected: 如果 pet_data.json 存在，迁移成功并打印信息。

- [ ] **Step 3: Commit**

```bash
git add pet/migrate_v1.py
git commit -m "feat: add V1 to V2 data migration script"
```

---

## Task 10: 集成测试

**Files:**
- Create: `tests/test_integration.py`

- [ ] **Step 1: 写集成测试**

Write `tests/test_integration.py`:
```python
"""集成测试：验证多用户 + 多品种的完整流程。"""
import sys, os, tempfile, shutil
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'pet'))

# 设置环境变量避免 AI 调用
os.environ.setdefault("AI_API_KEY", "test")
os.environ.setdefault("AI_BASE_URL", "http://localhost:9999")
os.environ.setdefault("AI_MODEL", "test")

from store import PetRegistry


USER_A = "user_a@test"
USER_B = "user_b@test"


class TestMultiUserIntegration:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.registry = PetRegistry(self.tmpdir)

    def teardown_method(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_two_users_different_species(self):
        """两个用户各自领养不同品种的宠物"""
        store_a = self.registry.get_or_create(USER_A)
        store_b = self.registry.get_or_create(USER_B)

        store_a.create_egg(USER_A, "UserA", "fox")
        store_b.create_egg(USER_B, "UserB", "dragon")

        assert store_a.pet["species"] == "fox"
        assert store_b.pet["species"] == "dragon"

    def test_users_dont_interfere(self):
        """一个用户的操作不影响另一个"""
        store_a = self.registry.get_or_create(USER_A)
        store_b = self.registry.get_or_create(USER_B)

        store_a.create_egg(USER_A, "A", "penguin")
        store_a.hatch("谷谷A")
        store_a.pet["hunger"] = 30
        store_a.feed()

        store_b.create_egg(USER_B, "B", "owl")
        store_b.hatch("谷谷B")

        # B 的 hunger 应该还是 100（初始值）
        assert store_b.pet["hunger"] == 100
        # A 的 hunger 应该大于 30
        assert store_a.pet["hunger"] > 30

    def test_species_name_in_pet_name(self):
        """未命名时用品种名"""
        store = self.registry.get_or_create(USER_A)
        store.create_egg(USER_A, "A", "fox")
        # egg 阶段 name 是 None
        assert store.get_pet_name() == "小狐狸"

        store.hatch("小七")
        assert store.get_pet_name() == "小七"

    def test_registry_persistence(self):
        """注册表重启后能恢复用户"""
        store = self.registry.get_or_create(USER_A)
        store.create_egg(USER_A, "A", "dragon")
        store.hatch("大龙")

        # 模拟重启
        registry2 = PetRegistry(self.tmpdir)
        stores = registry2.all_active_stores()
        assert len(stores) == 1
        assert stores[0].pet["name"] == "大龙"
        assert stores[0].pet["species"] == "dragon"

    def test_full_lifecycle(self):
        """完整生命周期：创建 → 孵化 → 喂食 → 洗澡 → 玩耍 → 治疗"""
        store = self.registry.get_or_create(USER_A)
        store.create_egg(USER_A, "Owner", "rabbit")
        store.hatch("小白")

        # 喂食
        store.pet["hunger"] = 50
        result = store.feed()
        assert result is not None
        assert result[1] > 50

        # 洗澡
        store.pet["cleanliness"] = 40
        result = store.bathe()
        assert result is not None
        assert result[1] > 40

        # 玩耍
        result = store.play()
        assert result is not None
        assert result != "no_stamina"

        # 治疗
        store.pet["health"] = 60
        result = store.heal()
        assert result is not None
        assert result[1] > 60

    def test_decay_per_user(self):
        """每个用户的衰减独立"""
        sa = self.registry.get_or_create(USER_A)
        sb = self.registry.get_or_create(USER_B)
        sa.create_egg(USER_A, "A", "penguin")
        sa.hatch("AA")
        sb.create_egg(USER_B, "B", "fox")
        sb.hatch("BB")

        sa.pet["hunger"] = 80
        sb.pet["hunger"] = 80

        # A 衰减
        sa.decay_all()
        # B 不应该受影响（同一个 tick 但独立调用）
        # 注意：decay_all 有 tick_mod 控制，第一次 tick 可能不衰减 hunger
        # 这里只验证不会交叉影响
        assert sb.pet["hunger"] == 80  # B 没调用 decay_all
```

- [ ] **Step 2: 运行集成测试**

```bash
cd c:/Users/Aoc/OneDrive/ClaudeCodeP/017Pet
py -m pytest tests/test_integration.py -v
```

Expected: All tests pass

- [ ] **Step 3: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: add multi-user integration tests"
```

---

## Task 11: 端到端验证

- [ ] **Step 1: 运行迁移脚本（如果有旧数据）**

```bash
cd c:/Users/Aoc/OneDrive/ClaudeCodeP/017Pet/pet
py migrate_v1.py
```

- [ ] **Step 2: 运行全部测试**

```bash
cd c:/Users/Aoc/OneDrive/ClaudeCodeP/017Pet
py -m pytest tests/ -v
```

Expected: All tests pass

- [ ] **Step 3: 手动启动 bot 验证**

```bash
cd c:/Users/Aoc/OneDrive/ClaudeCodeP/017Pet/pet
py ilink.py start
```

用微信发消息测试：
1. 发"领养"→ 应该进入孵化流程
2. 给宠物起名字 → 应该看到品种名（不再是固定的"小企鹅"）
3. 发"喂食"→ 应该正常喂食
4. 发"看看"→ 应该看到状态展示（包含品种信息）
5. 发"探险"→ 应该正常开始探险

如果有第二个微信账号，用它也发"领养"，验证两个用户互不干扰。

- [ ] **Step 4: Commit 最终状态**

```bash
git add -A
git commit -m "feat: Phase 1 complete - multi-user support with 6 pet species"
```

---

## 已知风险与注意事项

1. **core.py 重构量大**：1325 行代码中约 60% 需要修改引用方式（self.store → store 参数）。建议用编辑器的全局替换功能，但每次替换后都要检查上下文。

2. **scheduler.py 全局状态**：`_chitchat_state` 从全局改为 per-user dict 时，要确保线程安全（已用 `_chitchat_lock`）。

3. **import 循环**：`store.py` import `config.py`，`config.py` 不能 import `store.py`。如果遇到循环 import，使用延迟 import（在函数内部 import）。

4. **旧数据兼容**：迁移脚本只处理标准格式的 pet_data.json。如果数据有异常，迁移脚本会跳过并提示。

5. **AI 调用不受影响**：本 Phase 不改变 AI 调用逻辑，只是给 system prompt 注入了品种信息。DeepSeek API 调用方式不变。

6. **图片素材**：目前只有 `assets/penguin/` 目录，其他品种会 fallback 到 penguin。这在 Phase 3（AI 生图）中解决。
