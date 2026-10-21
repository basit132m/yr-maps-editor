"""Reports, chat and the admin panel.

The point of the design: a visitor needs no account, but the admin area
must be shut to everyone else.
"""

import pytest
from fastapi.testclient import TestClient

from app import accounts, chat, db, support
from app.chat import ChatError
from app.main import app
from app.support import SupportError

client = TestClient(app)
ADMIN_EMAIL = "mapsadmin@gmail.com"


@pytest.fixture(autouse=True)
def clean_database(monkeypatch):
    monkeypatch.setattr("app.accounts.ADMIN_EMAILS", (ADMIN_EMAIL,))
    db.init()
    with db.transaction() as conn:
        for table in ("messages", "conversations", "reports", "sessions", "users"):
            conn.execute(f"DELETE FROM {table}")
    client.cookies.clear()
    yield


def become_admin():
    client.post("/signup", data={"email": ADMIN_EMAIL, "password": "a good password"},
                follow_redirects=False)


def become_ordinary_user():
    client.post("/signup", data={"email": "someoneelse@gmail.com",
                                 "password": "a good password"},
                follow_redirects=False)


# -- reports, with no account ------------------------------------------------


def test_anyone_can_send_a_report_without_an_account():
    response = client.post("/support", data={
        "kind": "problem", "subject": "Map will not open",
        "body": "The game does not list it after I download it.",
    }, follow_redirects=False)
    assert response.status_code == 303
    assert support.listing()[0].subject == "Map will not open"


def test_a_visitor_sees_their_own_reports_come_back():
    client.post("/support", data={"kind": "feature", "subject": "Ore regrowth",
                                  "body": "Let ore grow back faster please."},
                follow_redirects=False)
    page = client.get("/support")
    assert "Ore regrowth" in page.text


def test_one_visitor_cannot_read_another_visitors_reports():
    client.post("/support", data={"kind": "problem", "subject": "Private thing",
                                  "body": "Something only I sent."},
                follow_redirects=False)
    client.cookies.clear()                      # a different browser
    assert "Private thing" not in client.get("/support").text


@pytest.mark.parametrize("subject, body", [
    ("", "A long enough description here."),
    ("ab", "A long enough description here."),
    ("A fine subject", ""),
    ("A fine subject", "too short"),
])
def test_empty_or_tiny_reports_are_refused(subject, body):
    with pytest.raises(SupportError):
        support.submit("problem", subject, body, "", "tok")


def test_an_unknown_kind_is_refused():
    with pytest.raises(SupportError):
        support.submit("nonsense", "A subject", "A long enough body here.", "", "tok")


def test_a_flood_of_reports_is_throttled(monkeypatch):
    monkeypatch.setattr("app.support.REPORTS_PER_HOUR", 3)
    for n in range(3):
        support.submit("problem", f"Report {n}", "A long enough body here.", "", "tok")
    with pytest.raises(SupportError):
        support.submit("problem", "One too many", "A long enough body here.", "", "tok")


def test_throttling_is_per_visitor_not_global(monkeypatch):
    monkeypatch.setattr("app.support.REPORTS_PER_HOUR", 1)
    support.submit("problem", "Mine", "A long enough body here.", "", "first")
    support.submit("problem", "Theirs", "A long enough body here.", "", "second")


# -- chat, with no account ---------------------------------------------------


def test_a_visitor_can_chat_and_read_the_reply():
    sent = client.post("/chat/send", data={"body": "My map will not load"})
    assert sent.status_code == 200

    thread = chat.conversations()[0]
    chat.send_from_admin(thread.id, "Send me the file and I will look")

    messages = client.get("/chat/messages").json()["messages"]
    assert [m["sender"] for m in messages] == ["visitor", "admin"]
    assert messages[1]["body"] == "Send me the file and I will look"


def test_only_new_messages_come_back_when_polling():
    client.post("/chat/send", data={"body": "first"})
    first = client.get("/chat/messages").json()["messages"]
    client.post("/chat/send", data={"body": "second"})
    rest = client.get(f"/chat/messages?after={first[-1]['id']}").json()["messages"]
    assert [m["body"] for m in rest] == ["second"]


def test_one_visitor_cannot_read_another_visitors_chat():
    client.post("/chat/send", data={"body": "something private"})
    client.cookies.clear()
    assert client.get("/chat/messages").json()["messages"] == []


