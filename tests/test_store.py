import sys, os, json, tempfile, shutil
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'pet'))

from store import UserPetStore, PetRegistry

TEST_USER_A = "user_a@test"
TEST_USER_B = "user_b@test"


class TestUserPetStore:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.store = UserPetStore(TEST_USER_A, self.tmpdir)

    def teardown_method(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_creates_user_directory(self):
        user_dir = os.path.join(self.tmpdir, TEST_USER_A)
        assert os.path.isdir(user_dir)

    def test_initial_state_is_empty(self):
        assert self.store.pet is None
        assert self.store.owner == {}

    def test_create_egg_and_save(self):
        ok = self.store.create_egg(TEST_USER_A, "TestOwner", "penguin")
        assert ok is True
        assert self.store.pet is not None
        assert self.store.pet["species"] == "penguin"
        assert self.store.pet["stage"] == "egg"
        # Verify file written
        data_file = os.path.join(self.tmpdir, TEST_USER_A, "pet.json")
        assert os.path.exists(data_file)
        with open(data_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["schema_version"] == 4
        assert data["pet"]["species"] == "penguin"

    def test_hatch_sets_name(self):
        self.store.create_egg(TEST_USER_A, "TestOwner", "fox")
        ok = self.store.hatch("小七")
        assert ok is True
        assert self.store.pet["name"] == "小七"
        assert self.store.pet["stage"] == "baby"
        assert self.store.pet["species"] == "fox"

    def test_feed_increases_hunger(self):
        self.store.create_egg(TEST_USER_A, "TestOwner", "penguin")
        self.store.hatch("谷谷")
        self.store.pet["hunger"] = 50
        result = self.store.feed()
        assert result is not None
        old, new = result
        assert new > old

    def test_atomic_save(self):
        """验证 save 是原子操作（先写 tmp 再 replace）"""
        self.store.create_egg(TEST_USER_A, "TestOwner", "penguin")
        data_file = os.path.join(self.tmpdir, TEST_USER_A, "pet.json")
        assert os.path.exists(data_file)
        # tmp 文件不应残留
        tmp_file = data_file + ".tmp"
        assert not os.path.exists(tmp_file)


class TestPetRegistry:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.registry = PetRegistry(self.tmpdir)

    def teardown_method(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_get_or_create_returns_store(self):
        store = self.registry.get_or_create(TEST_USER_A)
        assert isinstance(store, UserPetStore)

    def test_same_user_returns_same_instance(self):
        s1 = self.registry.get_or_create(TEST_USER_A)
        s2 = self.registry.get_or_create(TEST_USER_A)
        assert s1 is s2

    def test_different_users_get_different_stores(self):
        sa = self.registry.get_or_create(TEST_USER_A)
        sb = self.registry.get_or_create(TEST_USER_B)
        assert sa is not sb

    def test_all_stores_returns_active(self):
        self.registry.get_or_create(TEST_USER_A)
        self.registry.get_or_create(TEST_USER_B)
        stores = self.registry.all_stores()
        assert len(stores) == 2

    def test_loads_existing_users_on_init(self):
        # Create a user via store
        s = self.registry.get_or_create(TEST_USER_A)
        s.create_egg(TEST_USER_A, "Owner", "penguin")
        # New registry instance should discover the existing user
        registry2 = PetRegistry(self.tmpdir)
        stores = registry2.all_stores()
        assert len(stores) >= 1
