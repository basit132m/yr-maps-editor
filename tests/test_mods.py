"""Upgrades must change exactly what they claim and nothing else."""

import pytest

from app.inifile import IniFile
from app.mapfile import MapError, YRMap
from app.mods import BY_ID, REGISTRY
from app.mods.auto_repair import BUILDINGS

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
    assert after - before == {"ForcedOptions", *BUILDINGS}


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
    BY_ID["money"].apply(ymap, {"credits": "; injected"})
    BY_ID["game_speed"].apply(ymap, {"speed": "../../etc/passwd"})
    assert ymap.ini.get("ForcedOptions", "cmbCredits") == "0"
    assert ymap.ini.get("ForcedOptions", "cmbGameSpeedCapSkirmish") == "0"


def test_existing_forced_options_are_updated_not_duplicated(map_bytes):
    raw = map_bytes + b"\r\n[ForcedOptions]\r\ncmbCredits=8\r\nchkCrates=false\r\n"
    ymap = YRMap.load(raw)
    BY_ID["money"].apply(ymap, {"credits": "0"})
    assert ymap.ini.items("ForcedOptions") == [("cmbCredits", "0"), ("chkCrates", "false")]


def test_renaming_marks_the_map_as_edited(map_bytes):
    ymap = YRMap.load(map_bytes)
    ymap.set_display_name("Tournament Island [Edited]")
    assert ymap.ini.get("Basic", "Name") == "Tournament Island [Edited]"


def test_output_is_still_a_loadable_map(map_bytes, all_options):
    reloaded = YRMap.load(apply_all(map_bytes, all_options).to_bytes())
    assert reloaded.info().players == 4
