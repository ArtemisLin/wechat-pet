# Phase 3: AI 生图 + 视觉合成系统 — 施工计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 孵化时 AI 生成独特宠物立绘，Pillow 三层合成（角色+场景+配饰），按成长阶段解锁新状态图。每只宠物视觉唯一。

**Architecture:** 三层视觉架构——角色基底层（AI 生成，永久缓存）→ 场景背景层（模板库）→ 装饰配饰层（叠加合成）。输出聊天图 256px / 分享卡 1024px。

**Tech Stack:** Python 3.13, Pillow, 生图 API（阿里云百炼 wan2.2 或即梦），pathlib, threading

**前置条件:** Phase 1+2 已完成（多用户 + 品种 + 性格系统正常工作）

**设计文档:** `017Pet/docs/2026-04-02-pet-v2-design.md` — 模块二

---

## Phase 1+2 产出参考

```
pet/store.py       — UserPetStore，user_dir 下有 pet.json
pet/species.py     — 6 品种定义含 baseline_traits
pet/personality.py  — 性格引擎
pet/image.py       — 现有的 AES 加密 + CDN 上传（不改动，继续使用）
pet/ilink.py       — _get_assets_dir(species_id) 按品种解析素材目录
```

**存储结构（Phase 1 产出）：**
```
data/{user_id}/
  pet.json          — 宠物数据
  images/           — 本 Phase 新建，存放 AI 生成的图片缓存
```

---

## 生图成本预算

按阿里云百炼 wan2.2-t2i-flash（¥0.14/张）估算：
- 孵化首发：基底 + idle + happy + sleeping = 4 张 ≈ ¥0.56
- 成长解锁：每阶段 1-2 张 = 5 张 ≈ ¥0.70
- 含重试缓冲：总计 ≈ ¥1.5/用户

---

## Task 1: 创建 image_gen.py — AI 生图引擎

**Files:**
- Create: `pet/image_gen.py`
- Create: `tests/test_image_gen.py`

- [ ] **Step 1: 写测试（mock API 调用）**

Write `tests/test_image_gen.py`:
```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'pet'))

from image_gen import build_prompt, ImageGenResult


def test_build_prompt_penguin_idle():
    prompt = build_prompt("penguin", "idle", traits={"greedy": 0.8})
    assert "penguin" in prompt.lower() or "企鹅" in prompt
    assert "idle" in prompt.lower() or "standing" in prompt.lower()


def test_build_prompt_fox_eating():
    prompt = build_prompt("fox", "eating")
    assert "fox" in prompt.lower() or "狐狸" in prompt


def test_build_prompt_includes_style():
    prompt = build_prompt("dragon", "happy")
    assert "cute" in prompt.lower() or "chibi" in prompt.lower() or "可爱" in prompt


def test_image_gen_result_dataclass():
    r = ImageGenResult(
        success=True,
        image_bytes=b"fake",
        prompt="test prompt",
        model="test-model",
        seed=12345,
    )
    assert r.success
    assert r.image_bytes == b"fake"
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd c:/Users/Aoc/OneDrive/ClaudeCodeP/017Pet
py -m pytest tests/test_image_gen.py -v
```

- [ ] **Step 3: 实现 image_gen.py**

