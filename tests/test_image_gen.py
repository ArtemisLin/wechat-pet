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
