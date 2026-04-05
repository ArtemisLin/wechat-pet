import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'pet'))

from quota import QuotaManager, DegradationLevel


def test_initial_quota():
    qm = QuotaManager(stars=100, companion_energy=100)
    assert qm.stars == 100
    assert qm.companion_energy == 100


def test_spend_stars():
    qm = QuotaManager(stars=100, companion_energy=100)
    assert qm.can_spend_stars(10)
    assert qm.spend_stars(10)
    assert qm.stars == 90


def test_spend_stars_insufficient():
    qm = QuotaManager(stars=5, companion_energy=100)
    assert not qm.can_spend_stars(10)
    assert not qm.spend_stars(10)
    assert qm.stars == 5  # unchanged


def test_spend_companion():
    qm = QuotaManager(stars=100, companion_energy=10)
    assert qm.can_spend_companion(1)
    assert qm.spend_companion(1)
    assert qm.companion_energy == 9


def test_daily_reset():
    qm = QuotaManager(stars=50, companion_energy=0)
    qm.daily_reset()
    assert qm.companion_energy == 100
    assert qm.stars == 50  # stars NOT reset


def test_degradation_normal():
    qm = QuotaManager(stars=100, companion_energy=100)
    assert qm.degradation_level() == DegradationLevel.NORMAL


def test_degradation_light():
    qm = QuotaManager(stars=20, companion_energy=100, initial_stars=100)
    assert qm.degradation_level() == DegradationLevel.LIGHT


def test_degradation_medium():
    qm = QuotaManager(stars=5, companion_energy=100, initial_stars=100)
    assert qm.degradation_level() == DegradationLevel.MEDIUM


def test_degradation_deep():
    qm = QuotaManager(stars=0, companion_energy=0, initial_stars=100)
    assert qm.degradation_level() == DegradationLevel.DEEP


def test_recharge():
    qm = QuotaManager(stars=10, companion_energy=50)
    qm.recharge_stars(50)
    assert qm.stars == 60


def test_to_dict_and_from_dict():
    qm = QuotaManager(stars=42, companion_energy=88, initial_stars=100)
    d = qm.to_dict()
    qm2 = QuotaManager.from_dict(d)
    assert qm2.stars == 42
    assert qm2.companion_energy == 88
    assert qm2.initial_stars == 100
