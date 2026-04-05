"""AI 生图引擎：调用即梦 API 生成宠物图片。

职责：
- 根据品种 + 动作 + 性格构建提示词
- 调用即梦 API（火山引擎 volcengine SDK）
- 异步提交 + 轮询结果
- 失败降级到预制图

生成的图片缓存在 data/{user_id}/images/{image_key}.png
"""

import os
import json
import time
import base64
from dataclasses import dataclass
from typing import Optional


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


# === 即梦 API 调用（volcengine SDK）===

_REQ_KEY = "jimeng_seedream46_cvtob"

_visual_service = None


def _get_visual_service():
    """懒加载 VisualService 单例。"""
    global _visual_service
    if _visual_service is None:
        from config import IMAGE_GEN_AK, IMAGE_GEN_SK
        if not IMAGE_GEN_AK or not IMAGE_GEN_SK:
            return None
        from volcengine.visual.VisualService import VisualService
        _visual_service = VisualService()
        _visual_service.set_ak(IMAGE_GEN_AK)
        _visual_service.set_sk(IMAGE_GEN_SK)
    return _visual_service


def generate_image(prompt, negative_prompt=None, timeout=90):
    """调用即梦 API 生成图片（异步提交 + 轮询）。

    Returns:
        ImageGenResult
    """
    svc = _get_visual_service()
    if svc is None:
        return ImageGenResult(success=False, error="Image gen API not configured (missing AK/SK)")

    try:
        # Step 1: 提交异步任务
        submit_form = {
            "req_key": _REQ_KEY,
            "prompt": prompt,
            "width": 1024,
            "height": 1024,
            "force_single": True,
        }

        result = svc.cv_sync2async_submit_task(submit_form)

        resp_code = result.get("code")
        if resp_code != 10000:
            return ImageGenResult(
                success=False,
                error=f"Submit failed: code={resp_code}, msg={result.get('message', '')}",
            )

        task_id = result.get("data", {}).get("task_id")
        if not task_id:
            return ImageGenResult(success=False, error=f"No task_id: {json.dumps(result)[:200]}")

        # Step 2: 轮询结果
        return _poll_result(svc, task_id, timeout)

    except Exception as e:
        return ImageGenResult(success=False, error=str(e)[:300])


def _poll_result(svc, task_id, max_wait=90):
    """轮询即梦异步任务结果。"""
    import urllib.request

    start = time.time()
    while time.time() - start < max_wait:
        time.sleep(3)
        try:
            poll_form = {
                "req_key": _REQ_KEY,
                "task_id": task_id,
                "req_json": json.dumps({"return_url": True, "logo_info": {"add_logo": False}}),
            }
            result = svc.cv_sync2async_get_result(poll_form)

            data = result.get("data", {})
            status = data.get("status")

            if status == "done":
                # 优先用 URL 下载
                image_urls = data.get("image_urls", [])
                if image_urls:
                    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                    resp = opener.open(image_urls[0], timeout=15)
                    image_bytes = resp.read()
                    return ImageGenResult(
                        success=True,
                        image_bytes=image_bytes,
                        prompt="",
                        model=_REQ_KEY,
                    )
                # fallback: base64
                bin_list = data.get("binary_data_base64", [])
                if bin_list:
                    image_bytes = base64.b64decode(bin_list[0])
                    return ImageGenResult(
                        success=True,
                        image_bytes=image_bytes,
                        prompt="",
                        model=_REQ_KEY,
                    )
                return ImageGenResult(success=False, error="Done but no image data")

            elif status in ("not_found", "expired"):
                return ImageGenResult(success=False, error=f"Task {status}")

        except Exception as e:
            print(f"[image_gen] Poll error: {e}")

    return ImageGenResult(success=False, error="Polling timeout")


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
