import sys, os, tempfile, shutil
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'pet'))

from invite import InviteManager


class TestInviteManager:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.mgr = InviteManager(self.tmpdir)

    def teardown_method(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_generate_code_format(self):
        code = self.mgr.generate_code("user1")
        assert len(code) == 4
        assert code.isalnum()

    def test_generate_code_unique(self):
        codes = set()
        for i in range(20):
            c = self.mgr.generate_code(f"user{i}")
            codes.add(c)
        assert len(codes) == 20

    def test_validate_code(self):
        code = self.mgr.generate_code("user1")
        result = self.mgr.validate_code(code)
        assert result is not None
        assert result["inviter"] == "user1"

    def test_validate_invalid_code(self):
        result = self.mgr.validate_code("ZZZZ")
        assert result is None

    def test_use_code(self):
        code = self.mgr.generate_code("user1")
        ok = self.mgr.use_code(code, "user2")
        assert ok is True
        # Code should be consumed
        result = self.mgr.validate_code(code)
        assert result["used_by"] == "user2"

    def test_use_code_self_invite_rejected(self):
        code = self.mgr.generate_code("user1")
        ok = self.mgr.use_code(code, "user1")
        assert ok is False

    def test_user_codes_count(self):
        self.mgr.generate_code("user1")
        self.mgr.generate_code("user1")
        codes = self.mgr.get_user_codes("user1")
        assert len(codes) == 2

    def test_persistence(self):
        code = self.mgr.generate_code("user1")
        mgr2 = InviteManager(self.tmpdir)
        result = mgr2.validate_code(code)
        assert result is not None
