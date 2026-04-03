# Phase 5: 传播系统 — 施工计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 性格签卡（第一传播武器）、宠物名片、成就卡、邀请码（4 位/可控稀缺）、轻版成长册 H5。

**Architecture:** 新建 cards.py（Pillow 卡片生成）、invite.py（邀请码系统）、highlights.py（高光时刻分级）、h5.py（轻量 Flask 静态页）。

**Tech Stack:** Python 3.13, Pillow, Flask（轻量 H5）, json, random, string

**前置条件:** Phase 1-4 已完成

**设计文档:** `017Pet/docs/2026-04-02-pet-v2-design.md` — 模块四

---

## 传播设计速览

### 优先级
1. 性格签卡（孵化完成自动生成，最强拉新素材）
2. 宠物名片（随时可查看）
3. 高光时刻卡（S 级事件触发）
4. 邀请码机制
5. 周报卡
6. 成长册 H5

### 高光分级
| 级别 | 事件 | 处理 |
|------|------|------|
| S 级 | 第一次叫名字、满月、成年礼、SSR 纪念品 | 分镜+卡片+自然分享提示 |
| A 级 | 性格跨档、第一次探险、第一件收藏 | 轻提醒+记录 |
| B 级 | 普通成就 | 只记录 |

### 邀请码
- 4 位字母+数字，初始 1 个码
- 补码路径：养满3天/分享卡片/连续7天

---

## Task 1: 创建 highlights.py — 高光时刻引擎

**Files:**
- Create: `pet/highlights.py`

- [ ] **Step 1: 实现高光检测与分级**

Write `pet/highlights.py`:
```python
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
```

- [ ] **Step 2: Commit**

```bash
git add pet/highlights.py
git commit -m "feat: add highlight detection engine with S/A/B grading"
```

---

## Task 2: 创建 cards.py — 卡片生成器

**Files:**
- Create: `pet/cards.py`

- [ ] **Step 1: 实现 4 种卡片模板**

