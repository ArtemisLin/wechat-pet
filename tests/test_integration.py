"""集成测试：验证多用户 + 多品种的完整流程。"""
import sys, os, tempfile, shutil
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'pet'))

# 设置环境变量避免 AI 调用
os.environ.setdefault("AI_API_KEY", "test")
os.environ.setdefault("AI_BASE_URL", "http://localhost:9999")
os.environ.setdefault("AI_MODEL", "test")

from store import PetRegistry


USER_A = "user_a@test"
USER_B = "user_b@test"


class TestMultiUserIntegration:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.registry = PetRegistry(self.tmpdir)

    def teardown_method(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_two_users_different_species(self):
        """两个用户各自领养不同品种的宠物"""
        store_a = self.registry.get_or_create(USER_A)
        store_b = self.registry.get_or_create(USER_B)

        store_a.create_egg(USER_A, "UserA", "fox")
        store_b.create_egg(USER_B, "UserB", "dragon")

        assert store_a.pet["species"] == "fox"
        assert store_b.pet["species"] == "dragon"

    def test_users_dont_interfere(self):
        """一个用户的操作不影响另一个"""
        store_a = self.registry.get_or_create(USER_A)
        store_b = self.registry.get_or_create(USER_B)

        store_a.create_egg(USER_A, "A", "penguin")
        store_a.hatch("谷谷A")
        store_a.pet["hunger"] = 30
        store_a.feed()

        store_b.create_egg(USER_B, "B", "owl")
        store_b.hatch("谷谷B")

        # B 的 hunger 应该还是 100（初始值）
        assert store_b.pet["hunger"] == 100
        # A 的 hunger 应该大于 30
        assert store_a.pet["hunger"] > 30

    def test_species_name_in_pet_name(self):
        """未命名时用品种名"""
        store = self.registry.get_or_create(USER_A)
        store.create_egg(USER_A, "A", "fox")
        # egg 阶段 name 是 None
        assert store.get_pet_name() == "小狐狸"

        store.hatch("小七")
        assert store.get_pet_name() == "小七"

    def test_registry_persistence(self):
        """注册表重启后能恢复用户"""
        store = self.registry.get_or_create(USER_A)
        store.create_egg(USER_A, "A", "dragon")
        store.hatch("大龙")

        # 模拟重启
        registry2 = PetRegistry(self.tmpdir)
        stores = registry2.all_active_stores()
        assert len(stores) == 1
        assert stores[0].pet["name"] == "大龙"
        assert stores[0].pet["species"] == "dragon"

    def test_full_lifecycle(self):
        """完整生命周期：创建 → 孵化 → 喂食 → 洗澡 → 玩耍 → 治疗"""
        store = self.registry.get_or_create(USER_A)
        store.create_egg(USER_A, "Owner", "rabbit")
        store.hatch("小白")

        # 喂食
        store.pet["hunger"] = 50
        result = store.feed()
        assert result is not None
        assert result[1] > 50

        # 洗澡
        store.pet["cleanliness"] = 40
        result = store.bathe()
        assert result is not None
        assert result[1] > 40

        # 玩耍
        result = store.play()
        assert result is not None
        assert result != "no_stamina"

        # 治疗
        store.pet["health"] = 60
        result = store.heal()
        assert result is not None
        assert result[1] > 60

    def test_decay_per_user(self):
        """每个用户的衰减独立"""
        sa = self.registry.get_or_create(USER_A)
        sb = self.registry.get_or_create(USER_B)
        sa.create_egg(USER_A, "A", "penguin")
        sa.hatch("AA")
        sb.create_egg(USER_B, "B", "fox")
        sb.hatch("BB")

        sa.pet["hunger"] = 80
        sb.pet["hunger"] = 80

        # A 衰减
        sa.decay_all()
        # B 不应该受影响
        assert sb.pet["hunger"] == 80  # B 没调用 decay_all

    def test_record_action_and_achievements(self):
        """成就系统在多用户下正常工作"""
        store = self.registry.get_or_create(USER_A)
        store.create_egg(USER_A, "A", "dinosaur")
        store.hatch("恐恐")

        # 首次喂食应该触发 first_feed 成就
        store.feed()
        unlocked = store.record_action("feed")
        ach_names = [a["name"] for a in unlocked]
        assert "第一口饭" in ach_names

    def test_format_collection(self):
        """收藏品格式化"""
        store = self.registry.get_or_create(USER_A)
        store.create_egg(USER_A, "A", "owl")
        store.hatch("咕咕")

        # 空背包
        result = store.format_collection()
        assert "空空" in result

    def test_format_diary_empty(self):
        """空日记"""
        store = self.registry.get_or_create(USER_A)
        store.create_egg(USER_A, "A", "penguin")
        store.hatch("企企")

        result = store.format_diary()
        assert "空" in result
