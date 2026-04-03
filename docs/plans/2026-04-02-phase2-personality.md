# Phase 2: 性格系统 — 施工计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 每只宠物有 5 个性格维度 + 独立亲密度。孵化包含 3 次塑形互动。性格随养育缓慢变化，AI 对话反映性格差异。

**Architecture:** 新建 `personality.py` 作为性格引擎，管理初始值计算、互动偏移、日衰减、区间检测。性格数据存入 pet.json 的 `traits` 和 `intimacy` 字段（schema v5）。

**Tech Stack:** Python 3.13, json, threading

**前置条件:** Phase 1 已完成（多用户 + 品种系统正常工作）

**设计文档:** `017Pet/docs/2026-04-02-pet-v2-design.md` — 模块一

---

## Phase 1 产出参考（本 Phase 依赖的文件）

```
pet/species.py    — 6 个品种定义，每个品种有 baseline_traits（5 维浮点数）
pet/store.py      — UserPetStore（per-user 数据）+ PetRegistry（全局注册表）
pet/core.py       — MessageHandler 使用 registry，handle_message(user_id, text) 路由
pet/ai.py         — _build_system_prompt(pet_context, species_id) 已支持品种
pet/config.py     — DATA_DIR, STAT_CONFIG 等常量
```

**pet.json schema v4 中 pet 字段结构（Phase 1 产出）：**
```json
{
  "name": "小七",
  "species": "fox",
  "stage": "baby",
  "hunger": 90, "cleanliness": 100, "mood": 96, "stamina": 91, "health": 100,
  "xp": 66, "level": 1,
  "is_sleeping": false, "is_exploring": false,
  "achievements": {}, "stats": {}
}
```

本 Phase 将在此基础上新增 `traits` 和 `intimacy` 字段，升级到 schema v5。

---

## 性格系统设计速览

### 双层架构
- **性格层（traits）**：5 个维度，每个 0.0-1.0，稳定底色 + 缓慢漂移
- **亲密度层（intimacy）**：单独 0.0-1.0，反映当前关系，短期波动

### 5 个维度
| Key | 低值含义 | 高值含义 |
|-----|----------|----------|
| extrovert | 内向：安静少话 | 外向：主动活泼 |
| brave | 谨慎：怕生犹豫 | 勇敢：不怕新事物 |
| greedy | 克制：对食物无感 | 嘴馋：总想吃 |
| curious | 安定：喜欢待原地 | 好奇：问东问西 |
| blunt | 委婉：拐弯抹角 | 直球：直接表达 |

### 初始值
```
final_trait = species_baseline + random_offset(±0.15) + hatching_offset
```

### 互动漂移
```
displayed_trait = species_baseline + learned_offset
```
- 每次喂食：greedy +0.005
- 每次探险：brave +0.005
- 每次玩耍：extrovert +0.005
- learned_offset 上限 ±0.25，每日上限 ±0.015
- 长期不强化回归 baseline（每天 -0.002）

### 亲密度
- 每次互动 +0.01（每日上限 +0.05）
- 24h 无互动 -0.03
- 影响称呼进化、行为表现

### 区间通知
- [0, 0.3] 低 / [0.3, 0.7] 中 / [0.7, 1.0] 高
- 只在跨区间时通知，自然语言，不暴露数值

---

## Task 1: 创建 personality.py — 性格引擎

**Files:**
- Create: `pet/personality.py`
- Create: `tests/test_personality.py`

- [ ] **Step 1: 写性格引擎测试**

