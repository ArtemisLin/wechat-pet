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
    draw.rounded_rectangle(xy, radius=radius, fill=fill)


def personality_sign_card(character_path, pet_name, species_name, species_emoji,
                          trait_tags, trait_desc, size=(1024, 1024)):
    """性格签卡：类似 MBTI 结果卡。"""
    canvas = Image.new("RGBA", size, (250, 245, 255, 255))
    draw = ImageDraw.Draw(canvas)

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

    _draw_centered(draw, "你孵出了一只", font_title, (100, 100, 100), size[0], 530)
    _draw_centered(draw, f"{species_emoji} {species_name} · {pet_name}", font_name, (60, 60, 60), size[0], 585)
    _draw_centered(draw, trait_tags, font_tags, (130, 100, 180), size[0], 660)

    if trait_desc:
        lines = _wrap_text(trait_desc, 30)
        y = 720
        for line in lines[:3]:
            _draw_centered(draw, line, font_desc, (120, 120, 120), size[0], y)
            y += 35

    _draw_centered(draw, "看看你会孵出什么样的宠物？", font_cta, (180, 160, 200), size[0], size[1] - 80)

    return canvas


def pet_profile_card(character_path, pet_name, species_name, species_emoji,
                     trait_tags, ai_tagline, days_together, size=(1024, 600)):
    """宠物名片：横向布局，左半角色图，右半信息。"""
    canvas = Image.new("RGBA", size, (255, 255, 255, 255))
    draw = ImageDraw.Draw(canvas)
    _draw_rounded_rect(draw, (20, 20, size[0]-20, size[1]-20), 20, (248, 248, 252, 255))

    if character_path and os.path.exists(character_path):
        char_img = Image.open(character_path).convert("RGBA")
        char_img = char_img.resize((350, 350), Image.LANCZOS)
        canvas.paste(char_img, (60, 120), char_img)

    font_name = _load_font(48)
    font_info = _load_font(28)
    font_tag = _load_font(24)
    font_quote = _load_font(22)

    right_x = 460

    draw.text((right_x, 120), f"{species_emoji} {pet_name}", fill=(40, 40, 40), font=font_name)
    draw.text((right_x, 185), species_name, fill=(120, 120, 120), font=font_info)
    draw.text((right_x, 240), trait_tags, fill=(130, 100, 180), font=font_tag)

    if ai_tagline:
        draw.text((right_x, 300), f"\u300c{ai_tagline}\u300d", fill=(150, 150, 150), font=font_quote)

    draw.text((right_x, 380), f"\u5728\u4e00\u8d77 {days_together} \u5929", fill=(180, 180, 180), font=font_tag)

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
    draw.rounded_rectangle((15, 15, size[0]-15, size[1]-15), radius=20, outline=border, width=3)

    font_title = _load_font(40)
    font_name = _load_font(32)
    font_desc = _load_font(24)

    _draw_centered(draw, "\U0001f3c6 \u6210\u5c31\u89e3\u9501\uff01", font_title, (80, 80, 80), size[0], 60)
    _draw_centered(draw, achievement_name, font_name, (40, 40, 40), size[0], 130)
    _draw_centered(draw, achievement_desc, font_desc, (120, 120, 120), size[0], 190)

    if character_path and os.path.exists(character_path):
        char_img = Image.open(character_path).convert("RGBA")
        char_img = char_img.resize((280, 280), Image.LANCZOS)
        x = (size[0] - 280) // 2
        canvas.paste(char_img, (x, 260), char_img)

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

    _draw_centered(draw, f"\U0001f4cb {pet_name}\u7684\u4e00\u5468\u5c0f\u7ed3", font_title, (60, 60, 60), size[0], 40)

    if highlight_text:
        _draw_centered(draw, "\u2728 \u672c\u5468\u540d\u573a\u9762", font_body, (100, 100, 100), size[0], 100)
        lines = _wrap_text(highlight_text, 35)
        y = 140
        for line in lines[:3]:
            _draw_centered(draw, line, font_small, (120, 120, 120), size[0], y)
            y += 30

    if character_path and os.path.exists(character_path):
        char_img = Image.open(character_path).convert("RGBA")
        char_img = char_img.resize((300, 300), Image.LANCZOS)
        x = (size[0] - 300) // 2
        canvas.paste(char_img, (x, 240), char_img)

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
