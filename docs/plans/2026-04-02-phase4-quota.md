# Phase 4: 额度系统 — 施工计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 双能量系统——陪伴能量（免费/日恢复）覆盖基础聊天，创作能量（星星/付费）覆盖生图、卡片、语音。渐进式降级。

**Architecture:** 独立 `quota.py` 模块，`can_spend()` + `spend()` 接口。调用方（ai.py、image_gen.py、core.py）在执行前检查额度。

**Tech Stack:** Python 3.13, json, threading

**前置条件:** Phase 1-3 已完成

**设计文档:** `017Pet/docs/2026-04-02-pet-v2-design.md` — 模块三

---

## 额度设计速览

### 双能量
- **陪伴能量**：每日自动恢复 100 点。日常聊天每次消耗 1 点，基础回复 0 点。
- **创作能量（星星）**：初始赠送 100 颗（≈ ¥2）。生图、精装卡、语音消耗星星。

### 消耗表
| 行为 | 消耗类型 | 消耗量 |
|------|----------|--------|
| AI 对话 | 陪伴能量 | 1 |
| 预制模板回复 | 无 | 0 |
| 主动闲聊（AI） | 陪伴能量 | 1 |
| 生图（1张） | 星星 | 10 |
| 精装分享卡 | 星星 | 3 |
| 语音生成 | 星星 | 5 |
| 探险长文（AI） | 星星 | 2 |
| 日记生成 | 星星 | 1 |
| 周报生成 | 星星 | 2 |

### 渐进降级
| 级别 | 触发条件 | 表现 |
|------|----------|------|
| 正常 | 星星 ≥ 30% | 全功能 |
| 轻度 | 星星 < 30% | AI 回复变短（max_tokens 减半），闲聊减少 |
| 中度 | 星星 < 10% | 不生成新图片和精装卡 |
| 深度（犯困） | 星星 = 0 且陪伴能量 = 0 | 预制模板回复 |

---

## Task 1: 创建 quota.py

**Files:**
- Create: `pet/quota.py`
- Create: `tests/test_quota.py`

- [ ] **Step 1: 写测试**

Write `tests/test_quota.py`:
```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'pet'))

from quota import QuotaManager, DegradationLevel


def test_initial_quota():
    qm = QuotaManager(stars=100, companion_energy=100)
    assert qm.stars == 100
    assert qm.companion_energy == 100


def test_spend_stars():
    qm = QuotaManager(stars=100, companion_energy=100)
    assert qm.can_spend_stars(10)
    assert qm.spend_stars(10)
    assert qm.stars == 90


def test_spend_stars_insufficient():
    qm = QuotaManager(stars=5, companion_energy=100)
    assert not qm.can_spend_stars(10)
    assert not qm.spend_stars(10)
    assert qm.stars == 5  # unchanged


def test_spend_companion():
    qm = QuotaManager(stars=100, companion_energy=10)
    assert qm.can_spend_companion(1)
    assert qm.spend_companion(1)
    assert qm.companion_energy == 9


def test_daily_reset():
    qm = QuotaManager(stars=50, companion_energy=0)
    qm.daily_reset()
    assert qm.companion_energy == 100
    assert qm.stars == 50  # stars NOT reset


def test_degradation_normal():
    qm = QuotaManager(stars=100, companion_energy=100)
    assert qm.degradation_level() == DegradationLevel.NORMAL


def test_degradation_light():
    qm = QuotaManager(stars=20, companion_energy=100, initial_stars=100)
    assert qm.degradation_level() == DegradationLevel.LIGHT


def test_degradation_medium():
    qm = QuotaManager(stars=5, companion_energy=100, initial_stars=100)
    assert qm.degradation_level() == DegradationLevel.MEDIUM


def test_degradation_deep():
    qm = QuotaManager(stars=0, companion_energy=0, initial_stars=100)
    assert qm.degradation_level() == DegradationLevel.DEEP


def test_recharge():
    qm = QuotaManager(stars=10, companion_energy=50)
    qm.recharge_stars(50)
    assert qm.stars == 60


def test_to_dict_and_from_dict():
    qm = QuotaManager(stars=42, companion_energy=88, initial_stars=100)
    d = qm.to_dict()
    qm2 = QuotaManager.from_dict(d)
    assert qm2.stars == 42
    assert qm2.companion_energy == 88
    assert qm2.initial_stars == 100
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd c:/Users/Aoc/OneDrive/ClaudeCodeP/017Pet
py -m pytest tests/test_quota.py -v
```