Write `tests/test_personality.py`:
```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'pet'))

from personality import (
    compute_initial_traits,
    apply_interaction_offset,
    daily_decay_toward_baseline,
    get_trait_band,
    detect_band_crossings,
    update_intimacy,
    TRAIT_KEYS,
)


def test_trait_keys_are_five():
    assert len(TRAIT_KEYS) == 5
    assert set(TRAIT_KEYS) == {"extrovert", "brave", "greedy", "curious", "blunt"}


def test_compute_initial_traits_range():
    """初始值应在 [0.1, 0.9] 范围内"""
    baselines = {"extrovert": 0.5, "brave": 0.4, "greedy": 0.7, "curious": 0.5, "blunt": 0.6}
    for _ in range(50):
        traits = compute_initial_traits(baselines)
        for k, v in traits.items():
            assert 0.1 <= v <= 0.9, f"{k}={v} out of range"


def test_compute_initial_with_hatching_offset():
    baselines = {"extrovert": 0.5, "brave": 0.5, "greedy": 0.5, "curious": 0.5, "blunt": 0.5}
    hatching = {"extrovert": 0.05, "brave": 0.05}
    traits = compute_initial_traits(baselines, hatching_offsets=hatching)
    # With hatching offset, extrovert and brave should tend higher
    # (still has random component, so just check range)
    for v in traits.values():
        assert 0.1 <= v <= 0.9


def test_apply_interaction_offset():
    traits = {"extrovert": 0.5, "brave": 0.5, "greedy": 0.5, "curious": 0.5, "blunt": 0.5}
    baselines = {"extrovert": 0.5, "brave": 0.5, "greedy": 0.5, "curious": 0.5, "blunt": 0.5}
    offsets = {"extrovert": 0.0, "brave": 0.0, "greedy": 0.0, "curious": 0.0, "blunt": 0.0}
    daily_used = {"extrovert": 0.0, "brave": 0.0, "greedy": 0.0, "curious": 0.0, "blunt": 0.0}

    new_offsets, new_daily = apply_interaction_offset(
        offsets, daily_used, baselines, "feed"
    )
    # Feeding should increase greedy
    assert new_offsets["greedy"] > 0
    assert new_daily["greedy"] > 0


def test_offset_respects_daily_cap():
    offsets = {"extrovert": 0.0, "brave": 0.0, "greedy": 0.0, "curious": 0.0, "blunt": 0.0}
    baselines = {"extrovert": 0.5, "brave": 0.5, "greedy": 0.5, "curious": 0.5, "blunt": 0.5}
    daily = {"extrovert": 0.015, "brave": 0.0, "greedy": 0.0, "curious": 0.0, "blunt": 0.0}

    # extrovert daily already at cap
    new_offsets, new_daily = apply_interaction_offset(
        offsets, daily, baselines, "play"  # play increases extrovert
    )
    # Should not increase further
    assert new_offsets["extrovert"] == 0.0


def test_offset_respects_absolute_cap():
    offsets = {"extrovert": 0.25, "brave": 0.0, "greedy": 0.0, "curious": 0.0, "blunt": 0.0}
    baselines = {"extrovert": 0.5, "brave": 0.5, "greedy": 0.5, "curious": 0.5, "blunt": 0.5}
    daily = {"extrovert": 0.0, "brave": 0.0, "greedy": 0.0, "curious": 0.0, "blunt": 0.0}

    new_offsets, _ = apply_interaction_offset(
        offsets, daily, baselines, "play"
    )
    # Should not exceed 0.25
    assert new_offsets["extrovert"] <= 0.25


def test_daily_decay_toward_baseline():
    offsets = {"extrovert": 0.1, "brave": -0.1, "greedy": 0.0, "curious": 0.05, "blunt": -0.02}
    new_offsets = daily_decay_toward_baseline(offsets)
    # All should move toward 0
    assert abs(new_offsets["extrovert"]) < abs(offsets["extrovert"])
    assert abs(new_offsets["brave"]) < abs(offsets["brave"])
    # Zero should stay zero
    assert new_offsets["greedy"] == 0.0


def test_get_trait_band():
    assert get_trait_band(0.1) == "low"
    assert get_trait_band(0.29) == "low"
    assert get_trait_band(0.3) == "mid"
    assert get_trait_band(0.5) == "mid"
    assert get_trait_band(0.69) == "mid"
    assert get_trait_band(0.7) == "high"
    assert get_trait_band(0.9) == "high"


def test_detect_band_crossings():
    old_traits = {"extrovert": 0.29, "brave": 0.5, "greedy": 0.69, "curious": 0.5, "blunt": 0.5}
    new_traits = {"extrovert": 0.31, "brave": 0.5, "greedy": 0.71, "curious": 0.5, "blunt": 0.5}
    crossings = detect_band_crossings(old_traits, new_traits)
    assert "extrovert" in crossings  # low → mid
    assert "greedy" in crossings      # mid → high
    assert "brave" not in crossings   # no change


def test_update_intimacy():
    # 互动增加
    new_val, daily = update_intimacy(0.5, daily_gained=0.0, interaction=True)
    assert new_val > 0.5
    assert daily > 0.0

    # 日上限
    new_val2, daily2 = update_intimacy(0.5, daily_gained=0.05, interaction=True)
    assert new_val2 == 0.5  # daily cap reached

    # 忽视减少
    new_val3, _ = update_intimacy(0.5, daily_gained=0.0, interaction=False, hours_since_last=25)
    assert new_val3 < 0.5
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd c:/Users/Aoc/OneDrive/ClaudeCodeP/017Pet
py -m pytest tests/test_personality.py -v
```

Expected: FAIL

- [ ] **Step 3: 实现 personality.py**