Write `pet/cards.py`:
```python
"""Pillow 卡片生成器：4 种分享卡片模板。

1. 性格签卡（personality_sign_card）— 孵化完成时，最强拉新素材
2. 宠物名片（pet_profile_card）— 随时可查看
3. 成就卡（achievement_card）— S 级高光时
4. 周报卡（weekly_report_card）— 每周日
"""

from PIL import Image, ImageDraw, ImageFont
import os
from pathlib import Path

ASSETS_BASE = Path(__file__).parent.parent / "assets"


def _load_font(size):
    """加载中文字体。"""
    try:
        return ImageFont.truetype("msyh.ttc", size)
    except (OSError, IOError):
        try:
            return ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", size)
        except (OSError, IOError):
            return ImageFont.load_default()


def _draw_centered(draw, text, font, color, canvas_width, y):
    bbox = draw.textbbox((0, 0), text, font=font)
    x = (canvas_width - (bbox[2] - bbox[0])) // 2
    draw.text((x, y), text, fill=color, font=font)


def _draw_rounded_rect(draw, xy, radius, fill):
    """绘制圆角矩形。"""
    x0, y0, x1, y1 = xy
    draw.rounded_rectangle(xy, radius=radius, fill=fill)


def personality_sign_card(character_path, pet_name, species_name, species_emoji,
                          trait_tags, trait_desc, size=(1024, 1024)):
    """性格签卡：类似 MBTI 结果卡。

    布局：
    - 顶部渐变背景
    - 居中角色大图
    - "你孵出了一只【XXX】！"
    - 性格标签
    - 性格描述
    - 底部 CTA
    """
    # 渐变背景
    canvas = Image.new("RGBA", size, (250, 245, 255, 255))
    draw = ImageDraw.Draw(canvas)

    # 渐变色块
    _draw_rounded_rect(draw, (40, 40, size[0]-40, size[1]-40), 30, (255, 255, 255, 230))

    # 角色图
    if character_path and os.path.exists(character_path):
        char_img = Image.open(character_path).convert("RGBA")
        char_img = char_img.resize((400, 400), Image.LANCZOS)
        x = (size[0] - 400) // 2
        canvas.paste(char_img, (x, 100), char_img)

    font_title = _load_font(44)
    font_name = _load_font(56)
    font_tags = _load_font(36)
    font_desc = _load_font(24)
    font_cta = _load_font(20)

    # "你孵出了一只..."
    _draw_centered(draw, "你孵出了一只", font_title, (100, 100, 100), size[0], 530)

    # 品种名 + emoji
    _draw_centered(draw, f"{species_emoji} {species_name} · {pet_name}", font_name, (60, 60, 60), size[0], 585)

    # 性格标签
    _draw_centered(draw, trait_tags, font_tags, (130, 100, 180), size[0], 660)

    # 性格描述
    if trait_desc:
        lines = _wrap_text(trait_desc, 30)
        y = 720
        for line in lines[:3]:
            _draw_centered(draw, line, font_desc, (120, 120, 120), size[0], y)
            y += 35

    # CTA
    _draw_centered(draw, "看看你会孵出什么样的宠物？", font_cta, (180, 160, 200), size[0], size[1] - 80)

    return canvas


def pet_profile_card(character_path, pet_name, species_name, species_emoji,
                     trait_tags, ai_tagline, days_together, size=(1024, 600)):
    """宠物名片。

    横向布局：左半角色图，右半信息。
    """
    canvas = Image.new("RGBA", size, (255, 255, 255, 255))
    draw = ImageDraw.Draw(canvas)
    _draw_rounded_rect(draw, (20, 20, size[0]-20, size[1]-20), 20, (248, 248, 252, 255))

    # 左半：角色
    if character_path and os.path.exists(character_path):
        char_img = Image.open(character_path).convert("RGBA")
        char_img = char_img.resize((350, 350), Image.LANCZOS)
        canvas.paste(char_img, (60, 120), char_img)

    font_name = _load_font(48)
    font_info = _load_font(28)
    font_tag = _load_font(24)
    font_quote = _load_font(22)

    right_x = 460

    # 名字
    draw.text((right_x, 120), f"{species_emoji} {pet_name}", fill=(40, 40, 40), font=font_name)

    # 品种
    draw.text((right_x, 185), species_name, fill=(120, 120, 120), font=font_info)

    # 性格标签
    draw.text((right_x, 240), trait_tags, fill=(130, 100, 180), font=font_tag)

    # AI 签名
    if ai_tagline:
        draw.text((right_x, 300), f"「{ai_tagline}」", fill=(150, 150, 150), font=font_quote)

    # 在一起天数
    draw.text((right_x, 380), f"在一起 {days_together} 天", fill=(180, 180, 180), font=font_tag)

    return canvas


def achievement_card(character_path, pet_name, achievement_name, achievement_desc,
                     rarity="normal", size=(1024, 600)):
    """成就卡。"""
    bg_colors = {
        "normal": (245, 245, 250, 255),
        "rare": (240, 248, 255, 255),
        "ssr": (255, 248, 235, 255),
    }
    canvas = Image.new("RGBA", size, bg_colors.get(rarity, bg_colors["normal"]))
    draw = ImageDraw.Draw(canvas)

    border_colors = {
        "normal": (200, 200, 210),
        "rare": (100, 150, 255),
        "ssr": (255, 180, 50),
    }
    border = border_colors.get(rarity, border_colors["normal"])
    _draw_rounded_rect(draw, (15, 15, size[0]-15, size[1]-15), 20, None)
    draw.rounded_rectangle((15, 15, size[0]-15, size[1]-15), radius=20, outline=border, width=3)

    font_title = _load_font(40)
    font_name = _load_font(32)
    font_desc = _load_font(24)

    # 成就标题
    _draw_centered(draw, "🏆 成就解锁！", font_title, (80, 80, 80), size[0], 60)
    _draw_centered(draw, achievement_name, font_name, (40, 40, 40), size[0], 130)
    _draw_centered(draw, achievement_desc, font_desc, (120, 120, 120), size[0], 190)

    # 角色
    if character_path and os.path.exists(character_path):
        char_img = Image.open(character_path).convert("RGBA")
        char_img = char_img.resize((280, 280), Image.LANCZOS)
        x = (size[0] - 280) // 2
        canvas.paste(char_img, (x, 260), char_img)

    # 宠物名
    _draw_centered(draw, pet_name, font_desc, (150, 150, 150), size[0], 560)

    return canvas


def weekly_report_card(character_path, pet_name, highlight_text, stats_text,
                       size=(1024, 800)):
    """周报卡。"""
    canvas = Image.new("RGBA", size, (248, 250, 255, 255))
    draw = ImageDraw.Draw(canvas)

    font_title = _load_font(36)
    font_body = _load_font(24)
    font_small = _load_font(20)

    _draw_centered(draw, f"📋 {pet_name}的一周小结", font_title, (60, 60, 60), size[0], 40)

    # 本周名场面
    if highlight_text:
        _draw_centered(draw, "✨ 本周名场面", font_body, (100, 100, 100), size[0], 100)
        lines = _wrap_text(highlight_text, 35)
        y = 140
        for line in lines[:3]:
            _draw_centered(draw, line, font_small, (120, 120, 120), size[0], y)
            y += 30

    # 角色图
    if character_path and os.path.exists(character_path):
        char_img = Image.open(character_path).convert("RGBA")
        char_img = char_img.resize((300, 300), Image.LANCZOS)
        x = (size[0] - 300) // 2
        canvas.paste(char_img, (x, 240), char_img)

    # 数据摘要
    if stats_text:
        lines = stats_text.split("\n")
        y = 580
        for line in lines[:5]:
            _draw_centered(draw, line, font_small, (140, 140, 140), size[0], y)
            y += 30

    return canvas


def _wrap_text(text, max_chars):
    """简易中文换行。"""
    lines = []
    while text:
        if len(text) <= max_chars:
            lines.append(text)
            break
        lines.append(text[:max_chars])
        text = text[max_chars:]
    return lines


def card_to_bytes(card_image, format="PNG"):
    """将卡片 Image 转为 bytes。"""
    from io import BytesIO
    buf = BytesIO()
    card_image.save(buf, format=format)
    return buf.getvalue()
```