- [ ] **Step 3: 实现 quota.py**

Write `pet/quota.py`:
```python
"""额度系统：双能量（陪伴能量 + 创作星星）+ 渐进降级。

存储在 pet.json 的 quota 字段：
  pet.quota = {
      "stars": 100,
      "companion_energy": 100,
      "initial_stars": 100,
      "total_recharged": 0,
  }
"""

from enum import Enum


class DegradationLevel(Enum):
    NORMAL = "normal"    # 全功能
    LIGHT = "light"      # AI 回复变短，闲聊减少
    MEDIUM = "medium"    # 不生成新图片和精装卡
    DEEP = "deep"        # 预制模板回复


# 消耗常量
COST_AI_CHAT = 1           # 陪伴能量
COST_IMAGE_GEN = 10        # 星星
COST_SHARE_CARD = 3        # 星星
COST_VOICE = 5             # 星星
COST_EXPLORE_STORY = 2     # 星星
COST_DIARY = 1             # 星星
COST_WEEKLY_REPORT = 2     # 星星

# 每日恢复
DAILY_COMPANION_ENERGY = 100

# 降级阈值（基于 initial_stars 的百分比）
LIGHT_THRESHOLD = 0.30
MEDIUM_THRESHOLD = 0.10


class QuotaManager:
    """额度管理器。每个用户一个实例。

    用法：
        qm = QuotaManager.from_dict(store.pet.get("quota", {}))
        if qm.can_spend_stars(COST_IMAGE_GEN):
            qm.spend_stars(COST_IMAGE_GEN)
            store.pet["quota"] = qm.to_dict()
            store._save()
    """

    def __init__(self, stars=100, companion_energy=100, initial_stars=100, total_recharged=0):
        self.stars = stars
        self.companion_energy = companion_energy
        self.initial_stars = initial_stars or 100
        self.total_recharged = total_recharged

    @classmethod
    def from_dict(cls, d):
        if not d:
            return cls()
        return cls(
            stars=d.get("stars", 100),
            companion_energy=d.get("companion_energy", 100),
            initial_stars=d.get("initial_stars", 100),
            total_recharged=d.get("total_recharged", 0),
        )

    def to_dict(self):
        return {
            "stars": self.stars,
            "companion_energy": self.companion_energy,
            "initial_stars": self.initial_stars,
            "total_recharged": self.total_recharged,
        }

    def can_spend_stars(self, amount):
        return self.stars >= amount

    def spend_stars(self, amount):
        if self.stars < amount:
            return False
        self.stars -= amount
        return True

    def can_spend_companion(self, amount=1):
        return self.companion_energy >= amount

    def spend_companion(self, amount=1):
        if self.companion_energy < amount:
            return False
        self.companion_energy -= amount
        return True

    def daily_reset(self):
        """每日重置陪伴能量（星星不重置）。"""
        self.companion_energy = DAILY_COMPANION_ENERGY

    def recharge_stars(self, amount):
        """充值星星。"""
        self.stars += amount
        self.total_recharged += amount

    def degradation_level(self):
        """计算当前降级等级。"""
        if self.stars <= 0 and self.companion_energy <= 0:
            return DegradationLevel.DEEP

        star_ratio = self.stars / max(self.initial_stars, 1)

        if star_ratio < MEDIUM_THRESHOLD:
            return DegradationLevel.MEDIUM
        elif star_ratio < LIGHT_THRESHOLD:
            return DegradationLevel.LIGHT
        else:
            return DegradationLevel.NORMAL

    def format_status(self):
        """格式化额度状态显示。"""
        stars_display = f"⭐ 星星：{self.stars}"
        energy_bar = "🔋" * max(1, self.companion_energy // 20) if self.companion_energy > 0 else "🪫"
        energy_display = f"💬 陪伴能量：{energy_bar} ({self.companion_energy})"

        level = self.degradation_level()
        if level == DegradationLevel.DEEP:
            status = "😴 犯困中...补充星星让我恢复活力吧"
        elif level == DegradationLevel.MEDIUM:
            status = "😪 有点累了...高级功能暂时休息中"
        elif level == DegradationLevel.LIGHT:
            status = "🙂 还好，但星星不太够了"
        else:
            status = "✨ 状态很好！"

        return f"{stars_display}\n{energy_display}\n{status}"
```