Write `pet/personality.py`:
```python
"""性格引擎：5 维性格 + 亲密度管理。

性格架构：
  displayed_trait[key] = species_baseline[key] + learned_offset[key]

存储在 pet.json 中：
  pet.traits = {extrovert: 0.52, brave: 0.41, ...}    # 当前展示值
  pet.trait_offsets = {extrovert: 0.02, brave: -0.09, ...}  # 学习偏移量
  pet.trait_daily = {extrovert: 0.005, ...}  # 今日已用偏移量（每日重置）
  pet.intimacy = 0.65
  pet.intimacy_daily_gained = 0.03
"""

import random

TRAIT_KEYS = ["extrovert", "brave", "greedy", "curious", "blunt"]

# 互动 → 性格影响映射
INTERACTION_TRAIT_MAP = {
    "feed":    {"greedy": 0.005},
    "explore": {"brave": 0.005, "curious": 0.003},
    "play":    {"extrovert": 0.005},
    "bathe":   {},
    "sleep":   {},
    "heal":    {},
    "chat":    {"extrovert": 0.002},
}

# 每日偏移上限（单个维度）
DAILY_OFFSET_CAP = 0.015

# 绝对偏移上限
ABSOLUTE_OFFSET_CAP = 0.25

# 日回归速率（向 baseline 靠拢）
DAILY_DECAY_RATE = 0.002

# 亲密度
INTIMACY_PER_INTERACTION = 0.01
INTIMACY_DAILY_CAP = 0.05
INTIMACY_NEGLECT_PENALTY = 0.03  # 24h 无互动
INTIMACY_NEGLECT_HOURS = 24


def compute_initial_traits(baselines, hatching_offsets=None):
    """计算初始性格值。

    Args:
        baselines: dict，品种基准值 {key: float}
        hatching_offsets: dict 或 None，孵化塑形偏移 {key: float}

    Returns:
        dict {key: float}，裁剪到 [0.1, 0.9]
    """
    traits = {}
    for key in TRAIT_KEYS:
        base = baselines.get(key, 0.5)
        rand_offset = random.uniform(-0.15, 0.15)
        hatch_offset = (hatching_offsets or {}).get(key, 0.0)
        value = base + rand_offset + hatch_offset
        traits[key] = max(0.1, min(0.9, round(value, 3)))
    return traits


def apply_interaction_offset(offsets, daily_used, baselines, action):
    """应用一次互动的性格偏移。

    Args:
        offsets: dict，当前 learned_offset {key: float}
        daily_used: dict，今日已用偏移 {key: float}
        baselines: dict，品种基准值
        action: str，互动类型（feed/explore/play/...）

    Returns:
        (new_offsets, new_daily_used) 两个 dict
    """
    trait_changes = INTERACTION_TRAIT_MAP.get(action, {})
    new_offsets = dict(offsets)
    new_daily = dict(daily_used)

    for key, delta in trait_changes.items():
        # 检查每日上限
        if abs(new_daily.get(key, 0.0)) + abs(delta) > DAILY_OFFSET_CAP:
            continue
        # 检查绝对上限
        if abs(new_offsets.get(key, 0.0)) + abs(delta) > ABSOLUTE_OFFSET_CAP:
            continue
        new_offsets[key] = round(new_offsets.get(key, 0.0) + delta, 4)
        new_daily[key] = round(new_daily.get(key, 0.0) + delta, 4)

    return new_offsets, new_daily


def daily_decay_toward_baseline(offsets):
    """每日回归：所有 offset 向 0 靠拢。

    Args:
        offsets: dict {key: float}

    Returns:
        new_offsets dict
    """
    new_offsets = {}
    for key in TRAIT_KEYS:
        val = offsets.get(key, 0.0)
        if val > 0:
            val = max(0.0, val - DAILY_DECAY_RATE)
        elif val < 0:
            val = min(0.0, val + DAILY_DECAY_RATE)
        new_offsets[key] = round(val, 4)
    return new_offsets


def compute_displayed_traits(baselines, offsets):
    """计算当前展示的性格值。

    displayed = baseline + offset，裁剪到 [0.1, 0.9]。
    """
    traits = {}
    for key in TRAIT_KEYS:
        val = baselines.get(key, 0.5) + offsets.get(key, 0.0)
        traits[key] = max(0.1, min(0.9, round(val, 3)))
    return traits


def get_trait_band(value):
    """返回性格区间：low / mid / high。"""
    if value < 0.3:
        return "low"
    elif value < 0.7:
        return "mid"
    else:
        return "high"


def detect_band_crossings(old_traits, new_traits):
    """检测哪些维度跨越了区间。

    Returns:
        dict {key: (old_band, new_band)} 仅包含跨越的维度
    """
    crossings = {}
    for key in TRAIT_KEYS:
        old_band = get_trait_band(old_traits.get(key, 0.5))
        new_band = get_trait_band(new_traits.get(key, 0.5))
        if old_band != new_band:
            crossings[key] = (old_band, new_band)
    return crossings


def update_intimacy(current, daily_gained, interaction=False, hours_since_last=0):
    """更新亲密度。

    Args:
        current: float，当前亲密度
        daily_gained: float，今日已增加的量
        interaction: bool，是否是一次互动
        hours_since_last: float，距上次互动的小时数

    Returns:
        (new_value, new_daily_gained)
    """
    new_val = current
    new_daily = daily_gained

    if interaction:
        if daily_gained < INTIMACY_DAILY_CAP:
            gain = min(INTIMACY_PER_INTERACTION, INTIMACY_DAILY_CAP - daily_gained)
            new_val = min(1.0, current + gain)
            new_daily = daily_gained + gain
    elif hours_since_last >= INTIMACY_NEGLECT_HOURS:
        new_val = max(0.0, current - INTIMACY_NEGLECT_PENALTY)

    return round(new_val, 3), round(new_daily, 4)


# === 区间跨越通知文案 ===

BAND_CROSSING_MESSAGES = {
    "extrovert": {
        ("low", "mid"): "{name}最近话变多了呢，开始主动找你聊天了~",
        ("mid", "high"): "{name}现在超级活泼！一刻都停不下来！",
        ("high", "mid"): "{name}最近安静了不少，不过偶尔还是会蹭过来~",
        ("mid", "low"): "{name}变得好安静...是不是有什么心事呢？",
    },
    "brave": {
        ("low", "mid"): "{name}最近明显更敢出门了！",
        ("mid", "high"): "{name}现在超级勇敢，什么都不怕了！",
        ("high", "mid"): "{name}最近谨慎了一些，会先观察再行动~",
        ("mid", "low"): "{name}变得有点胆小了...需要多鼓励鼓励~",
    },
    "greedy": {
        ("low", "mid"): "{name}最近对零食开始感兴趣了~",
        ("mid", "high"): "{name}现在超级嘴馋！看到吃的眼睛都亮了！",
        ("high", "mid"): "{name}最近对吃的没那么疯狂了~",
        ("mid", "low"): "{name}变得很克制，对食物都无所谓了~",
    },
    "curious": {
        ("low", "mid"): "{name}开始对周围的东西好奇起来了~",
        ("mid", "high"): "{name}现在好奇心爆棚！什么都想看看！",
        ("high", "mid"): "{name}最近安定了不少，不再到处乱跑了~",
        ("mid", "low"): "{name}变得很安逸，喜欢待在原地发呆~",
    },
    "blunt": {
        ("low", "mid"): "{name}最近说话直接了不少~",
        ("mid", "high"): "{name}现在越来越直球了，有什么说什么！",
        ("high", "mid"): "{name}学会委婉了，说话开始拐弯抹角~",
        ("mid", "low"): "{name}变得好含蓄...有时候猜不透它在想什么~",
    },
}


def get_crossing_message(key, old_band, new_band, pet_name):
    """获取区间跨越的通知文案。"""
    messages = BAND_CROSSING_MESSAGES.get(key, {})
    template = messages.get((old_band, new_band))
    if template:
        return template.format(name=pet_name)
    return None
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd c:/Users/Aoc/OneDrive/ClaudeCodeP/017Pet
py -m pytest tests/test_personality.py -v
```

