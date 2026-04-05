"""额度系统：双能量（陪伴能量 + 创作星星）+ 渐进降级。

存储在 pet.json 的 quota 字段：
  pet.quota = {
      "stars": 100,
      "companion_energy": 100,
      "initial_stars": 100,
      "total_recharged": 0,
  }
"""

from enum import Enum


class DegradationLevel(Enum):
    NORMAL = "normal"    # 全功能
    LIGHT = "light"      # AI 回复变短，闲聊减少
    MEDIUM = "medium"    # 不生成新图片和精装卡
    DEEP = "deep"        # 预制模板回复


# 消耗常量
COST_AI_CHAT = 1           # 陪伴能量
COST_IMAGE_GEN = 10        # 星星
COST_SHARE_CARD = 3        # 星星
COST_VOICE = 5             # 星星
COST_EXPLORE_STORY = 2     # 星星
COST_DIARY = 1             # 星星
COST_WEEKLY_REPORT = 2     # 星星

# 每日恢复
DAILY_COMPANION_ENERGY = 100

# 降级阈值（基于 initial_stars 的百分比）
LIGHT_THRESHOLD = 0.30
MEDIUM_THRESHOLD = 0.10


class QuotaManager:
    """额度管理器。每个用户一个实例。

    用法：
        qm = QuotaManager.from_dict(store.pet.get("quota", {}))
        if qm.can_spend_stars(COST_IMAGE_GEN):
            qm.spend_stars(COST_IMAGE_GEN)
            store.pet["quota"] = qm.to_dict()
            store._save()
    """

    def __init__(self, stars=100, companion_energy=100, initial_stars=100, total_recharged=0):
        self.stars = stars
        self.companion_energy = companion_energy
        self.initial_stars = initial_stars or 100
        self.total_recharged = total_recharged

    @classmethod
    def from_dict(cls, d):
        if not d:
            return cls()
        return cls(
            stars=d.get("stars", 100),
            companion_energy=d.get("companion_energy", 100),
            initial_stars=d.get("initial_stars", 100),
            total_recharged=d.get("total_recharged", 0),
        )

    def to_dict(self):
        return {
            "stars": self.stars,
            "companion_energy": self.companion_energy,
            "initial_stars": self.initial_stars,
            "total_recharged": self.total_recharged,
        }

    def can_spend_stars(self, amount):
        return self.stars >= amount

    def spend_stars(self, amount):
        if self.stars < amount:
            return False
        self.stars -= amount
        return True

    def can_spend_companion(self, amount=1):
        return self.companion_energy >= amount

    def spend_companion(self, amount=1):
        if self.companion_energy < amount:
            return False
        self.companion_energy -= amount
        return True

    def daily_reset(self):
        """每日重置陪伴能量（星星不重置）。"""
        self.companion_energy = DAILY_COMPANION_ENERGY

    def recharge_stars(self, amount):
        """充值星星。"""
        self.stars += amount
        self.total_recharged += amount

    def degradation_level(self):
        """计算当前降级等级。"""
        if self.stars <= 0 and self.companion_energy <= 0:
            return DegradationLevel.DEEP

        star_ratio = self.stars / max(self.initial_stars, 1)

        if star_ratio < MEDIUM_THRESHOLD:
            return DegradationLevel.MEDIUM
        elif star_ratio < LIGHT_THRESHOLD:
            return DegradationLevel.LIGHT
        else:
            return DegradationLevel.NORMAL

    def format_status(self):
        """格式化额度状态显示。"""
        stars_display = f"⭐ 星星：{self.stars}"
        energy_bar = "🔋" * max(1, self.companion_energy // 20) if self.companion_energy > 0 else "🪫"
        energy_display = f"💬 陪伴能量：{energy_bar} ({self.companion_energy})"

        level = self.degradation_level()
        if level == DegradationLevel.DEEP:
            status = "😴 犯困中...补充星星让我恢复活力吧"
        elif level == DegradationLevel.MEDIUM:
            status = "😪 有点累了...高级功能暂时休息中"
        elif level == DegradationLevel.LIGHT:
            status = "🙂 还好，但星星不太够了"
        else:
            status = "✨ 状态很好！"

        return f"{stars_display}\n{energy_display}\n{status}"
