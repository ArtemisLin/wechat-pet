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