Expected: All passed

- [ ] **Step 5: Commit**

```bash
git add pet/personality.py tests/test_personality.py
git commit -m "feat: add personality engine with 5 trait dimensions + intimacy"
```

---

## Task 2: 升级数据模型 — schema v5

**Files:**
- Modify: `pet/store.py`

- [ ] **Step 1: 修改 _default_pet 添加性格字段**

在 `store.py` 的 `_default_pet(species)` 函数中，在现有字段之后添加：

```python
# 性格系统（Phase 2）
"traits": {},              # 当前展示的性格值，由 personality.py 计算
"trait_offsets": {},        # learned_offset，互动积累的偏移
"trait_daily_used": {},     # 今日已用偏移量，每日重置
"intimacy": 0.3,           # 亲密度，初始 0.3
"intimacy_daily_gained": 0.0,
"last_interaction_at": None,  # 最后互动时间（用于计算忽视惩罚）
```

- [ ] **Step 2: 修改 SCHEMA_VERSION 为 5**

```python
SCHEMA_VERSION = 5
```

- [ ] **Step 3: 添加 v4 → v5 迁移逻辑**

在 `_migrate` 方法中添加：

```python
if from_version < 5:
    if "traits" not in self.pet:
        # 用品种 baseline 作为初始性格
        from species import get_species
        from personality import compute_initial_traits
        spec = get_species(self.pet.get("species", "penguin"))
        baselines = spec["baseline_traits"] if spec else {k: 0.5 for k in ["extrovert","brave","greedy","curious","blunt"]}
        self.pet["traits"] = compute_initial_traits(baselines)
    if "trait_offsets" not in self.pet:
        self.pet["trait_offsets"] = {k: 0.0 for k in ["extrovert","brave","greedy","curious","blunt"]}
    if "trait_daily_used" not in self.pet:
        self.pet["trait_daily_used"] = {k: 0.0 for k in ["extrovert","brave","greedy","curious","blunt"]}
    self.pet.setdefault("intimacy", 0.3)
    self.pet.setdefault("intimacy_daily_gained", 0.0)
    self.pet.setdefault("last_interaction_at", None)
    self._save()
```