- [ ] **Step 2: Commit**

```bash
git add pet/cards.py
git commit -m "feat: add 4 share card templates (sign/profile/achievement/weekly)"
```

---

## Task 3: 创建 invite.py — 邀请码系统

**Files:**
- Create: `pet/invite.py`
- Create: `tests/test_invite.py`

- [ ] **Step 1: 写测试**

Write `tests/test_invite.py`:
```python
import sys, os, tempfile, shutil
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'pet'))

from invite import InviteManager


class TestInviteManager:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.mgr = InviteManager(self.tmpdir)

    def teardown_method(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_generate_code_format(self):
        code = self.mgr.generate_code("user1")
        assert len(code) == 4
        assert code.isalnum()

    def test_generate_code_unique(self):
        codes = set()
        for i in range(20):
            c = self.mgr.generate_code(f"user{i}")
            codes.add(c)
        assert len(codes) == 20

    def test_validate_code(self):
        code = self.mgr.generate_code("user1")
        result = self.mgr.validate_code(code)
        assert result is not None
        assert result["inviter"] == "user1"

    def test_validate_invalid_code(self):
        result = self.mgr.validate_code("ZZZZ")
        assert result is None

    def test_use_code(self):
        code = self.mgr.generate_code("user1")
        ok = self.mgr.use_code(code, "user2")
        assert ok is True
        # Code should be consumed
        result = self.mgr.validate_code(code)
        assert result["used_by"] == "user2"

    def test_user_codes_count(self):
        self.mgr.generate_code("user1")
        self.mgr.generate_code("user1")
        codes = self.mgr.get_user_codes("user1")
        assert len(codes) == 2

    def test_persistence(self):
        code = self.mgr.generate_code("user1")
        mgr2 = InviteManager(self.tmpdir)
        result = mgr2.validate_code(code)
        assert result is not None
```

- [ ] **Step 2: 实现 invite.py**