Write `pet/image_gen.py`:
```python
"""AI 生图引擎：调用生图 API 生成宠物图片。

职责：
- 根据品种 + 动作 + 性格构建提示词
- 调用生图 API（阿里云百炼 / 即梦 / 其他）
- 多候选筛选
- 失败重试 + 降级到预制图

生成的图片缓存在 data/{user_id}/images/{image_key}.png
"""

import os
import json
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path


@dataclass
class ImageGenResult:
    success: bool
    image_bytes: Optional[bytes] = None
    prompt: str = ""
    model: str = ""
    seed: int = 0
    error: str = ""


# === 提示词模板 ===

SPECIES_PROMPT = {
    "penguin": "cute chibi penguin character, round body, small wings",
    "dinosaur": "cute chibi baby dinosaur character, small horns, tiny tail",
    "fox": "cute chibi fox character, fluffy tail, pointed ears",
    "rabbit": "cute chibi rabbit character, long floppy ears, fluffy",
    "owl": "cute chibi owl character, big round eyes, small wings",
    "dragon": "cute chibi baby dragon character, tiny wings, small flame",
}

ACTION_PROMPT = {
    "idle": "standing, looking forward, neutral expression",
    "happy": "jumping, big smile, sparkle eyes, excited",
    "sleeping": "curled up sleeping, eyes closed, peaceful, zzz",
    "eating": "eating food, happy expression, crumbs",
    "bathing": "in a small bathtub, bubbles, rubber duck, content",
    "playing": "playing with a ball, energetic, tail wagging",
    "exploring": "wearing a small backpack, looking at a map, adventurous",
    "sick": "lying down, thermometer, sad expression, bandage",
    "base": "front facing portrait, neutral pose, clear details",
}

STYLE_SUFFIX = "pixel art style, 256x256, white background, simple clean design, high quality, no text"

NEGATIVE_PROMPT = "blurry, low quality, deformed, ugly, extra limbs, watermark, text, realistic, photographic"


def build_prompt(species_id, action, traits=None):
    """构建生图提示词。

    Args:
        species_id: 品种 ID
        action: 动作（idle/happy/sleeping/eating/...）
        traits: dict 性格值（可选，影响表情细节）

    Returns:
        str 完整提示词
    """
    species_desc = SPECIES_PROMPT.get(species_id, SPECIES_PROMPT["penguin"])
    action_desc = ACTION_PROMPT.get(action, ACTION_PROMPT["idle"])

    # 性格影响（可选的细节调整）
    trait_hints = []
    if traits:
        if traits.get("greedy", 0.5) > 0.7:
            trait_hints.append("chubby cheeks")
        if traits.get("brave", 0.5) > 0.7:
            trait_hints.append("confident pose")
        if traits.get("curious", 0.5) > 0.7:
            trait_hints.append("wide curious eyes")

    parts = [species_desc, action_desc]
    if trait_hints:
        parts.extend(trait_hints)
    parts.append(STYLE_SUFFIX)

    return ", ".join(parts)


def generate_image(prompt, negative_prompt=None, api_key=None, api_url=None, model=None, timeout=30):
    """调用生图 API 生成图片。

    当前实现为阿里云百炼兼容接口。实际使用时根据 .env 配置切换。

    Args:
        prompt: 正向提示词
        negative_prompt: 负向提示词
        api_key: API 密钥
        api_url: API 端点
        model: 模型名称
        timeout: 超时秒数

    Returns:
        ImageGenResult
    """
    from config import IMAGE_GEN_API_KEY, IMAGE_GEN_API_URL, IMAGE_GEN_MODEL

    api_key = api_key or IMAGE_GEN_API_KEY
    api_url = api_url or IMAGE_GEN_API_URL
    model = model or IMAGE_GEN_MODEL
    negative_prompt = negative_prompt or NEGATIVE_PROMPT

    if not api_key or not api_url:
        return ImageGenResult(success=False, error="Image gen API not configured")

    try:
        body = json.dumps({
            "model": model,
            "input": {
                "prompt": prompt,
                "negative_prompt": negative_prompt,
            },
            "parameters": {
                "size": "256*256",
                "n": 1,
            }
        }).encode("utf-8")

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

        # 提交异步任务
        req = urllib.request.Request(api_url, data=body, headers=headers, method="POST")
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        resp = opener.open(req, timeout=timeout)
        result = json.loads(resp.read().decode("utf-8"))

        # 不同 API 返回格式不同，这里做通用解析
        # 阿里云百炼返回 task_id 需要轮询，其他 API 可能直接返回图片 URL
        # 这里提供两种模式

        if "output" in result and "task_id" in result["output"]:
            # 异步模式：轮询等待结果
            return _poll_async_result(result["output"]["task_id"], api_key, timeout)
        elif "output" in result and "results" in result["output"]:
            # 同步模式：直接获取结果
            image_url = result["output"]["results"][0].get("url")
            if image_url:
                image_bytes = _download_image(image_url)
                return ImageGenResult(
                    success=True,
                    image_bytes=image_bytes,
                    prompt=prompt,
                    model=model,
                )
        elif "data" in result:
            # OpenAI 兼容格式
            image_url = result["data"][0].get("url")
            if image_url:
                image_bytes = _download_image(image_url)
                return ImageGenResult(success=True, image_bytes=image_bytes, prompt=prompt, model=model)

        return ImageGenResult(success=False, error=f"Unexpected API response: {json.dumps(result)[:200]}")

    except urllib.error.HTTPError as e:
        return ImageGenResult(success=False, error=f"HTTP {e.code}: {e.read().decode()[:200]}")
    except Exception as e:
        return ImageGenResult(success=False, error=str(e))


def _poll_async_result(task_id, api_key, max_wait=60):
    """轮询异步生图任务结果。"""
    from config import IMAGE_GEN_TASK_URL
    poll_url = IMAGE_GEN_TASK_URL

    headers = {
        "Authorization": f"Bearer {api_key}",
    }

    start = time.time()
    while time.time() - start < max_wait:
        time.sleep(3)
        try:
            req = urllib.request.Request(f"{poll_url}?task_id={task_id}", headers=headers)
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            resp = opener.open(req, timeout=10)
            result = json.loads(resp.read().decode("utf-8"))

            status = result.get("output", {}).get("task_status")
            if status == "SUCCEEDED":
                image_url = result["output"]["results"][0].get("url")
                if image_url:
                    image_bytes = _download_image(image_url)
                    return ImageGenResult(success=True, image_bytes=image_bytes, prompt="", model="")
            elif status == "FAILED":
                return ImageGenResult(success=False, error="Task failed")
        except Exception:
            pass

    return ImageGenResult(success=False, error="Polling timeout")


def _download_image(url):
    """下载图片 URL 返回 bytes。"""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    resp = opener.open(url, timeout=15)
    return resp.read()


# === 图片缓存管理 ===

def get_cached_image(user_dir, image_key):
    """获取缓存的图片路径。不存在返回 None。"""
    path = os.path.join(user_dir, "images", f"{image_key}.png")
    if os.path.exists(path):
        return path
    return None


def save_cached_image(user_dir, image_key, image_bytes):
    """保存图片到缓存目录。"""
    img_dir = os.path.join(user_dir, "images")
    os.makedirs(img_dir, exist_ok=True)
    path = os.path.join(img_dir, f"{image_key}.png")
    with open(path, "wb") as f:
        f.write(image_bytes)
    return path


def save_gen_metadata(user_dir, image_key, metadata):
    """保存生成参数（用于追溯和重绘）。"""
    meta_dir = os.path.join(user_dir, "images")
    os.makedirs(meta_dir, exist_ok=True)
    path = os.path.join(meta_dir, f"{image_key}.meta.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)
```