- [ ] **Step 4: 验证迁移**

```bash
cd c:/Users/Aoc/OneDrive/ClaudeCodeP/017Pet
py -m pytest tests/test_store.py -v
```

Expected: All pass（旧测试兼容）

- [ ] **Step 5: Commit**

```bash
git add pet/store.py
git commit -m "feat: upgrade schema to v5 with personality traits + intimacy"
```

---

## Task 3: 孵化塑形流程

**Files:**
- Modify: `pet/core.py`
- Modify: `pet/store.py`

孵化从"直接起名"变为"3 次互动选择 → 起名"。

- [ ] **Step 1: 在 core.py MessageHandler 中修改孵化状态机**

当前孵化流程（V1）：
1. 用户说"领养" → 创建蛋 → 问名字
2. 用户输入名字 → 孵化完成

新流程（V2）：
1. 用户说"领养" → 创建蛋 → 进入孵化塑形
2. 第 1 次互动：展示蛋的状态，问"你想对蛋做什么？" 给 3 个选项
3. 第 2 次互动：同上
4. 第 3 次互动：同上
5. 蛋裂开，揭示品种 → 问名字
6. 用户输入名字 → 孵化完成，计算初始性格

在 `MessageHandler._user_state` 中添加新状态：

```python
# _user_state[user_id] 可能的值:
# None — 正常状态
# "ask_name" — 等待宠物名字（V1 遗留）
# "hatching_1" — 孵化塑形第 1 次
# "hatching_2" — 孵化塑形第 2 次
# "hatching_3" — 孵化塑形第 3 次
# "ask_name_v2" — 揭示品种后等待命名
```

孵化互动选项（每次相同 3 个选项，但用户的选择影响不同维度）：

```python
HATCHING_OPTIONS = {
    "1": {"label": "轻轻跟它说话", "offsets": {"extrovert": 0.03, "blunt": 0.02}},
    "2": {"label": "安抚它，给它温暖", "offsets": {"brave": -0.02, "curious": -0.01}},
    "3": {"label": "鼓励它去看看外面的世界", "offsets": {"brave": 0.03, "curious": 0.03}},
}
```

- [ ] **Step 2: 实现孵化塑形消息处理**

在 `handle_message` 方法中，添加对 `hatching_1/2/3` 状态的处理：

```python
# 在 handle_message 方法开头的状态机检查中
state = self._user_state.get(user_id)

if state and state.startswith("hatching_"):
    return self._handle_hatching_step(user_id, text, store)

if state == "ask_name_v2":
    return self._handle_naming(user_id, text, store)
```

新方法 `_handle_hatching_step`:
```python
def _handle_hatching_step(self, user_id, text, store):
    state = self._user_state[user_id]
    step = int(state.split("_")[1])
    
    # 解析用户选择
    choice = text.strip()
    if choice not in ("1", "2", "3"):
        return "请输入 1、2 或 3 来选择哦~\n\n1️⃣ 轻轻跟它说话\n2️⃣ 安抚它，给它温暖\n3️⃣ 鼓励它去看看外面的世界"
    
    # 累积孵化偏移
    offsets = HATCHING_OPTIONS[choice]["offsets"]
    if "hatching_offsets" not in self._user_state:
        self._user_state[f"{user_id}_hatching"] = {}
    accumulated = self._user_state.get(f"{user_id}_hatching", {})
    for k, v in offsets.items():
        accumulated[k] = accumulated.get(k, 0) + v
    self._user_state[f"{user_id}_hatching"] = accumulated
    
    action_label = HATCHING_OPTIONS[choice]["label"]
    
    if step < 3:
        # 还有更多互动
        self._user_state[user_id] = f"hatching_{step + 1}"
        egg_responses = [
            f"你选择了「{action_label}」\n\n蛋轻轻晃动了一下... 好像有反应呢！✨\n\n要继续吗？\n1️⃣ 轻轻跟它说话\n2️⃣ 安抚它，给它温暖\n3️⃣ 鼓励它去看看外面的世界",
            f"你选择了「{action_label}」\n\n蛋裂开了一条小缝！能隐约看到里面在动！🥚💫\n\n最后一次，你想对它...\n1️⃣ 轻轻跟它说话\n2️⃣ 安抚它，给它温暖\n3️⃣ 鼓励它去看看外面的世界",
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
```