Write `pet/invite.py`:
```python
"""邀请码系统。

4 位字母+数字码。每个用户初始 1 个码，通过成就/分享获取更多。
数据存储在 {data_dir}/invites.json（全局，非 per-user）。
"""

import json
import os
import random
import string
import threading


class InviteManager:
    """邀请码管理器。"""

    def __init__(self, data_dir):
        self.data_file = os.path.join(data_dir, "invites.json")
        self._lock = threading.RLock()
        self._data = self._load()

    def _load(self):
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return {"codes": {}, "user_codes": {}}

    def _save(self):
        tmp = self.data_file + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.data_file)

    def _gen_unique_code(self):
        """生成一个唯一的 4 位码。"""
        chars = string.ascii_uppercase + string.digits
        for _ in range(100):
            code = "".join(random.choices(chars, k=4))
            if code not in self._data["codes"]:
                return code
        raise RuntimeError("Unable to generate unique invite code")

    def generate_code(self, user_id):
        """为用户生成一个邀请码。"""
        with self._lock:
            code = self._gen_unique_code()
            self._data["codes"][code] = {
                "inviter": user_id,
                "used_by": None,
                "created_at": _now_str(),
                "used_at": None,
            }
            if user_id not in self._data["user_codes"]:
                self._data["user_codes"][user_id] = []
            self._data["user_codes"][user_id].append(code)
            self._save()
            return code

    def validate_code(self, code):
        """验证邀请码。返回码信息或 None。"""
        with self._lock:
            return self._data["codes"].get(code.upper())

    def use_code(self, code, new_user_id):
        """使用邀请码。返回 True/False。"""
        with self._lock:
            code = code.upper()
            info = self._data["codes"].get(code)
            if not info:
                return False
            if info["used_by"]:
                return False  # 已被使用
            if info["inviter"] == new_user_id:
                return False  # 不能自己邀请自己
            info["used_by"] = new_user_id
            info["used_at"] = _now_str()
            self._save()
            return True

    def get_user_codes(self, user_id):
        """获取用户的所有邀请码。"""
        with self._lock:
            codes = self._data["user_codes"].get(user_id, [])
            return [{"code": c, **self._data["codes"].get(c, {})} for c in codes]

    def get_available_codes(self, user_id):
        """获取用户未使用的邀请码。"""
        return [c for c in self.get_user_codes(user_id) if not c.get("used_by")]

    def get_inviter(self, code):
        """获取邀请者 user_id。"""
        info = self._data["codes"].get(code.upper())
        return info["inviter"] if info else None


def _now_str():
    try:
        from config import now_str
        return now_str()
    except ImportError:
        from datetime import datetime
        return datetime.now().isoformat()
```

- [ ] **Step 3: 运行测试**

```bash
cd c:/Users/Aoc/OneDrive/ClaudeCodeP/017Pet
py -m pytest tests/test_invite.py -v
```

- [ ] **Step 4: Commit**

```bash
git add pet/invite.py tests/test_invite.py
git commit -m "feat: add invite code system with 4-char codes"
```

---

## Task 4: 集成到 core.py — 新命令和触发

**Files:**
- Modify: `pet/core.py`

- [ ] **Step 1: 添加新命令到 _rule_route**

```python
# 在 _rule_route 中添加：
if "邀请码" in text or "邀请" in text:
    return "invite_code"
if "名片" in text or "我的卡片" in text:
    return "profile_card"
```

- [ ] **Step 2: 处理新命令**

在 handle_message 的 action 处理分支中：

```python
if action == "invite_code":
    from invite import InviteManager
    from config import DATA_DIR
    mgr = InviteManager(str(DATA_DIR))
    available = mgr.get_available_codes(user_id)
    if available:
        codes_text = "\n".join([f"  📮 {c['code']}" for c in available])
        return f"你的邀请码：\n{codes_text}\n\n把邀请码分享给朋友，让他们也来领养一只宠物吧！"
    else:
        return "你暂时没有可用的邀请码哦~\n继续养宠物，达成成就就能获得新的邀请码！"

if action == "profile_card":
    from cards import pet_profile_card, card_to_bytes
    from assets_manager import resolve_image
    from image import send_image
    
    char_path = resolve_image(store.user_dir, species_id, "base")
    trait_tags_str = _trait_tags(store.pet.get("traits", {}))
    days = _days_together(store.pet)
    
    card = pet_profile_card(
        char_path, pet_name, species_name, species_emoji,
        trait_tags_str, "", days
    )
    card_bytes = card_to_bytes(card)
    
    # 通过 iLink 发送图片
    # 需要 send_image_fn 支持 bytes
    return ("这是你的宠物名片~ ✨", "profile_card_image")
    # 注意：实际实现需要通过 send_fn 发送 bytes 图片
```

- [ ] **Step 3: 孵化完成时生成性格签卡**

在 `_handle_naming` 方法的最后，孵化完成后：

