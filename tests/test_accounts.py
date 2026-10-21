"""Accounts: Gmail handling, passwords, sessions and the login gate."""

import pytest
from fastapi.testclient import TestClient

from app import accounts, db
from app.accounts import AccountError
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_database():
    db.init()
    with db.transaction() as conn:
        conn.execute("DELETE FROM sessions")
        conn.execute("DELETE FROM users")
    yield


# -- Gmail addresses ---------------------------------------------------------


@pytest.mark.parametrize("raw, expected", [
    ("johnsmith@gmail.com", "johnsmith@gmail.com"),
    ("JohnSmith@Gmail.com", "johnsmith@gmail.com"),
    ("  johnsmith@gmail.com  ", "johnsmith@gmail.com"),
    ("john.smith@gmail.com", "johnsmith@gmail.com"),        # dots are ignored
    ("j.o.h.n.smith@gmail.com", "johnsmith@gmail.com"),
    ("johnsmith+yr@gmail.com", "johnsmith@gmail.com"),      # +tag is ignored
    ("john.smith+anything@googlemail.com", "johnsmith@gmail.com"),
])
def test_addresses_reaching_one_inbox_are_one_account(raw, expected):
    assert accounts.canonical_email(raw) == expected


@pytest.mark.parametrize("raw", [
    "someone@yahoo.com", "someone@outlook.com", "someone@gmail.co",
    "someone@notgmail.com", "", "   ", "no-at-sign", "a@b@gmail.com",
    "short@gmail.com",                   # Gmail requires 6+ characters
    "@gmail.com", "....@gmail.com",
])
def test_addresses_we_will_not_take(raw):
    with pytest.raises(AccountError):
        accounts.canonical_email(raw)


def test_one_person_cannot_register_twice_with_aliases():
    accounts.create_user("john.smith@gmail.com", "a good password")
    with pytest.raises(AccountError):
        accounts.create_user("johnsmith+spare@googlemail.com", "another password")


# -- passwords ---------------------------------------------------------------


def test_password_is_not_stored_in_the_clear():
    accounts.create_user("johnsmith@gmail.com", "correct horse battery")
    with db.transaction() as conn:
        stored = conn.execute("SELECT password_hash FROM users").fetchone()[0]
    assert "correct horse battery" not in stored
    assert stored.startswith("scrypt$")


def test_the_same_password_hashes_differently_each_time():
    """A per-user salt, so identical passwords do not look identical."""
    assert accounts.hash_password("same password") != accounts.hash_password("same password")


def test_password_check():
    stored = accounts.hash_password("correct horse battery")
    assert accounts.verify_password("correct horse battery", stored)
    assert not accounts.verify_password("wrong", stored)
    assert not accounts.verify_password("correct horse battery", "nonsense")


@pytest.mark.parametrize("password", ["", "short", "1234567"])
def test_passwords_that_are_too_short_are_refused(password):
    with pytest.raises(AccountError):
        accounts.create_user("johnsmith@gmail.com", password)


def test_signing_in_with_an_alias_works():
    user = accounts.create_user("john.smith@gmail.com", "a good password")
    assert accounts.authenticate("johnsmith+yr@googlemail.com", "a good password").id == user.id


def test_a_wrong_password_and_an_unknown_address_look_the_same():
    """Nothing in the message says which accounts exist."""
    accounts.create_user("johnsmith@gmail.com", "a good password")
    with pytest.raises(AccountError) as wrong:
        accounts.authenticate("johnsmith@gmail.com", "not the password")
    with pytest.raises(AccountError) as unknown:
        accounts.authenticate("nobodyhere@gmail.com", "not the password")
    assert str(wrong.value) == str(unknown.value)


# -- sessions ----------------------------------------------------------------


def test_session_round_trip():
    user = accounts.create_user("johnsmith@gmail.com", "a good password")
    token = accounts.start_session(user.id)
    assert accounts.user_for_session(token).id == user.id
    accounts.end_session(token)
    assert accounts.user_for_session(token) is None


