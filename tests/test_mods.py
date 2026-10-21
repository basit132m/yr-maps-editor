"""Upgrades must change exactly what they claim and nothing else."""

import pytest

from app.inifile import IniFile
from app.mapfile import MapError, YRMap
from app.mods import BY_ID, REGISTRY
from app.mods.auto_repair import BUILDINGS
from app.mods.money import CONSTRUCTION_YARDS, INCOME_DELAY, INCOME_RATES

BINARY_SECTIONS = ("IsoMapPack5", "OverlayPack", "Digest")


def apply_all(map_bytes, options):
    ymap = YRMap.load(map_bytes)
    for mod in REGISTRY:
        mod.apply(ymap, options)
    return ymap


def test_map_info(map_bytes):
    info = YRMap.load(map_bytes).info()
    assert info.name == "Tournament Island"
    assert info.author == "Westwood"
    assert (info.width, info.height) == (116, 112)
    assert info.players == 4
    assert info.is_multiplayer
    assert info.has_terrain_data


@pytest.mark.parametrize("bad, reason", [
    (b"", "empty"),
    (b"just some text\r\nnot a map\r\n", "no sections"),
    (b"[Basic]\r\nName=X\r\n", "no [Map]"),
    (b"[Map]\r\nSize=0,0,1,1\r\n", "no [Basic]"),
    (b"MZ\x00\x00binary garbage" + b"\x00" * 50, "binary"),
])
def test_rejects_non_maps(bad, reason):
    with pytest.raises(MapError):
        YRMap.load(bad)


def test_binary_sections_are_never_touched(map_bytes, all_options):
    before = IniFile.from_bytes(map_bytes)
    after = apply_all(map_bytes, all_options).ini
    for section in BINARY_SECTIONS:
        assert before.items(section) == after.items(section), section


def test_only_expected_sections_are_added(map_bytes, all_options):
    before = set(IniFile.from_bytes(map_bytes).sections())
    after = set(apply_all(map_bytes, all_options).ini.sections())
    assert after - before == {"ForcedOptions", "General", "IQ", *BUILDINGS}


def test_forced_options_written(map_bytes, all_options):
    ini = apply_all(map_bytes, all_options).ini
    assert ini.get("ForcedOptions", "chkAutoRepair") == "true"
    assert ini.get("ForcedOptions", "cmbCredits") == "0"
    assert ini.get("ForcedOptions", "cmbGameSpeedCapSkirmish") == "0"
    assert ini.get("ForcedOptions", "cmbGameSpeedCapMultiplayer") == "0"
    assert ini.get("ForcedOptions", "chkDisableGameSpeed") == "true"


def test_every_building_gets_self_healing(map_bytes, all_options):
    ini = apply_all(map_bytes, all_options).ini
    for building in BUILDINGS:
        assert ini.get(building, "SelfHealing") == "yes", building


def test_applying_twice_changes_nothing_more(map_bytes, all_options):
    once = apply_all(map_bytes, all_options)
    snapshot = once.to_bytes()
    for mod in REGISTRY:
        mod.apply(once, all_options)
    assert once.to_bytes() == snapshot


def test_no_upgrades_selected_leaves_file_untouched(map_bytes):
    ymap = YRMap.load(map_bytes)
    off = {"forced_option": "0", "structures": "0", "lock": "0"}
    BY_ID["auto_repair"].apply(ymap, off)
    assert ymap.to_bytes() == map_bytes


def test_unknown_choice_falls_back_to_default(map_bytes):
    ymap = YRMap.load(map_bytes)
    BY_ID["money"].apply(ymap, {"starting": "1", "credits": "; injected", "income": "1", "rate": "<script>"})
    BY_ID["game_speed"].apply(ymap, {"speed": "../../etc/passwd"})
    assert ymap.ini.get("ForcedOptions", "cmbCredits") == "0"
    assert ymap.ini.get("ForcedOptions", "cmbGameSpeedCapSkirmish") == "0"


def test_existing_forced_options_are_updated_not_duplicated(map_bytes):
    raw = map_bytes + b"\r\n[ForcedOptions]\r\ncmbCredits=8\r\nchkCrates=false\r\n"
    ymap = YRMap.load(raw)
    BY_ID["money"].apply(ymap, {"starting": "1", "credits": "0"})
    assert ymap.ini.items("ForcedOptions") == [("cmbCredits", "0"), ("chkCrates", "false")]


def test_renaming_marks_the_map_as_edited(map_bytes):
    ymap = YRMap.load(map_bytes)
    ymap.set_display_name("Tournament Island [Edited]")
    assert ymap.ini.get("Basic", "Name") == "Tournament Island [Edited]"


