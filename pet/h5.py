"""轻量成长册 H5 页面生成。

V1 只做静态 HTML 生成，不需要 Flask 服务器。
生成到 data/{user_id}/h5/index.html。
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