新方法 `_handle_naming`:
```python
def _handle_naming(self, user_id, text, store):
    name = text.strip()
    if len(name) > 10:
        return "名字太长啦，10 个字以内吧~"
    if len(name) == 0:
        return "名字不能为空哦，再想一个吧~"
    
    # 计算初始性格
    from species import get_species
    from personality import compute_initial_traits
    
    species_id = store.get_species_id()
    spec = get_species(species_id)
    baselines = spec["baseline_traits"]
    hatching_offsets = self._user_state.pop(f"{user_id}_hatching", {})
    
    initial_traits = compute_initial_traits(baselines, hatching_offsets=hatching_offsets)
    
    # 孵化
    store.hatch(name)
    
    # 写入性格
    store.pet["traits"] = initial_traits
    store.pet["trait_offsets"] = {k: 0.0 for k in initial_traits}
    store.pet["trait_daily_used"] = {k: 0.0 for k in initial_traits}
    store._save()
    
    # 清理状态
    self._user_state.pop(user_id, None)
    
    species_name = spec["name"]
    species_emoji = spec["emoji"]
    
    # 生成性格描述
    trait_tags = _trait_tags(initial_traits)
    
    return (
        f"{species_emoji} **{name}** 开心地叫了一声！\n\n"
        f"品种：{species_name}\n"
        f"性格：{trait_tags}\n\n"
        f"从现在开始，{name}就是你的小伙伴啦！\n"
        f"试试对它说「喂食」「玩耍」或者随便聊聊天~"
    )
```

辅助函数 `_trait_tags`:
```python
TRAIT_LABELS = {
    "extrovert": {"high": "活泼", "mid": "", "low": "安静"},
    "brave": {"high": "勇敢", "mid": "", "low": "谨慎"},
    "greedy": {"high": "嘴馋", "mid": "", "low": "克制"},
    "curious": {"high": "好奇", "mid": "", "low": "安逸"},
    "blunt": {"high": "直球", "mid": "", "low": "委婉"},
}

def _trait_tags(traits):
    """从性格值生成 3 个最显著的标签。"""
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
```

- [ ] **Step 3: 验证孵化流程能编译**

```bash
cd c:/Users/Aoc/OneDrive/ClaudeCodeP/017Pet
py -c "import sys; sys.path.insert(0,'pet'); from core import MessageHandler; print('OK')"
```

- [ ] **Step 4: Commit**

```bash
git add pet/core.py pet/store.py
git commit -m "feat: 3-step hatching shaping flow with personality generation"
```

---

## Task 4: 互动性格漂移 — 接入 feed/play/explore

**Files:**
- Modify: `pet/core.py`
- Modify: `pet/store.py`

- [ ] **Step 1: 在 store.py 的 feed/play/explore 等方法中添加性格漂移调用**

在每个互动方法（feed, play, bathe, heal, start_explore）的 `_save()` 之前，添加性格更新：

```python
# 在 feed() 方法的 self._save() 之前添加：
self._apply_personality_offset("feed")
```

在 UserPetStore 中新增方法：

```python
def _apply_personality_offset(self, action):
    """应用一次互动的性格偏移。"""
    if self.pet is None or "trait_offsets" not in self.pet:
        return
    from personality import apply_interaction_offset, compute_displayed_traits
    from species import get_species
    
    spec = get_species(self.get_species_id())
    if not spec:
        return
    
    baselines = spec["baseline_traits"]
    offsets = self.pet.get("trait_offsets", {})
    daily = self.pet.get("trait_daily_used", {})
    
    new_offsets, new_daily = apply_interaction_offset(offsets, daily, baselines, action)
    
    self.pet["trait_offsets"] = new_offsets
    self.pet["trait_daily_used"] = new_daily
    self.pet["traits"] = compute_displayed_traits(baselines, new_offsets)
    
    # 更新亲密度
    from personality import update_intimacy
    from config import now_str
    intimacy = self.pet.get("intimacy", 0.3)
    daily_gained = self.pet.get("intimacy_daily_gained", 0.0)
    new_intimacy, new_daily_gained = update_intimacy(intimacy, daily_gained, interaction=True)
    self.pet["intimacy"] = new_intimacy
    self.pet["intimacy_daily_gained"] = new_daily_gained
    self.pet["last_interaction_at"] = now_str()
```

- [ ] **Step 2: 在每个互动方法中调用**

在 `feed()`, `bathe()`, `play()`, `heal()`, `start_explore()` 的 `self._save()` 之前各添加一行：

```python
self._apply_personality_offset("feed")   # 在 feed() 中
self._apply_personality_offset("bathe")  # 在 bathe() 中
self._apply_personality_offset("play")   # 在 play() 中
self._apply_personality_offset("heal")   # 在 heal() 中
self._apply_personality_offset("explore")  # 在 start_explore() 中
```

- [ ] **Step 3: 验证**