def test_output_is_still_a_loadable_map(map_bytes, all_options):
    reloaded = YRMap.load(apply_all(map_bytes, all_options).to_bytes())
    assert reloaded.info().players == 4


def test_income_is_written_to_every_construction_yard(map_bytes, all_options):
    ini = apply_all(map_bytes, all_options).ini
    amount, startup = INCOME_RATES["generous"]
    for yard in CONSTRUCTION_YARDS:
        assert ini.get(yard, "ProduceCashAmount") == str(amount), yard
        assert ini.get(yard, "ProduceCashDelay") == str(INCOME_DELAY), yard
        assert ini.get(yard, "ProduceCashStartup") == str(startup), yard


@pytest.mark.parametrize("rate", sorted(INCOME_RATES))
def test_every_rate_satisfies_the_engine_requirements(map_bytes, rate):
    """Delay must exceed 1 and startup must be non-zero, or no cash is paid."""
    ymap = YRMap.load(map_bytes)
    BY_ID["money"].apply(ymap, {"income": "1", "rate": rate})
    for yard in CONSTRUCTION_YARDS:
        assert int(ymap.ini.get(yard, "ProduceCashDelay")) > 1
        assert int(ymap.ini.get(yard, "ProduceCashStartup")) != 0
        assert int(ymap.ini.get(yard, "ProduceCashAmount")) > 0


def test_income_works_without_any_cncnet_keys(map_bytes):
    """A vanilla-only user gets money with no [ForcedOptions] written."""
    ymap = YRMap.load(map_bytes)
    BY_ID["money"].apply(ymap, {"income": "1", "rate": "steady"})
    assert ymap.ini.get("GACNST", "ProduceCashAmount") == "50"
    assert not ymap.ini.has_section("ForcedOptions")


def test_build_speed_override_is_written(map_bytes, all_options):
    ini = apply_all(map_bytes, all_options).ini
    assert ini.get("General", "BuildSpeed") == "0.35"


def test_build_speed_can_be_left_alone(map_bytes):
    ymap = YRMap.load(map_bytes)
    BY_ID["game_speed"].apply(ymap, {"speed": "normal", "build_speed": "normal"})
    assert ymap.ini.get("General", "BuildSpeed") is None


# -- merging into maps that already carry rules overrides --------------------


def test_existing_general_keys_survive(modded_map_bytes, all_options):
    ini = apply_all(modded_map_bytes, all_options).ini
    assert ini.get("General", "GrowthRate") == "1"
    assert ini.get("General", "RepairPercent") == "0%"


def test_existing_build_speed_is_replaced_not_duplicated(modded_map_bytes, all_options):
    ini = apply_all(modded_map_bytes, all_options).ini
    assert ini.get("General", "BuildSpeed") == "0.35"
    assert [k for k, _ in ini.items("General")].count("BuildSpeed") == 1


def test_building_keeps_its_tuning_when_given_self_healing(modded_map_bytes, all_options):
    ini = apply_all(modded_map_bytes, all_options).ini
    for section in ("GACNST", "GAGATE_A"):
        assert ini.get(section, "Strength") == "1000", section
        assert ini.get(section, "SelfHealing") == "yes", section


def test_another_buildings_income_is_left_alone(modded_map_bytes, all_options):
    """Income goes on Construction Yards; a map's own Oil Derrick tuning stays."""
    ini = apply_all(modded_map_bytes, all_options).ini
    assert ini.get("CAOILD", "ProduceCashAmount") == "100"
    assert ini.get("CAOILD", "ProduceCashDelay") == "100"


def test_no_key_is_ever_lost(modded_map_bytes, all_options):
    before = IniFile.from_bytes(modded_map_bytes)
    after = apply_all(modded_map_bytes, all_options).ini
    for section in before.sections():
        missing = {k.lower() for k, _ in before.items(section)} - {
            k.lower() for k, _ in after.items(section)
        }
        assert not missing, (section, missing)


def test_no_duplicate_keys_are_introduced(modded_map_bytes, all_options):
    """Upgrades add no repeated key.

    Maps in the wild do contain duplicates already — the engine honours the
    first — so this compares against the original rather than demanding the
    output be free of them.
    """
    def duplicate_count(ini, section):
        keys = [k.lower() for k, _ in ini.items(section)]
        return len(keys) - len(set(keys))

    before = IniFile.from_bytes(modded_map_bytes)
    after = apply_all(modded_map_bytes, all_options).ini
    for section in after.sections():
        assert duplicate_count(after, section) == duplicate_count(before, section), section


# -- warnings the analysis raises ------------------------------------------


