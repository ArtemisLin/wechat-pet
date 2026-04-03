"""V1 → V2 数据迁移：将 pet_data.json 迁移到 data/{user_id}/pet.json。

用法：py migrate_v1.py
"""
import sys
import io
import json
import os
import shutil

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OLD_FILE = os.path.join(BASE_DIR, "pet_data.json")
DATA_DIR = os.path.join(BASE_DIR, "data")


def migrate():
    if not os.path.exists(OLD_FILE):
        print("没有找到旧的 pet_data.json，无需迁移。")
        return

    with open(OLD_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    owner = data.get("owner", {})
    user_id = owner.get("user_id")
    if not user_id:
        print("旧数据中没有 owner.user_id，无法迁移。")
        return

    # 创建用户目录
    user_dir = os.path.join(DATA_DIR, user_id)
    os.makedirs(user_dir, exist_ok=True)

    # 升级 schema
    pet = data.get("pet", {})
    if "species" not in pet:
        pet["species"] = "penguin"
    data["pet"] = pet
    data["schema_version"] = 4

    # 写入新位置
    new_file = os.path.join(user_dir, "pet.json")
    with open(new_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # 备份旧文件
    backup = OLD_FILE + ".migrated"
    shutil.move(OLD_FILE, backup)

    print(f"迁移完成！")
    print(f"  用户 ID: {user_id}")
    print(f"  品种: {pet.get('species', 'penguin')}")
    print(f"  新位置: {new_file}")
    print(f"  旧文件已备份为: {backup}")


if __name__ == "__main__":
    migrate()