```bash
cd c:/Users/Aoc/OneDrive/ClaudeCodeP/017Pet
py -m pytest tests/ -v
```

Expected: All pass

- [ ] **Step 4: Commit**

```bash
git add pet/store.py
git commit -m "feat: personality drift on feed/play/explore/bathe/heal"
```

---

## Task 5: 日性格衰减 + 亲密度衰减

**Files:**
- Modify: `pet/scheduler.py`

- [ ] **Step 1: 添加 daily_personality_job**

在 scheduler.py 中添加每日 0:00 执行的性格衰减 job：

```python
def _daily_personality_job(registry):
    """每日重置性格日偏移量，执行 offset 回归，更新亲密度。"""
    for store in registry.all_active_stores():
        try:
            with store._lock:
                if store.pet is None or "trait_offsets" not in store.pet:
                    continue
                
                from personality import daily_decay_toward_baseline, compute_displayed_traits, update_intimacy
                from species import get_species
                
                # 重置每日偏移用量
                store.pet["trait_daily_used"] = {k: 0.0 for k in store.pet.get("trait_offsets", {})}
                store.pet["intimacy_daily_gained"] = 0.0
                
                # Offset 回归 baseline
                offsets = store.pet.get("trait_offsets", {})
                new_offsets = daily_decay_toward_baseline(offsets)
                store.pet["trait_offsets"] = new_offsets
                
                # 重算展示值
                spec = get_species(store.get_species_id())
                if spec:
                    old_traits = dict(store.pet.get("traits", {}))
                    store.pet["traits"] = compute_displayed_traits(spec["baseline_traits"], new_offsets)
                    
                    # 检测区间跨越
                    from personality import detect_band_crossings, get_crossing_message
                    crossings = detect_band_crossings(old_traits, store.pet["traits"])
                    # 跨越通知存入待发送队列（由下次 chitchat 或 tick 发出）
                    if crossings:
                        store.pet.setdefault("_pending_notifications", [])
                        for key, (old_band, new_band) in crossings.items():
                            msg = get_crossing_message(key, old_band, new_band, store.get_pet_name())
                            if msg:
                                store.pet["_pending_notifications"].append(msg)
                
                # 亲密度忽视惩罚
                last_at = store.pet.get("last_interaction_at")
                if last_at:
                    from datetime import datetime
                    from config import now
                    try:
                        last_time = datetime.fromisoformat(last_at)
                        hours = (now() - last_time).total_seconds() / 3600
                        intimacy = store.pet.get("intimacy", 0.3)
                        new_int, _ = update_intimacy(intimacy, 0.0, interaction=False, hours_since_last=hours)
                        store.pet["intimacy"] = new_int
                    except (ValueError, TypeError):
                        pass
                
                store._save()
        except Exception as e:
            print(f"[scheduler] personality decay error for {store.user_id}: {e}")
```

- [ ] **Step 2: 注册 job 到 scheduler**

在 `create_scheduler` 函数中添加：

```python
sched.add_job(
    _daily_personality_job,
    "cron",
    hour=0, minute=5,
    args=[registry],
    timezone=TIMEZONE,
    id="daily_personality",
)
```

- [ ] **Step 3: 在 tick_job 中发送待发通知**

在 `_tick_job` 的每用户循环中，添加检查 `_pending_notifications`：

```python
# 在 tick_job 的用户循环中
notifications = store.pet.pop("_pending_notifications", [])
for msg in notifications:
    send_fn(store.user_id, msg)
if notifications:
    store._save()
```

- [ ] **Step 4: Commit**

```bash
git add pet/scheduler.py
git commit -m "feat: daily personality decay + intimacy neglect penalty"
```

---

## Task 6: AI 对话注入性格 + 亲密度

**Files:**
- Modify: `pet/ai.py`

- [ ] **Step 1: 修改 _build_system_prompt 注入性格信息**

在 `_build_system_prompt` 函数中，找到品种描述部分，在其后添加性格注入：

```python
# 性格信息（Phase 2）
traits = pet_context.get("traits", {})
intimacy = pet_context.get("intimacy", 0.3)

from personality import get_trait_band, TRAIT_KEYS
trait_desc_parts = []
trait_label_cn = {
    "extrovert": ("外向", "内向"),
    "brave": ("勇敢", "谨慎"),
    "greedy": ("嘴馋", "克制"),
    "curious": ("好奇", "安定"),
    "blunt": ("直球", "委婉"),
}
for key in TRAIT_KEYS:
    val = traits.get(key, 0.5)
    band = get_trait_band(val)
    high_label, low_label = trait_label_cn.get(key, (key, key))
    if band == "high":
        trait_desc_parts.append(f"非常{high_label}（{val:.1f}）")
    elif band == "low":
        trait_desc_parts.append(f"比较{low_label}（{val:.1f}）")

if trait_desc_parts:
    prompt_parts.append(f"性格特点：{', '.join(trait_desc_parts)}")

# 亲密度影响称呼
if intimacy >= 0.8:
    prompt_parts.append("你和主人非常亲密，会撒娇、会吃醋、偶尔偷偷说'喜欢你'")
elif intimacy >= 0.5:
    prompt_parts.append("你和主人关系不错，会主动贴贴，偶尔撒娇")
elif intimacy >= 0.3:
    prompt_parts.append("你和主人还在熟悉中，有点害羞但很期待")
else:
    prompt_parts.append("你和主人还不太熟，比较拘谨，但会努力表现自己")
```