def test_plain_map_is_not_flagged_as_heavily_modified(map_bytes):
    info = YRMap.load(map_bytes).info()
    assert not info.heavily_modified
    assert info.existing_income == []


def test_conversion_is_flagged_as_heavily_modified(map_bytes):
    from app.mapfile import HEAVILY_MODIFIED_THRESHOLD
    extra = "".join(
        f"\r\n[CUSTOM{n}]\r\nStrength=100\r\n"
        for n in range(HEAVILY_MODIFIED_THRESHOLD)
    ).encode("latin-1")
    assert YRMap.load(map_bytes + extra).info().heavily_modified


def test_existing_income_is_detected(map_bytes):
    raw = map_bytes + (
        b"\r\n[CAOILD]\r\nProduceCashAmount=750\r\nProduceCashDelay=100\r\n"
    )
    assert YRMap.load(raw).info().existing_income == [("CAOILD", "750")]


def test_zero_income_is_not_reported(map_bytes):
    raw = map_bytes + b"\r\n[CAOILD]\r\nProduceCashAmount=0\r\n"
    assert YRMap.load(raw).info().existing_income == []


def test_lighting_tweaks_do_not_count_as_a_conversion(map_bytes):
    """Maps retint light posts for mood; that is not a gameplay change."""
    from app.mapfile import LIGHTING_SECTIONS
    extra = "".join(
        f"\r\n[{name.upper()}]\r\nLightIntensity=0.01\r\nLightVisibility=2500\r\n"
        for name in LIGHTING_SECTIONS
    ).encode("latin-1")
    info = YRMap.load(map_bytes + extra).info()
    assert len(info.rules_overrides) == len(LIGHTING_SECTIONS)
    assert info.gameplay_overrides == []
    assert not info.heavily_modified


# -- repair --------------------------------------------------------------


def test_fast_repair_makes_repairing_free_and_quick(map_bytes, all_options):
    from app.mods.auto_repair import REPAIR_PERCENT, REPAIR_RATE, REPAIR_STEP
    ini = apply_all(map_bytes, all_options).ini
    assert ini.get("General", "RepairPercent") == REPAIR_PERCENT
    assert ini.get("General", "RepairStep") == REPAIR_STEP
    assert ini.get("General", "RepairRate") == REPAIR_RATE


def test_repair_step_cannot_crash_the_game(map_bytes):
    """A RepairStep above a structure's Strength crashes the engine when
    that structure is damaged and repair starts. Walls are the weakest
    buildings in the game, so the value has to stay well under them."""
    from app.mods.auto_repair import REPAIR_STEP
    assert 0 < int(REPAIR_STEP) <= 35


def test_repair_is_faster_than_retail(map_bytes):
    """Retail RepairRate is 0.016 minutes between steps; lower is quicker."""
    from app.mods.auto_repair import REPAIR_RATE
    assert 0 < float(REPAIR_RATE) < 0.016


def test_fast_repair_needs_no_cncnet(map_bytes):
    ymap = YRMap.load(map_bytes)
    BY_ID["auto_repair"].apply(ymap, {"fast_repair": "1"})
    assert ymap.ini.get("General", "RepairPercent") == "0%"
    assert not ymap.ini.has_section("ForcedOptions")


def test_each_repair_lever_is_independent(map_bytes):
    ymap = YRMap.load(map_bytes)
    BY_ID["auto_repair"].apply(ymap, {"structures": "1"})
    assert ymap.ini.get("GACNST", "SelfHealing") == "yes"
    assert ymap.ini.get("General", "RepairPercent") is None


def test_auto_repair_lowers_the_iq_threshold(map_bytes, all_options):
    """Human players are IQ 0; the stock threshold of 1 excludes them."""
    from app.mods.auto_repair import REPAIR_SELL_IQ
    ini = apply_all(map_bytes, all_options).ini
    assert ini.get("IQ", "RepairSell") == REPAIR_SELL_IQ
    assert int(REPAIR_SELL_IQ) == 0


def test_auto_repair_needs_no_cncnet(map_bytes):
    ymap = YRMap.load(map_bytes)
    BY_ID["auto_repair"].apply(ymap, {"auto": "1"})
    assert ymap.ini.get("IQ", "RepairSell") == "0"
    assert not ymap.ini.has_section("ForcedOptions")


def test_auto_repair_merges_into_an_existing_iq_section(map_bytes):
    raw = map_bytes + b"\r\n[IQ]\r\nRepairSell=1\r\nGuardArea=2\r\n"
    ymap = YRMap.load(raw)
    BY_ID["auto_repair"].apply(ymap, {"auto": "1"})
    assert ymap.ini.items("IQ") == [("RepairSell", "0"), ("GuardArea", "2")]
