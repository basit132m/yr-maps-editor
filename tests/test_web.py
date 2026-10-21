"""End-to-end checks through the HTTP layer."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.mapfile import YRMap

client = TestClient(app)


def upload(map_bytes, filename="island.map"):
    return client.post("/upload", files={"mapfile": (filename, map_bytes, "application/octet-stream")})


def test_home_page_loads():
    response = client.get("/")
    assert response.status_code == 200
    assert "Upload your map" in response.text


def test_healthz():
    assert client.get("/healthz").json() == {"status": "ok"}


def test_upload_shows_map_details(map_bytes):
    response = upload(map_bytes)
    assert response.status_code == 200
    assert "Tournament Island" in response.text
    assert "Repair" in response.text


@pytest.mark.parametrize("filename", ["map.mpr", "map.yrm", "MAP.MAP"])
def test_all_map_extensions_accepted(map_bytes, filename):
    assert upload(map_bytes, filename).status_code == 200


def test_wrong_extension_rejected(map_bytes):
    response = upload(map_bytes, "map.exe")
    assert response.status_code == 400
    assert "not a map file" in response.text


def test_garbage_upload_rejected():
    response = upload(b"\x00\x01\x02" * 100, "fake.map")
    assert response.status_code == 400


def _token_from(html):
    marker = 'name="token" value="'
    start = html.index(marker) + len(marker)
    return html[start:html.index('"', start)]


def test_full_journey_returns_an_edited_map(map_bytes):
    token = _token_from(upload(map_bytes).text)
    response = client.post("/apply", data={
        "token": token,
        "mods": ["auto_repair", "money", "game_speed"],
        "forced_option": "1", "structures": "1", "fast_repair": "1", "auto": "1",
        "income": "1", "rate": "generous", "starting": "1", "credits": "0",
        "speed": "fastest", "build_speed": "fast", "strength": "unbreakable", "lock": "1",
    })
    assert response.status_code == 200
    assert "attachment" in response.headers["content-disposition"]

    edited = YRMap.load(response.content)
    assert edited.ini.get("ForcedOptions", "chkAutoRepair") == "true"
    assert edited.ini.get("ForcedOptions", "cmbCredits") == "0"
    assert edited.ini.get("GACNST", "SelfHealing") == "yes"
    assert edited.ini.get("Basic", "Name") == "Tournament Island [Edited]"
    # Terrain survived the trip unchanged.
    assert edited.ini.items("IsoMapPack5") == YRMap.load(map_bytes).ini.items("IsoMapPack5")


def test_selecting_one_upgrade_leaves_the_others_alone(map_bytes):
    token = _token_from(upload(map_bytes).text)
    response = client.post("/apply", data={
        "token": token, "mods": ["money"], "starting": "1", "credits": "1",
    })
    edited = YRMap.load(response.content)
    assert edited.ini.get("ForcedOptions", "cmbCredits") == "1"
    assert edited.ini.get("ForcedOptions", "chkAutoRepair") is None
    assert edited.ini.get("GACNST", "SelfHealing") is None


def test_no_upgrade_selected_is_rejected(map_bytes):
    token = _token_from(upload(map_bytes).text)
    response = client.post("/apply", data={"token": token})
    assert response.status_code == 400


def test_bad_token_is_rejected():
    response = client.post("/apply", data={"token": "../../etc/passwd", "mods": ["money"]})
    assert response.status_code == 410


def test_token_cannot_be_reused(map_bytes):
    token = _token_from(upload(map_bytes).text)
    data = {"token": token, "mods": ["money"], "starting": "1", "credits": "0"}
    assert client.post("/apply", data=data).status_code == 200
    assert client.post("/apply", data=data).status_code == 410


@pytest.mark.parametrize("uploaded, expected", [
    ("island.map", "island [Edited].map"),
    ("island.yrm", "island [Edited].yrm"),
    ("island.mpr", "island [Edited].mpr"),
    ("ISLAND.YRM", "ISLAND [Edited].YRM"),
])
def test_download_keeps_the_original_extension(map_bytes, uploaded, expected):
    """A .yrm must come back as .yrm, or offline skirmish will not list it."""
    token = _token_from(upload(map_bytes, uploaded).text)
    response = client.post("/apply", data={
        "token": token, "mods": ["money"], "income": "1", "rate": "steady",
    })
    assert expected in response.headers["content-disposition"]


# -- the upgrade picker ------------------------------------------------------


def _mod_inputs(html):
    """Every <input name="mods" ...> tag on the page, as raw text."""
    import re
    return re.findall(r'<input[^>]*name="mods"[^>]*>', html)


def test_no_upgrade_is_preselected(map_bytes):
    """The visitor chooses; nothing is ticked for them."""
    tags = _mod_inputs(upload(map_bytes).text)
    assert len(tags) == 4
    for tag in tags:
        assert "checked" not in tag, tag


def test_every_upgrade_panel_can_collapse(map_bytes):
    html = upload(map_bytes).text
    assert html.count("data-mod-toggle") == 4
    assert html.count('class="mod-clip"') == 4


def test_sub_options_keep_their_recommended_defaults(map_bytes):
    """Opening an upgrade should present sensible settings, not blanks."""
    html = upload(map_bytes).text
    assert 'name="auto" value="1"' in html and "checked" in html
    assert 'name="income" value="1"' in html


def test_picker_is_only_presentation(map_bytes):
    """Collapsing changes no behaviour: an unticked upgrade is still skipped
    and a ticked one still applies, exactly as before."""
    token = _token_from(upload(map_bytes).text)
    response = client.post("/apply", data={
        "token": token, "mods": ["auto_repair"], "auto": "1",
        # Values belonging to upgrades the user did not tick.
        "income": "1", "rate": "generous", "build_speed": "fast",
        "strength": "unbreakable",
    })
    edited = YRMap.load(response.content)
    assert edited.ini.get("IQ", "RepairSell") == "0"
    assert edited.ini.get("GACNST", "ProduceCashAmount") is None
    assert edited.ini.get("General", "BuildSpeed") is None
    assert edited.ini.get("General", "RepairPercent") is None