- [ ] **Step 4: 运行测试**

```bash
cd c:/Users/Aoc/OneDrive/ClaudeCodeP/017Pet
py -m pytest tests/test_quota.py -v
```

- [ ] **Step 5: Commit**

```bash
git add pet/quota.py tests/test_quota.py
git commit -m "feat: add dual-energy quota system with graceful degradation"
```

---

## Task 2: 集成到数据模型

**Files:**
- Modify: `pet/store.py`

- [ ] **Step 1: 在 _default_pet 中添加 quota 字段**

```python
"quota": {
    "stars": 100,
    "companion_energy": 100,
    "initial_stars": 100,
    "total_recharged": 0,
},
```

- [ ] **Step 2: schema 迁移 v5 → v6**

```python
if from_version < 6:
    self.pet.setdefault("quota", {
        "stars": 100,
        "companion_energy": 100,
        "initial_stars": 100,
        "total_recharged": 0,
    })
    self._save()
```

更新 `SCHEMA_VERSION = 6`

- [ ] **Step 3: Commit**

```bash
git add pet/store.py
git commit -m "feat: add quota field to pet data (schema v6)"
```

---

## Task 3: AI 对话接入额度检查

**Files:**
- Modify: `pet/core.py`
- Modify: `pet/ai.py`

- [ ] **Step 1: 在 handle_message 的 AI 调用前检查额度**

在 core.py 的 `handle_message` 中，AI fallback 调用前：

```python
from quota import QuotaManager, DegradationLevel, COST_AI_CHAT

qm = QuotaManager.from_dict(store.pet.get("quota", {}))
level = qm.degradation_level()

if level == DegradationLevel.DEEP:
    # 犯困模式：预制模板回复
    replies = [
        f"{pet_name}打了个哈欠... zzZ",
        f"{pet_name}迷迷糊糊地蹭了蹭你~",
        f"今天有点困... 先陪你待着，等补充点星星再跟你好好聊~",
    ]
    import random
    return random.choice(replies)

# 消耗陪伴能量
if qm.can_spend_companion(COST_AI_CHAT):
    qm.spend_companion(COST_AI_CHAT)
    store.pet["quota"] = qm.to_dict()
    store._save()
else:
    # 陪伴能量不足但星星还有
    return f"{pet_name}有点累了，明天能量恢复了再聊吧~"
```

- [ ] **Step 2: 轻度降级时缩短 AI 回复**

在 ai.py 的 `parse_message` 中，添加 `degradation` 参数：

```python
def parse_message(text, pet_context, history=None, species_id="penguin", degradation="normal"):
    # ...
    max_tokens = 200
    if degradation == "light":
        max_tokens = 100
        history = (history or [])[-20:]  # 缩短历史
    # ...
```

core.py 调用时传入降级等级：

```python
result = ai.parse_message(text, pet_context, history=store.chat_history,
                          species_id=species_id,
                          degradation=level.value)
```

- [ ] **Step 3: Commit**

```bash
git add pet/core.py pet/ai.py
git commit -m "feat: AI chat quota check with graceful degradation"
```

---

## Task 4: 生图接入额度检查

**Files:**
- Modify: `pet/core.py`（孵化生图处）

- [ ] **Step 1: 孵化生图前检查星星**

在 core.py 的孵化生图触发处：

```python
from quota import QuotaManager, COST_IMAGE_GEN

qm = QuotaManager.from_dict(store.pet.get("quota", {}))
images_to_gen = ["base", "idle", "happy", "sleeping"]
total_cost = len(images_to_gen) * COST_IMAGE_GEN

if qm.can_spend_stars(total_cost):
    qm.spend_stars(total_cost)
    store.pet["quota"] = qm.to_dict()
    store._save()
    # 触发异步生图...
else:
    # 星星不足，用预制图
    print(f"[quota] Not enough stars for hatching images, using fallback")
```

