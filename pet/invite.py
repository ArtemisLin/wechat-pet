"""邀请码系统。

4 位字母+数字码。每个用户初始 1 个码，通过成就/分享获取更多。
数据存储在 {data_dir}/invites.json（全局，非 per-user）。
"""

import json
import os
import random
import string
import threading


class InviteManager:
    """邀请码管理器。"""

    def __init__(self, data_dir):
        self.data_file = os.path.join(data_dir, "invites.json")
        self._lock = threading.RLock()
        self._data = self._load()

    def _load(self):
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return {"codes": {}, "user_codes": {}}

    def _save(self):
        tmp = self.data_file + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.data_file)

    def _gen_unique_code(self):
        """生成一个唯一的 4 位码。"""
        chars = string.ascii_uppercase + string.digits
        for _ in range(100):
            code = "".join(random.choices(chars, k=4))
            if code not in self._data["codes"]:
                return code
        raise RuntimeError("Unable to generate unique invite code")

    def generate_code(self, user_id):
        """为用户生成一个邀请码。"""
        with self._lock:
            code = self._gen_unique_code()
            self._data["codes"][code] = {
                "inviter": user_id,
                "used_by": None,
                "created_at": _now_str(),
                "used_at": None,
            }
            if user_id not in self._data["user_codes"]:
                self._data["user_codes"][user_id] = []
            self._data["user_codes"][user_id].append(code)
            self._save()
            return code

    def validate_code(self, code):
        """验证邀请码。返回码信息或 None。"""
        with self._lock:
            return self._data["codes"].get(code.upper())

    def use_code(self, code, new_user_id):
        """使用邀请码。返回 True/False。"""
        with self._lock:
            code = code.upper()
            info = self._data["codes"].get(code)
            if not info:
                return False
            if info["used_by"]:
                return False  # 已被使用
            if info["inviter"] == new_user_id:
                return False  # 不能自己邀请自己
            info["used_by"] = new_user_id
            info["used_at"] = _now_str()
            self._save()
            return True

    def get_user_codes(self, user_id):
        """获取用户的所有邀请码。"""
        with self._lock:
            codes = self._data["user_codes"].get(user_id, [])
            return [{"code": c, **self._data["codes"].get(c, {})} for c in codes]

    def get_available_codes(self, user_id):
        """获取用户未使用的邀请码。"""
        return [c for c in self.get_user_codes(user_id) if not c.get("used_by")]

    def get_inviter(self, code):
        """获取邀请者 user_id。"""
        info = self._data["codes"].get(code.upper())
        return info["inviter"] if info else None


def _now_str():
    try:
        from config import now_str
        return now_str()
    except ImportError:
        from datetime import datetime
        return datetime.now().isoformat()
