"""素材管理器：统一的图片路径解析。

优先级：
  1. AI 生成的缓存图（data/{user_id}/images/{key}.png）
  2. 品种预制图（assets/{species_id}/{key}.png）
  3. 默认预制图（assets/penguin/{key}.png）

成长阶段解锁：
  - 孵化完成：base, idle, happy, sleeping
  - baby→child: eating, bathing
  - child→teen: playing, exploring
  - teen→adult: sick
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