- [ ] **Step 4: 在 config.py 中添加生图 API 配置**

在 `config.py` 中添加：

```python
# 生图 API（Phase 3）
IMAGE_GEN_API_KEY = os.environ.get("IMAGE_GEN_API_KEY", "")
IMAGE_GEN_API_URL = os.environ.get("IMAGE_GEN_API_URL", "")
IMAGE_GEN_MODEL = os.environ.get("IMAGE_GEN_MODEL", "wanx-v1")
IMAGE_GEN_TASK_URL = os.environ.get("IMAGE_GEN_TASK_URL", "")
```

在 `.env.example` 中添加：

```
IMAGE_GEN_API_KEY=your_key_here
IMAGE_GEN_API_URL=https://dashscope.aliyuncs.com/api/v1/services/aigc/text2image/image-synthesis
IMAGE_GEN_MODEL=wanx-v1
IMAGE_GEN_TASK_URL=https://dashscope.aliyuncs.com/api/v1/tasks
```

- [ ] **Step 5: 运行测试**

```bash
cd c:/Users/Aoc/OneDrive/ClaudeCodeP/017Pet
py -m pytest tests/test_image_gen.py -v
```

- [ ] **Step 6: Commit**

```bash
git add pet/image_gen.py tests/test_image_gen.py pet/config.py .env.example
git commit -m "feat: add AI image generation engine with caching"
```

---

## Task 2: 创建 compositor.py — Pillow 三层合成

**Files:**
- Create: `pet/compositor.py`

- [ ] **Step 1: 实现三层合成器**