def test_the_cookie_value_is_never_stored():
    user = accounts.create_user("johnsmith@gmail.com", "a good password")
    token = accounts.start_session(user.id)
    with db.transaction() as conn:
        stored = conn.execute("SELECT token_hash FROM sessions").fetchone()[0]
    assert token not in stored


@pytest.mark.parametrize("token", [None, "", "not-a-real-token", "x" * 64])
def test_invented_tokens_are_rejected(token):
    assert accounts.user_for_session(token) is None


def test_changing_the_password_signs_other_devices_out():
    user = accounts.create_user("johnsmith@gmail.com", "a good password")
    phone, laptop = accounts.start_session(user.id), accounts.start_session(user.id)
    accounts.change_password(user.id, "a good password", "a better password")
    assert accounts.user_for_session(phone) is None
    assert accounts.user_for_session(laptop) is None
    assert accounts.authenticate("johnsmith@gmail.com", "a better password").id == user.id


def test_changing_the_password_needs_the_current_one():
    user = accounts.create_user("johnsmith@gmail.com", "a good password")
    with pytest.raises(AccountError):
        accounts.change_password(user.id, "guessing", "a better password")


# -- display -----------------------------------------------------------------


def test_initials_come_from_the_name_then_the_address():
    named = accounts.create_user("johnsmith@gmail.com", "a good password", "John Smith")
    assert named.initials == "JS"
    assert named.display_name == "John Smith"
    plain = accounts.create_user("marywilson@gmail.com", "a good password")
    assert plain.display_name == "marywilson"


# -- through the web ---------------------------------------------------------


def register(email="johnsmith@gmail.com", password="a good password", name=""):
    return client.post("/signup", data={"email": email, "password": password,
                                        "name": name}, follow_redirects=False)


def test_signup_signs_you_in():
    response = register()
    assert response.status_code == 303
    assert response.headers["location"] == "/account"
    assert "yrme_session" in response.cookies
    assert "johnsmith" in client.get("/account").text


def test_signup_rejects_a_non_gmail_address():
    response = register(email="someone@yahoo.com")
    assert response.status_code == 400
    assert "@gmail.com" in response.text


def test_session_cookie_is_protected():
    """Not readable by script, and not sent on cross-site requests."""
    client.cookies.clear()
    raw = register().headers["set-cookie"]
    assert "HttpOnly" in raw
    assert "SameSite=lax" in raw.replace("samesite", "SameSite")
    assert "Path=/" in raw


def test_signout_ends_the_session():
    register()
    assert client.post("/signout", follow_redirects=False).status_code == 303
    assert client.get("/account", follow_redirects=False).headers["location"] == "/signin"


def test_account_page_needs_a_session():
    client.cookies.clear()
    response = client.get("/account", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/signin"


def test_name_can_be_changed():
    register()
    client.post("/account/name", data={"name": "John Smith"}, follow_redirects=False)
    assert "John Smith" in client.get("/account").text


def test_the_tool_stays_open_without_an_account(map_bytes):
    """REQUIRE_LOGIN is off by default, so nothing is gated."""
    client.cookies.clear()
    response = client.post("/upload", files={
        "mapfile": ("island.map", map_bytes, "application/octet-stream")})
    assert response.status_code == 200


def test_the_login_gate_closes_when_switched_on(map_bytes, monkeypatch):
    """With REQUIRE_LOGIN set, editing needs an account; signed in it works."""
    from app import main

    monkeypatch.setattr(main, "REQUIRE_LOGIN", True)
    client.cookies.clear()

    upload = {"mapfile": ("island.map", map_bytes, "application/octet-stream")}
    blocked = client.post("/upload", files=upload)
    assert blocked.status_code == 401
    assert "Sign in" in blocked.text

    # The public pages stay reachable, or nobody could ever sign up.
    assert client.get("/").status_code == 200
    assert client.get("/signup").status_code == 200

    register()
    assert client.post("/upload", files=upload).status_code == 200
