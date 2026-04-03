import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'pet'))

from species import SPECIES, get_species, ALL_SPECIES_IDS


def test_six_species_defined():
    assert len(SPECIES) == 6


def test_all_species_have_required_fields():
    required = {"name", "emoji", "description", "personality_hint", "baseline_traits"}
    trait_keys = {"extrovert", "brave", "greedy", "curious", "blunt"}
    for sid, spec in SPECIES.items():
        assert required.issubset(spec.keys()), f"{sid} missing fields"
        assert trait_keys == set(spec["baseline_traits"].keys()), f"{sid} bad traits"
        for v in spec["baseline_traits"].values():
            assert 0.1 <= v <= 0.9, f"{sid} trait out of range"


def test_get_species_returns_copy():
    s = get_species("penguin")
    assert s is not None
    s["name"] = "hacked"
    assert get_species("penguin")["name"] != "hacked"


def test_get_species_unknown():
    assert get_species("unicorn") is None


def test_all_species_ids():
    assert len(ALL_SPECIES_IDS) == 6
    assert "penguin" in ALL_SPECIES_IDS