Write `pet/compositor.py`:
```python
"""Pillow 三层视觉合成器。

层次：
  1. 场景背景层（256x256 或 1024x1024）
  2. 角色基底层（AI 生成的角色 PNG，透明背景）
  3. 装饰配饰层（帽子、围巾等，透明 PNG 叠加）

输出：
  - 聊天图：256x256
  - 分享卡：1024x1024
"""

from PIL import Image, ImageDraw, ImageFont
import os
from pathlib import Path

ASSETS_BASE = Path(__file__).parent.parent / "assets"


def compose_chat_image(character_path, scene_key=None, accessories=None, size=(256, 256)):
    """合成聊天用图片。

    Args:
        character_path: 角色 PNG 路径（透明背景）
        scene_key: 场景名（morning/afternoon/night/explore_xxx），None 则用白色背景
        accessories: list of accessory PNG 路径
        size: 输出尺寸

    Returns:
        PIL.Image 对象
    """
    canvas = Image.new("RGBA", size, (255, 255, 255, 255))

    # Layer 1: 场景背景
    if scene_key:
        scene_path = ASSETS_BASE / "scenes" / f"{scene_key}.png"
        if scene_path.exists():
            scene = Image.open(scene_path).convert("RGBA").resize(size)
            canvas = Image.alpha_composite(canvas, scene)

    # Layer 2: 角色
    if character_path and os.path.exists(character_path):
        char_img = Image.open(character_path).convert("RGBA").resize(size)
        canvas = Image.alpha_composite(canvas, char_img)

    # Layer 3: 配饰
    if accessories:
        for acc_path in accessories:
            if os.path.exists(acc_path):
                acc_img = Image.open(acc_path).convert("RGBA").resize(size)
                canvas = Image.alpha_composite(canvas, acc_img)

    return canvas


def compose_share_card(character_path, pet_name, species_name, trait_tags, days_together,
                       size=(1024, 1024)):
    """合成分享卡片（1024px）。

    简版布局：
    - 上半部分：角色大图 + 品种名
    - 下半部分：宠物名 + 性格标签 + 在一起天数
    """
    canvas = Image.new("RGBA", size, (245, 245, 250, 255))
    draw = ImageDraw.Draw(canvas)

    # 角色图（居中上半部分）
    if character_path and os.path.exists(character_path):
        char_img = Image.open(character_path).convert("RGBA")
        char_size = (512, 512)
        char_img = char_img.resize(char_size, Image.LANCZOS)
        x = (size[0] - char_size[0]) // 2
        y = 80
        canvas.paste(char_img, (x, y), char_img)

    # 文字信息（使用默认字体，实际项目可替换为自定义字体）
    try:
        # 尝试加载中文字体
        font_large = ImageFont.truetype("msyh.ttc", 48)
        font_medium = ImageFont.truetype("msyh.ttc", 32)
        font_small = ImageFont.truetype("msyh.ttc", 24)
    except (OSError, IOError):
        font_large = ImageFont.load_default()
        font_medium = ImageFont.load_default()
        font_small = ImageFont.load_default()

    # 宠物名
    text_y = 620
    _draw_centered_text(draw, pet_name, font_large, (0, 0, 0), size[0], text_y)

    # 品种
    text_y += 60
    _draw_centered_text(draw, species_name, font_medium, (120, 120, 120), size[0], text_y)

    # 性格标签
    text_y += 50
    _draw_centered_text(draw, trait_tags, font_medium, (80, 80, 80), size[0], text_y)

    # 在一起天数
    text_y += 60
    days_text = f"在一起 {days_together} 天"
    _draw_centered_text(draw, days_text, font_small, (150, 150, 150), size[0], text_y)

    return canvas


def _draw_centered_text(draw, text, font, color, canvas_width, y):
    """居中绘制文字。"""
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    x = (canvas_width - text_width) // 2
    draw.text((x, y), text, fill=color, font=font)


def image_to_bytes(img, format="PNG"):
    """将 PIL Image 转为 bytes。"""
    from io import BytesIO
    buf = BytesIO()
    img.save(buf, format=format)
    return buf.getvalue()
```

- [ ] **Step 2: 创建 assets/scenes 目录结构**

```bash
mkdir -p "c:/Users/Aoc/OneDrive/ClaudeCodeP/017Pet/assets/scenes"
mkdir -p "c:/Users/Aoc/OneDrive/ClaudeCodeP/017Pet/assets/templates"
```

暂时不需要实际场景图——合成器在无场景时用白色背景。