```python
# 生成性格签卡
from cards import personality_sign_card, card_to_bytes
from assets_manager import resolve_image

char_path = resolve_image(store.user_dir, species_id, "base")
from personality import get_trait_band
trait_tags_str = _trait_tags(initial_traits)

# 生成性格描述文案
trait_desc = f"这是一只{trait_tags_str}的{species_name}，它的世界因为有你而变得特别。"

card = personality_sign_card(
    char_path, name, species_name, spec["emoji"],
    trait_tags_str, trait_desc
)
card_bytes = card_to_bytes(card)

# 保存卡片
from image_gen import save_cached_image
save_cached_image(store.user_dir, "sign_card", card_bytes)
```

- [ ] **Step 4: 新用户扫码流程接入邀请码验证**

在 handle_message 的"无宠物"分支中：

```python
# 如果用户输入的是邀请码格式（4位字母数字）
import re
if re.match(r'^[A-Z0-9]{4}$', text.strip().upper()):
    from invite import InviteManager
    from config import DATA_DIR
    mgr = InviteManager(str(DATA_DIR))
    result = mgr.validate_code(text.strip())
    if result and not result.get("used_by"):
        mgr.use_code(text.strip(), user_id)
        # 给双方奖励
        inviter_id = result["inviter"]
        inviter_store = self._registry.get_or_create(inviter_id)
        if inviter_store.pet:
            from quota import QuotaManager
            qm = QuotaManager.from_dict(inviter_store.pet.get("quota", {}))
            qm.recharge_stars(10)
            inviter_store.pet["quota"] = qm.to_dict()
            inviter_store._save()
        
        # 继续正常的领养流程
        # ...
    elif result and result.get("used_by"):
        return "这个邀请码已经被使用啦~\n再找朋友要一个新的吧！"
    else:
        return "现在是邀请制领养哦~\n去找已经养宠物的朋友要一张邀请卡吧！"
```

- [ ] **Step 5: 补码逻辑**

在成就解锁、连续天数达标时自动生成新邀请码：

```python
# 在 record_action 的成就检查后
# 养满3天 → 第2个码
# 连续7天 → 额外码
# 触发 S 级高光 → 额外码
```

- [ ] **Step 6: Commit**

```bash
git add pet/core.py
git commit -m "feat: integrate invite codes, share cards, and highlights into core"
```

---

## Task 5: 创建 h5.py — 轻量成长册

**Files:**
- Create: `pet/h5.py`

- [ ] **Step 1: 实现静态页生成**

