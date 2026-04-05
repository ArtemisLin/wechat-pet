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

    # 文字信息
    try:
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
