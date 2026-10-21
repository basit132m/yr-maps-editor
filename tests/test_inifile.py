"""The round-trip guarantee everything else depends on."""

import pytest

from app.inifile import IniFile

ODD_INPUTS = [
    b"",
    b"[A]\r\n",
    b"[A]\nkey=value",                      # no trailing newline
    b"[A]\r\nkey=value\r\n",
    b"; leading comment\r\n[A]\r\nk=v\r\n",
    b"[A]\r\n\r\n\r\n[B]\r\nk=v\r\n",       # blank-line runs
    b"[A]\r\nk=a=b=c\r\n",                  # '=' inside the value
    b"[A]\r\nk=v ; trailing comment\r\n",
    b"[A]\r\nk=v\r\n[A]\r\nk=other\r\n",    # duplicate section
    b"[A]\r\nName=Caf\xe9 Map\r\n",         # non-UTF-8 byte
    b"[A]\rk=v\r",                          # bare CR
    b"  [Indented]  \r\n  k = v  \r\n",
]


@pytest.mark.parametrize("raw", ODD_INPUTS)
def test_roundtrip_is_byte_identical(raw):
    assert IniFile.from_bytes(raw).to_bytes() == raw


def test_fixture_roundtrip(map_bytes):
    assert IniFile.from_bytes(map_bytes).to_bytes() == map_bytes


def test_first_duplicate_key_wins():
    doc = IniFile.from_bytes(b"[A]\r\nName=first\r\nName=second\r\n")
    assert doc.get("A", "Name") == "first"


def test_trailing_comment_stripped_from_value():
    doc = IniFile.from_bytes(b"[A]\r\nk=v ; note\r\n")
    assert doc.get("A", "k") == "v"


def test_lookup_is_case_insensitive():
    doc = IniFile.from_bytes(b"[Basic]\r\nName=X\r\n")
    assert doc.get("basic", "NAME") == "X"


def test_set_existing_key_preserves_everything_else(map_bytes):
    doc = IniFile.from_bytes(map_bytes)
    doc.set("Basic", "Author", "Someone Else")
    assert doc.get("Basic", "Author") == "Someone Else"
    assert len(doc.lines) == len(IniFile.from_bytes(map_bytes).lines)


def test_set_new_key_appends_inside_section():
    doc = IniFile.from_bytes(b"[A]\r\nk=v\r\n\r\n[B]\r\nj=w\r\n")
    doc.set("A", "new", "1")
    assert doc.to_bytes() == b"[A]\r\nk=v\r\nnew=1\r\n\r\n[B]\r\nj=w\r\n"


def test_new_section_uses_crlf_even_when_file_has_none():
    doc = IniFile.from_bytes(b"[A]\r\nk=v")
    doc.set("New", "a", "b")
    assert doc.to_bytes() == b"[A]\r\nk=v\r\n\r\n[New]\r\na=b\r\n"


def test_setting_same_value_is_a_noop(map_bytes):
    doc = IniFile.from_bytes(map_bytes)
    assert doc.set("Basic", "Author", "Nobody") is True
    before = doc.to_bytes()
    assert doc.set("Basic", "Author", "Nobody") is False
    assert doc.to_bytes() == before


def test_unset_removes_every_occurrence():
    doc = IniFile.from_bytes(b"[A]\r\nk=1\r\nk=2\r\nj=3\r\n")
    assert doc.unset("A", "k") is True
    assert doc.to_bytes() == b"[A]\r\nj=3\r\n"