- [ ] **Step 2: 成长解锁生图也检查星星**

同样在 store.py 的 `add_xp` 升级时，检查星星是否足够。

- [ ] **Step 3: Commit**

```bash
git add pet/core.py pet/store.py
git commit -m "feat: image generation quota check"
```

---

## Task 5: 日额度重置 + 状态展示

**Files:**
- Modify: `pet/scheduler.py`
- Modify: `pet/core.py`

- [ ] **Step 1: 在 daily_personality_job 中添加额度重置**

在 scheduler.py 的每日 job 中：

```python
# 每日重置陪伴能量
from quota import QuotaManager
qm = QuotaManager.from_dict(store.pet.get("quota", {}))
qm.daily_reset()
store.pet["quota"] = qm.to_dict()
```

- [ ] **Step 2: 在 format_status 中显示额度**

在 core.py 的 `format_status` 中添加：

```python
from quota import QuotaManager
qm = QuotaManager.from_dict(store.pet.get("quota", {}))
lines.append("")
lines.append(qm.format_status())
```

- [ ] **Step 3: 添加"充值"命令**

在 core.py 的 `_rule_route` 中添加"充值"关键词，返回充值指引文案：

```python
if "充值" in text or "买星星" in text:
    return "recharge"
```

处理 recharge 时返回文案（V1 阶段手动转账）：

```python
if action == "recharge":
    return "想要更多星星吗？✨\n\n目前是内测阶段，请联系谷雨充值~\n💰 ¥2 = 100 星星\n💰 ¥5 = 280 星星\n💰 ¥10 = 600 星星"
```

- [ ] **Step 4: Commit**

```bash
git add pet/scheduler.py pet/core.py
git commit -m "feat: daily quota reset + status display + recharge command"
```

---

## Task 6: 闲聊额度控制

**Files:**
- Modify: `pet/scheduler.py`

- [ ] **Step 1: 闲聊 job 中检查额度和降级**

在 `_chitchat_job` 的每用户处理中：

```python
from quota import QuotaManager, DegradationLevel

qm = QuotaManager.from_dict(store.pet.get("quota", {}))
level = qm.degradation_level()

if level == DegradationLevel.DEEP:
    continue  # 犯困模式不主动闲聊

if level == DegradationLevel.LIGHT:
    # 轻度降级：降低闲聊概率
    if random.random() > 0.3:  # 原本 50%，现在只有 30%
        continue

# 50% 用预制模板（不消耗），50% 用 AI（消耗陪伴能量）
use_ai = random.random() < 0.5 and qm.can_spend_companion(1)
if use_ai:
    qm.spend_companion(1)
    store.pet["quota"] = qm.to_dict()
    store._save()
    msg = _generate_chitchat(name, store.pet, slot_key, species_id=store.get_species_id())
else:
    # 预制模板
    msg = random.choice(_CHITCHAT_FALLBACK.get(slot_key, ["~"])).format(name=name)
```

- [ ] **Step 2: 日记和周报也检查星星**

```python
# _diary_job
from quota import QuotaManager, COST_DIARY
qm = QuotaManager.from_dict(store.pet.get("quota", {}))
if qm.can_spend_stars(COST_DIARY):
    qm.spend_stars(COST_DIARY)
    store.pet["quota"] = qm.to_dict()
    # ... 生成 AI 日记
else:
    # 用简单模板
    ...
```

- [ ] **Step 3: Commit**

```bash
git add pet/scheduler.py
git commit -m "feat: quota-aware chitchat, diary, and weekly report"
```

---

## Task 7: 端到端验证

- [ ] **Step 1: 运行全部测试**

```bash
cd c:/Users/Aoc/OneDrive/ClaudeCodeP/017Pet
py -m pytest tests/ -v
```

- [ ] **Step 2: 手动测试**

1. 发"看看" → 确认状态显示包含星星和陪伴能量
2. 多次对话 → 观察陪伴能量减少
3. 发"充值" → 看到充值指引
4. 手动修改 pet.json 将 stars 设为 5 → 发消息 → 确认 AI 回复变短（轻度降级）
5. 将 stars 和 companion_energy 都设为 0 → 确认进入犯困模式

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "feat: Phase 4 complete - dual energy quota system"
```