- [ ] **Step 2: 在 core.py 构建 pet_context 时传入 traits 和 intimacy**

找到 core.py 中构建 `pet_context` dict 的地方（传给 `ai.parse_message` 的参数），确保包含：

```python
pet_context = {
    "name": store.get_pet_name(),
    "hunger": store.pet["hunger"],
    "cleanliness": store.pet["cleanliness"],
    "mood": store.pet["mood"],
    "stamina": store.pet["stamina"],
    "health": store.pet["health"],
    "is_exploring": store.pet.get("is_exploring", False),
    "is_sleeping": store.pet.get("is_sleeping", False),
    "days_together": ...,  # 已有计算逻辑
    "owner_display_name": store.owner.get("display_name", "主人"),
    # Phase 2 新增
    "traits": store.pet.get("traits", {}),
    "intimacy": store.pet.get("intimacy", 0.3),
}
```

- [ ] **Step 3: 验证 AI prompt 包含性格信息**

```bash
cd c:/Users/Aoc/OneDrive/ClaudeCodeP/017Pet
py -c "
import sys; sys.path.insert(0,'pet')
from ai import _build_system_prompt
ctx = {'name':'小七','hunger':80,'cleanliness':90,'mood':85,'stamina':70,'health':100,'is_exploring':False,'is_sleeping':False,'days_together':5,'owner_display_name':'谷雨','traits':{'extrovert':0.8,'brave':0.3,'greedy':0.75,'curious':0.5,'blunt':0.4},'intimacy':0.6}
p = _build_system_prompt(ctx, species_id='fox')
print(p)
"
```

Expected: prompt 中包含"非常外向"、"比较谨慎"、"非常嘴馋"、"关系不错"等描述

- [ ] **Step 4: Commit**

```bash
git add pet/ai.py pet/core.py
git commit -m "feat: inject personality traits + intimacy into AI system prompt"
```

---

## Task 7: 在状态展示中显示性格

**Files:**
- Modify: `pet/core.py`

- [ ] **Step 1: 修改 format_status 添加性格信息**

在 `format_status` 方法中，在属性条之后添加性格标签和亲密度显示：

```python
# 在属性条展示之后，成就统计之前
traits = store.pet.get("traits", {})
if traits:
    tags = _trait_tags(traits)
    lines.append(f"🎭 性格：{tags}")

intimacy = store.pet.get("intimacy", 0.3)
hearts = "❤️" * int(intimacy * 5)  # 0-5 颗心
if not hearts:
    hearts = "🤍"
lines.append(f"💕 亲密度：{hearts}")
```

- [ ] **Step 2: 验证**

手动测试或运行现有测试。

- [ ] **Step 3: Commit**

```bash
git add pet/core.py
git commit -m "feat: show personality tags + intimacy in status display"
```

---

## Task 8: 端到端验证

- [ ] **Step 1: 运行全部测试**

```bash
cd c:/Users/Aoc/OneDrive/ClaudeCodeP/017Pet
py -m pytest tests/ -v
```

- [ ] **Step 2: 手动测试孵化流程**

启动 bot，走完整孵化流程：
1. 发"领养" → 进入孵化塑形
2. 选择 3 次互动选项
3. 看到品种揭示
4. 起名
5. 看到性格标签
6. 发"看看" → 确认状态展示包含性格和亲密度
7. 多次喂食后发"看看" → 观察性格是否有微小变化

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "feat: Phase 2 complete - personality system with hatching shaping"
```

---

## 已知注意事项

1. **孵化塑形的 3 次互动**是固定选项，不是自由对话。这是有意的设计——简单选项比自由输入更容易引导用户，也更容易映射到性格偏移。

2. **性格漂移非常缓慢**（每次 0.005，每日上限 0.015）。用户短期内不会感知到变化。跨区间通知是唯一的感知渠道。

3. **亲密度会因忽视下降**，但性格不会因忽视直接变化（offset 只回归 baseline，不会变成反向）。

4. **AI prompt 注入的是展示值**（baseline + offset），不是原始 offset。AI 不需要知道 baseline 和 offset 的拆分。

5. **每日重置在 0:05 执行**（避开 0:00 整点可能的其他任务冲突）。