Write `pet/h5.py`:
```python
"""轻量成长册 H5 页面生成。

V1 只做静态 HTML 生成，不需要 Flask 服务器。
生成到 data/{user_id}/h5/index.html。

内容：
- 宠物立绘
- 3 个性格标签
- 在一起多少天
- 最近一个高光时刻
- 收藏品数量
- 1 段代表性日记
- 邀请入口
"""

import os
import base64


def generate_h5(store):
    """为用户生成成长册 H5 页面。"""
    if store.pet is None:
        return None

    pet = store.pet
    pet_name = store.get_pet_name()

    from species import get_species
    spec = get_species(store.get_species_id())
    species_name = spec["name"] if spec else "宠物"
    species_emoji = spec["emoji"] if spec else "🐾"

    # 性格标签
    from core import _trait_tags
    traits = pet.get("traits", {})
    trait_tags = _trait_tags(traits) if traits else "神秘"

    # 在一起天数
    from highlights import _days_together
    days = _days_together(pet)

    # 收藏数
    collection_count = len(store.collection)

    # 最近日记
    latest_diary = ""
    if store.diary:
        latest_diary = store.diary[-1].get("content", "")[:100]

    # 最近高光
    highlights = pet.get("highlights_triggered", [])
    latest_highlight = highlights[-1] if highlights else ""

    # 角色图（base64 内嵌）
    from assets_manager import resolve_image
    char_path = resolve_image(store.user_dir, store.get_species_id(), "base")
    char_b64 = ""
    if char_path and os.path.exists(char_path):
        with open(char_path, "rb") as f:
            char_b64 = base64.b64encode(f.read()).decode()

    html = _H5_TEMPLATE.format(
        pet_name=pet_name,
        species_name=species_name,
        species_emoji=species_emoji,
        trait_tags=trait_tags,
        days=days,
        collection_count=collection_count,
        latest_diary=latest_diary,
        latest_highlight=latest_highlight,
        char_b64=char_b64,
    )

    # 保存
    h5_dir = os.path.join(store.user_dir, "h5")
    os.makedirs(h5_dir, exist_ok=True)
    path = os.path.join(h5_dir, "index.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)

    return path


_H5_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{pet_name}的成长册</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, sans-serif; background: linear-gradient(135deg, #f5f3ff 0%, #ede9fe 100%); min-height: 100vh; padding: 20px; }}
.card {{ background: white; border-radius: 20px; padding: 30px; max-width: 400px; margin: 0 auto; box-shadow: 0 4px 20px rgba(0,0,0,0.08); }}
.avatar {{ text-align: center; margin-bottom: 20px; }}
.avatar img {{ width: 200px; height: 200px; border-radius: 50%; object-fit: cover; background: #f3f4f6; }}
.name {{ text-align: center; font-size: 28px; font-weight: bold; color: #1f2937; margin-bottom: 5px; }}
.species {{ text-align: center; color: #6b7280; margin-bottom: 15px; }}
.tags {{ text-align: center; color: #7c3aed; font-size: 18px; margin-bottom: 20px; }}
.stats {{ display: flex; justify-content: space-around; margin-bottom: 20px; padding: 15px; background: #f9fafb; border-radius: 12px; }}
.stat {{ text-align: center; }}
.stat-num {{ font-size: 24px; font-weight: bold; color: #4f46e5; }}
.stat-label {{ font-size: 12px; color: #9ca3af; }}
.section {{ margin-bottom: 15px; }}
.section-title {{ font-size: 14px; color: #9ca3af; margin-bottom: 5px; }}
.section-content {{ font-size: 15px; color: #374151; line-height: 1.6; }}
.cta {{ text-align: center; margin-top: 25px; padding: 15px; background: #ede9fe; border-radius: 12px; color: #6d28d9; font-size: 14px; }}
</style>
</head>
<body>
<div class="card">
  <div class="avatar">
    <img src="data:image/png;base64,{char_b64}" alt="{pet_name}" onerror="this.style.display='none'">
  </div>
  <div class="name">{species_emoji} {pet_name}</div>
  <div class="species">{species_name}</div>
  <div class="tags">{trait_tags}</div>
  <div class="stats">
    <div class="stat"><div class="stat-num">{days}</div><div class="stat-label">天</div></div>
    <div class="stat"><div class="stat-num">{collection_count}</div><div class="stat-label">收藏</div></div>
  </div>
  <div class="section">
    <div class="section-title">📖 最近的日记</div>
    <div class="section-content">{latest_diary}</div>
  </div>
  <div class="cta">想养一只？找 TA 的主人要邀请码吧~ 🎉</div>
</div>
</body>
</html>"""
```

- [ ] **Step 2: Commit**

```bash
git add pet/h5.py
git commit -m "feat: add lightweight H5 growth album page generator"
```

---

## Task 6: 端到端验证

- [ ] **Step 1: 运行全部测试**

```bash
cd c:/Users/Aoc/OneDrive/ClaudeCodeP/017Pet
py -m pytest tests/ -v
```

- [ ] **Step 2: 手动测试**

1. 完成孵化 → 确认性格签卡生成并发送
2. 发"名片" → 确认宠物名片图片
3. 发"邀请码" → 看到邀请码
4. 用另一个账号输入邀请码 → 验证通过并开始领养
5. 检查 `data/{user_id}/h5/index.html` → 在浏览器打开确认显示正常

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "feat: Phase 5 complete - sharing system with cards, invites, and H5"
```

---

## 已知注意事项

1. **卡片图片发送**：iLink 的图片发送需要 AES 加密+CDN 上传流程。cards.py 生成的 bytes 需要通过 image.py 的 `send_image()` 发送，而非 `send_image_file()`。需要在 ilink.py 中添加支持。

2. **字体文件**：Pillow 卡片依赖 msyh.ttc（微软雅黑）。非 Windows 系统需要自带字体或用 load_default()。

3. **H5 部署**：V1 阶段 H5 只是本地生成的静态文件。如果需要外网访问，后续需要部署到服务器或用 GitHub Pages。

4. **邀请码与领养流程的衔接**：新用户第一条消息如果是邀请码，需要在验证通过后自动进入领养流程。这需要在 handle_message 的"无宠物"分支中仔细处理状态。

5. **补码逻辑细节**：具体在哪些成就触发补码需要在实现时确认 achievement id 与补码条件的映射。
