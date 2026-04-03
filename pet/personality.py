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