- [ ] **Step 3: Commit**

```bash
git add pet/compositor.py
git commit -m "feat: add Pillow 3-layer visual compositor"
```

---

## Task 3: 创建 assets_manager.py — 素材管理

**Files:**
- Create: `pet/assets_manager.py`

- [ ] **Step 1: 实现素材管理器**

Write `pet/assets_manager.py`:
```python
"""素材管理器：统一的图片路径解析。

优先级：
  1. AI 生成的缓存图（data/{user_id}/images/{key}.png）
  2. 品种预制图（assets/{species_id}/{key}.png）
  3. 默认预制图（assets/penguin/{key}.png）

成长阶段解锁：
  - 孵化完成：base, idle, happy, sleeping
  - baby→child: eating, bathing
  - child→teen: playing, exploring
  - teen→adult: sick, adult_base
"""

import os
from pathlib import Path

ASSETS_BASE = Path(__file__).parent.parent / "assets"

# 成长阶段 → 解锁的图片 key
STAGE_UNLOCKS = {
    "baby":  ["base", "idle", "happy", "sleeping"],
    "child": ["eating", "bathing"],
    "teen":  ["playing", "exploring"],
    "adult": ["sick"],
}

# 所有图片 key
ALL_IMAGE_KEYS = ["base", "idle", "happy", "sleeping", "eating",
                  "bathing", "playing", "exploring", "sick"]


def resolve_image(user_dir, species_id, image_key):
    """解析图片路径（三级优先级）。

    Args:
        user_dir: 用户数据目录
        species_id: 品种 ID
        image_key: 图片 key（idle/happy/eating/...）

    Returns:
        str 路径 或 None
    """
    # 1. AI 生成缓存
    cached = os.path.join(user_dir, "images", f"{image_key}.png")
    if os.path.exists(cached):
        return cached

    # 2. 品种预制图
    species_path = ASSETS_BASE / species_id / f"{image_key}.png"
    if species_path.exists():
        return str(species_path)

    # 3. 默认预制图（penguin）
    default_path = ASSETS_BASE / "penguin" / f"{image_key}.png"
    if default_path.exists():
        return str(default_path)

    return None


def get_unlocked_keys(stage):
    """返回指定阶段及之前所有已解锁的图片 key 列表。"""
    stages_order = ["baby", "child", "teen", "adult"]
    unlocked = []
    for s in stages_order:
        unlocked.extend(STAGE_UNLOCKS.get(s, []))
        if s == stage:
            break
    return unlocked


def get_pending_gen_keys(user_dir, stage):
    """返回已解锁但未生成的图片 key 列表。"""
    unlocked = get_unlocked_keys(stage)
    pending = []
    for key in unlocked:
        cached = os.path.join(user_dir, "images", f"{key}.png")
        if not os.path.exists(cached):
            pending.append(key)
    return pending
```

- [ ] **Step 2: Commit**

```bash
git add pet/assets_manager.py
git commit -m "feat: add assets manager with stage-based unlock"
```

---

## Task 4: 孵化时触发生图

**Files:**
- Modify: `pet/core.py`
- Modify: `pet/store.py`

- [ ] **Step 1: 在孵化完成后触发异步生图**

在 core.py 的 `_handle_naming` 方法中（Phase 2 添加的），孵化完成后添加：

```python
# 触发异步生图（不阻塞用户）
import threading
def _async_gen_images(user_dir, species_id, traits):
    try:
        from image_gen import build_prompt, generate_image, save_cached_image, save_gen_metadata
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
                print(f"[image_gen] Generated {key} for {user_id}")
            else:
                print(f"[image_gen] Failed {key} for {user_id}: {result.error}")
    except Exception as e:
        print(f"[image_gen] Error: {e}")

threading.Thread(
    target=_async_gen_images,
    args=(store.user_dir, species_id, initial_traits),
    daemon=True,
).start()
```

- [ ] **Step 2: 修改 ilink.py 的图片发送使用 assets_manager**

在 ilink.py 的 `_send_image_by_key` 中，改用 `assets_manager.resolve_image`：