def test_an_empty_chat_message_is_refused():
    assert client.post("/chat/send", data={"body": "   "}).status_code == 400
    with pytest.raises(ChatError):
        chat.send_from_visitor("tok", "")


def test_chat_flooding_is_throttled(monkeypatch):
    monkeypatch.setattr("app.chat.CHAT_MESSAGES_PER_MINUTE", 2)
    chat.send_from_visitor("tok", "one")
    chat.send_from_visitor("tok", "two")
    with pytest.raises(ChatError):
        chat.send_from_visitor("tok", "three")


def test_a_reply_to_a_missing_conversation_is_refused():
    with pytest.raises(ChatError):
        chat.send_from_admin(9999, "hello?")


# -- the admin area is shut --------------------------------------------------


ADMIN_PAGES = ["/admin", "/admin/reports", "/admin/chats"]


@pytest.mark.parametrize("path", ADMIN_PAGES)
def test_a_stranger_is_sent_to_sign_in(path):
    response = client.get(path, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == f"/signin?next={path}"


@pytest.mark.parametrize("path", ADMIN_PAGES)
def test_an_ordinary_signed_in_user_is_refused(path):
    become_ordinary_user()
    response = client.get(path)
    assert response.status_code == 403
    assert "not an administrator" in response.text


def test_an_ordinary_user_cannot_change_a_report():
    report = support.submit("problem", "A subject", "A long enough body here.", "", "tok")
    become_ordinary_user()
    assert client.post(f"/admin/reports/{report.id}",
                       data={"status": "done", "admin_note": "hijacked"}).status_code == 403
    assert support.listing()[0].status == "open"


def test_an_ordinary_user_cannot_reply_in_a_chat():
    chat.send_from_visitor("tok", "hello")
    thread = chat.conversations()[0]
    become_ordinary_user()
    assert client.post(f"/admin/chats/{thread.id}/send",
                       data={"body": "pretending to be support"}).status_code == 403
    assert [m.sender for m in chat.thread(thread.id)] == ["visitor"]


def test_an_ordinary_user_cannot_read_a_chat_thread():
    chat.send_from_visitor("tok", "private")
    thread = chat.conversations()[0]
    become_ordinary_user()
    assert client.get(f"/admin/chats/{thread.id}/messages").status_code == 403


# -- the admin can work ------------------------------------------------------


@pytest.mark.parametrize("path", ADMIN_PAGES)
def test_the_admin_gets_in(path):
    become_admin()
    assert client.get(path).status_code == 200


def test_the_configured_address_becomes_admin():
    become_admin()
    assert accounts.authenticate(ADMIN_EMAIL, "a good password").is_admin


def test_replacing_the_address_takes_admin_away(monkeypatch):
    become_admin()
    monkeypatch.setattr("app.accounts.ADMIN_EMAILS", ("someoneelse@gmail.com",))
    assert not accounts.authenticate(ADMIN_EMAIL, "a good password").is_admin


def test_an_empty_config_leaves_the_database_alone(monkeypatch):
    """So a flag set by tools/make_admin.py is not wiped on the next page
    load when the environment variable never arrived."""
    become_admin()
    monkeypatch.setattr("app.accounts.ADMIN_EMAILS", ())
    assert accounts.authenticate(ADMIN_EMAIL, "a good password").is_admin
    assert client.get("/admin").status_code == 200


def test_admin_can_be_granted_without_any_configuration(monkeypatch):
    """The escape hatch: no environment variable involved at all."""
    monkeypatch.setattr("app.accounts.ADMIN_EMAILS", ())
    become_admin()
    assert client.get("/admin").status_code == 403

    accounts.grant_admin(ADMIN_EMAIL)
    assert client.get("/admin").status_code == 200    # same session

    accounts.grant_admin(ADMIN_EMAIL, admin=False)
    assert client.get("/admin").status_code == 403


def test_granting_admin_to_a_missing_account_says_so(monkeypatch):
    with pytest.raises(accounts.AccountError):
        accounts.grant_admin("nobodyhere@gmail.com")


def test_the_admin_can_answer_a_report():
    report = support.submit("feature", "Ore regrowth", "Let ore grow back.", "", "tok")
    become_admin()
    client.post(f"/admin/reports/{report.id}",
                data={"status": "planned", "admin_note": "Good idea, queued."},
                follow_redirects=False)
    updated = support.listing()[0]
    assert updated.status == "planned"
    assert updated.admin_note == "Good idea, queued."


def test_the_sender_sees_the_admin_reply():
    client.post("/support", data={"kind": "problem", "subject": "Broken map",
                                  "body": "It will not open at all."},
                follow_redirects=False)
    visitor_cookies = dict(client.cookies)
    report = support.listing()[0]

    client.cookies.clear()
    become_admin()
    client.post(f"/admin/reports/{report.id}",
                data={"status": "done", "admin_note": "Fixed in the latest update."},
                follow_redirects=False)

    client.cookies.clear()
    client.cookies.update(visitor_cookies)
    page = client.get("/support").text
    assert "Fixed in the latest update." in page
    assert "Done" in page


def test_opening_a_chat_clears_its_unread_count():
    chat.send_from_visitor("tok", "hello")
    assert chat.waiting_count() == 1
    become_admin()
    client.get("/admin/chats")
    assert chat.waiting_count() == 0


def test_report_text_is_escaped_not_executed():
    """A report is shown back to the admin and the sender, so markup in it
    must never become markup on the page."""
    support.submit("problem", "<script>alert(1)</script>",
                   "Body with <b>tags</b> & an ampersand.", "", "tok")
    become_admin()
    page = client.get("/admin/reports").text
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;" in page
    assert "<b>tags</b>" not in page


@pytest.mark.parametrize("configured", [
    "mapsadmin@gmail.com",
    "maps.admin@gmail.com",          # dots are ignored by Gmail
    "MapsAdmin@Gmail.com",           # case is ignored
    "maps.admin+site@googlemail.com",  # tag and alias domain
])
def test_an_admin_address_is_matched_however_it_is_written(monkeypatch, configured):
    """The configured address must be reduced the same way a stored one is,
    or a dot in it silently grants nobody admin."""
    monkeypatch.setattr("app.accounts.ADMIN_EMAILS", (configured,))
    become_admin()
    assert accounts.authenticate(ADMIN_EMAIL, "a good password").is_admin


def test_a_malformed_admin_address_is_ignored_not_fatal(monkeypatch):
    monkeypatch.setattr("app.accounts.ADMIN_EMAILS", ("not-an-address", ADMIN_EMAIL))
    become_admin()
    assert accounts.authenticate(ADMIN_EMAIL, "a good password").is_admin


def test_admin_applies_without_signing_out_again(monkeypatch):
    """Adding an address to the config must take effect on the next page
    load. Requiring a sign-out, with nothing on screen saying so, is how
    someone concludes the panel is broken."""
    monkeypatch.setattr("app.accounts.ADMIN_EMAILS", ())
    become_admin()                                  # signed up as nobody special
    assert client.get("/admin").status_code == 403

    monkeypatch.setattr("app.accounts.ADMIN_EMAILS", (ADMIN_EMAIL,))
    assert client.get("/admin").status_code == 200   # same session, no sign-out


def test_losing_admin_also_applies_at_once(monkeypatch):
    monkeypatch.setattr("app.accounts.ADMIN_EMAILS", (ADMIN_EMAIL,))
    become_admin()
    assert client.get("/admin").status_code == 200
    monkeypatch.setattr("app.accounts.ADMIN_EMAILS", ("someoneelse@gmail.com",))
    assert client.get("/admin").status_code == 403


def test_the_refusal_names_the_account_and_the_reason(monkeypatch):
    """A refusal that says only 'you may not' leaves someone stuck."""
    monkeypatch.setattr("app.accounts.ADMIN_EMAILS", ())
    become_ordinary_user()
    page = client.get("/admin").text
    assert "someoneelse@gmail.com" in page          # which account it is
    assert "no admin addresses configured" in page  # why
    assert "make_admin.py" in page                  # what to do
    assert "Try another file" not in page


def test_the_refusal_never_lists_the_admin_addresses(monkeypatch):
    """Any signed-in visitor can reach it, so it reports a count only."""
    monkeypatch.setattr("app.accounts.ADMIN_EMAILS", (ADMIN_EMAIL,))
    become_ordinary_user()
    page = client.get("/admin").text
    assert ADMIN_EMAIL not in page
    assert "1 admin address" in page