```python
def _send_image_by_key(state, user_id, context_token, image_key, species_id="penguin", user_dir=None):
    path = None
    if user_dir:
        from assets_manager import resolve_image
        path = resolve_image(user_dir, species_id, image_key)
    if not path:
        path = _resolve_image_path(image_key, species_id)
    if path:
        from image import send_image_file
        send_image_file(state, user_id, context_token, path)
```

- [ ] **Step 3: 在成长升级时触发补图**

在 store.py 的 `add_xp` 方法中，当升级发生时，触发异步补图：

```python
if new_level > old_level:
    # 触发成长解锁图生成
    import threading
    def _async_gen_unlock(user_dir, species_id, new_stage, traits):
        from assets_manager import STAGE_UNLOCKS
        from image_gen import build_prompt, generate_image, save_cached_image, save_gen_metadata
        from config import now_str
        keys = STAGE_UNLOCKS.get(new_stage, [])
        for key in keys:
            prompt = build_prompt(species_id, key, traits=traits)
            result = generate_image(prompt)
            if result.success and result.image_bytes:
                save_cached_image(user_dir, key, result.image_bytes)
                save_gen_metadata(user_dir, key, {"prompt": prompt, "model": result.model, "generated_at": now_str()})
    
    threading.Thread(
        target=_async_gen_unlock,
        args=(self.user_dir, self.get_species_id(), stage_id, self.pet.get("traits", {})),
        daemon=True
    ).start()
```

- [ ] **Step 4: Commit**

```bash
git add pet/core.py pet/store.py pet/ilink.py
git commit -m "feat: async image generation on hatching + growth unlock"
```

---

## Task 5: typing 节奏表演

**Files:**
- Modify: `pet/ilink.py`

- [ ] **Step 1: 实现 typing 节奏工具函数**

在 ilink.py 中添加：

```python
def _send_with_rhythm(state, user_id, context_token, text, image_key=None,
                      species_id="penguin", user_dir=None, is_ritual=False):
    """带节奏的消息发送。

    普通消息：直接发
    仪式节点（is_ritual=True）：typing → 文字 → 短暂停 → 图片
    """
    if is_ritual and image_key:
        # 先发 typing 状态
        _send_typing(state, user_id, status=1)
        time.sleep(1.5)
        # 发文字
        send_message(state, user_id, context_token, text)
        time.sleep(1.0)
        # 发图片
        _send_image_by_key(state, user_id, context_token, image_key, species_id, user_dir)
        _send_typing(state, user_id, status=2)
    else:
        send_message(state, user_id, context_token, text)
        if image_key:
            _send_image_by_key(state, user_id, context_token, image_key, species_id, user_dir)
```

- [ ] **Step 2: Commit**

```bash
git add pet/ilink.py
git commit -m "feat: add typing rhythm for ritual moments"
```

---

## Task 6: 端到端验证

- [ ] **Step 1: 运行全部测试**

```bash
cd c:/Users/Aoc/OneDrive/ClaudeCodeP/017Pet
py -m pytest tests/ -v
```

- [ ] **Step 2: 配置 .env 中的生图 API**

确保 `.env` 中设置了生图 API 凭证。

- [ ] **Step 3: 手动测试**

启动 bot，领养一只宠物，观察：
1. 孵化完成后是否在后台生成了图片（检查 `data/{user_id}/images/` 目录）
2. 发"看看"时是否发送了 AI 生成的图片（如果已生成）
3. 如果生图未配置或失败，是否正常 fallback 到 penguin 预制图

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "feat: Phase 3 complete - AI image generation + visual composition"
```

---

## 已知注意事项

1. **生图 API 选型未确定**：代码兼容阿里云百炼和 OpenAI 格式。实际使用时需根据选定的 API 调整 `generate_image()` 中的请求格式。需要在 `.env` 中正确配置。

2. **异步生图的线程安全**：生图线程只写文件到 `images/` 目录，不修改 pet.json，因此不需要获取 store._lock。

3. **一致性问题**：同一宠物不同状态图的一致性依赖 image-to-image/reference image 模式，这需要在 `generate_image()` 中实现（基底图作为参考）。V1 先不做，后续迭代。

4. **Pillow 字体**：Windows 上 `msyh.ttc`（微软雅黑）通常可用。其他系统需要自带字体文件。

5. **场景图暂时为空**：`assets/scenes/` 目录暂时没有实际场景图。合成器在无场景时用白色背景，不影响功能。
