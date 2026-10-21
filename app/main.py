"""YR Maps Editor — upload a Yuri's Revenge map, pick upgrades, download it."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Form, Request, UploadFile
from fastapi.responses import (HTMLResponse, JSONResponse,
                               RedirectResponse, Response)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import secrets

from . import accounts, chat, db, storage, support
from .config import (CLIENT_COOKIE, REQUIRE_LOGIN, SESSION_COOKIE,
                     SESSION_DAYS, SITE_NAME)
from .mapfile import ALLOWED_EXTENSIONS, MAX_UPLOAD_BYTES, MapError, YRMap
from .mods import BY_ID, REGISTRY
from .preview import render_png

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title=SITE_NAME, docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")

db.init()


def current_user(request: Request):
    return accounts.user_for_session(request.cookies.get(SESSION_COOKIE))


def client_token(request: Request) -> str:
    """The visitor's own identifier, minted on first use.

    It names nobody. It exists so a visitor without an account still gets
    their own chat thread and their own report history back, and so one
    visitor can be rate-limited without rate-limiting everyone.
    """
    return request.cookies.get(CLIENT_COOKIE) or secrets.token_urlsafe(18)


def set_client_cookie(response: Response, request: Request, token: str) -> None:
    response.set_cookie(
        CLIENT_COOKIE, token,
        max_age=365 * 24 * 3600, httponly=True, samesite="lax",
        secure=request.url.scheme == "https", path="/",
    )


def require_admin(request: Request):
    """The signed-in admin, or a response explaining why not."""
    user = current_user(request)
    if user is not None and user.is_admin:
        return user, None
    if user is None:
        return None, RedirectResponse("/signin", status_code=303)
    return None, error_page(
        request,
        "You are signed in, but this account is not an administrator. "
        "Add its address to YRME_ADMIN_EMAILS and reload.",
        403, action_label="Back to the tool", action_href="/")


def render(request: Request, template: str, **context) -> HTMLResponse:
    context.setdefault("user", current_user(request))
    return templates.TemplateResponse(
        request=request,
        name=template,
        context={"site_name": SITE_NAME, "require_login": REQUIRE_LOGIN, **context},
    )


def signin_required(request: Request) -> HTMLResponse | None:
    """A page the visitor may not use yet, or None when they may.

    Only bites when REQUIRE_LOGIN is on, so the tool stays open to
    everyone until that is deliberately switched.
    """
    if not REQUIRE_LOGIN or current_user(request) is not None:
        return None
    response = render(request, "signin.html",
                      message="Sign in to edit a map.", email="")
    response.status_code = 401
    return response


def set_session_cookie(response: Response, request: Request, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_DAYS * 24 * 3600,
        httponly=True,
        samesite="lax",
        # True behind Caddy, False on plain http in development.
        secure=request.url.scheme == "https",
        path="/",
    )


def error_page(request: Request, message: str, status_code: int = 400,
               action_label: str = "Try another file",
               action_href: str = "/") -> HTMLResponse:
    response = render(request, "error.html", message=message,
                      action_label=action_label, action_href=action_href)
    response.status_code = status_code
    return response


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return render(request, "index.html", max_mb=MAX_UPLOAD_BYTES // (1024 * 1024))


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.post("/upload", response_class=HTMLResponse)
async def upload(request: Request, mapfile: UploadFile):
    blocked = signin_required(request)
    if blocked is not None:
        return blocked

    filename = Path(mapfile.filename or "map.map").name
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        return error_page(
            request,
            f"'{filename}' is not a map file. Upload a file ending in {allowed}.",
        )

    data = await mapfile.read()
    try:
        ymap = YRMap.load(data, filename)
    except MapError as exc:
        return error_page(request, str(exc))

    token = storage.store(data, filename)
    return render(
        request,
        "options.html",
        token=token,
        filename=filename,
        info=ymap.info(),
        mods=REGISTRY,
    )


@app.get("/preview/{token}.png")
def preview(token: str):
    """The map's own embedded minimap, decoded from the uploaded file.

    Nothing from the game's data files is involved, so no assets have to
    be shipped or licensed.
    """
    try:
        data, filename = storage.load(token)
    except storage.StorageError:
        return Response(status_code=404)

    try:
        ymap = YRMap.load(data, filename)
    except MapError:
        return Response(status_code=404)

    png = render_png(ymap.ini)
    if png is None:
        return Response(status_code=404)

    return Response(
        content=png,
        media_type="image/png",
        headers={"Cache-Control": "private, max-age=1800"},
    )


@app.post("/apply")
async def apply(request: Request, token: str = Form(...)):
    blocked = signin_required(request)
    if blocked is not None:
        return blocked

    try:
        data, filename = storage.load(token)
    except storage.StorageError as exc:
        return error_page(request, str(exc), status_code=410)

    form = await request.form()
    selected = form.getlist("mods")
    if not selected:
        return error_page(request, "Pick at least one upgrade to apply.")

    try:
        ymap = YRMap.load(data, filename)
    except MapError as exc:
        return error_page(request, str(exc))

    values = {key: str(value) for key, value in form.items()}
    applied: list[tuple[str, list]] = []
    for mod_id in selected:
        mod = BY_ID.get(mod_id)
        if mod is None:
            continue
        changes = mod.apply(ymap, values)
        if changes:
            applied.append((mod.name, changes))

    if not applied:
        return error_page(
            request, "Nothing was changed — every selected upgrade was left empty."
        )

    original_name = ymap.ini.get("Basic", "Name") or Path(filename).stem
    if not original_name.endswith("[Edited]"):
        ymap.set_display_name(f"{original_name} [Edited]")

    storage.discard(token)

    # Keep the extension the map arrived with. .map is what the CnCNet
    # client lists, while the stock game's skirmish screen wants .yrm for
    # Yuri's Revenge and .mpr for Red Alert 2, so forcing one of them would
    # leave half of users renaming the file by hand.
    stem = Path(filename).stem
    suffix = Path(filename).suffix or ".map"
    download_name = f"{stem} [Edited]{suffix}"
    return Response(
        content=ymap.to_bytes(),
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{download_name}"',
            "X-Upgrades-Applied": str(len(applied)),
        },
    )


# --------------------------------------------------------------- accounts


@app.get("/signup", response_class=HTMLResponse)
def signup_page(request: Request):
    if current_user(request) is not None:
        return RedirectResponse("/account", status_code=303)
    return render(request, "signup.html", email="", name="")


@app.post("/signup", response_class=HTMLResponse)
def signup(request: Request, email: str = Form(""), password: str = Form(""),
           name: str = Form("")):
    try:
        user = accounts.create_user(email, password, name)
    except accounts.AccountError as exc:
        response = render(request, "signup.html", error=str(exc),
                          email=email, name=name)
        response.status_code = 400
        return response

    response = RedirectResponse("/account", status_code=303)
    set_session_cookie(response, request, accounts.start_session(user.id))
    return response


@app.get("/signin", response_class=HTMLResponse)
def signin_page(request: Request):
    if current_user(request) is not None:
        return RedirectResponse("/account", status_code=303)
    return render(request, "signin.html", email="")


@app.post("/signin", response_class=HTMLResponse)
def signin(request: Request, email: str = Form(""), password: str = Form("")):
    try:
        user = accounts.authenticate(email, password)
    except accounts.AccountError as exc:
        response = render(request, "signin.html", error=str(exc), email=email)
        response.status_code = 401
        return response

    response = RedirectResponse("/account", status_code=303)
    set_session_cookie(response, request, accounts.start_session(user.id))
    return response


@app.post("/signout")
def signout(request: Request):
    accounts.end_session(request.cookies.get(SESSION_COOKIE))
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


@app.get("/account", response_class=HTMLResponse)
def account_page(request: Request):
    user = current_user(request)
    if user is None:
        return RedirectResponse("/signin", status_code=303)
    return render(request, "account.html", user=user)


@app.post("/account/name", response_class=HTMLResponse)
def update_name(request: Request, name: str = Form("")):
    user = current_user(request)
    if user is None:
        return RedirectResponse("/signin", status_code=303)
    accounts.set_name(user.id, name)
    return RedirectResponse("/account?saved=name", status_code=303)


@app.post("/account/password", response_class=HTMLResponse)
def update_password(request: Request, current: str = Form(""),
                    new_password: str = Form("")):
    user = current_user(request)
    if user is None:
        return RedirectResponse("/signin", status_code=303)
    try:
        accounts.change_password(user.id, current, new_password)
    except accounts.AccountError as exc:
        response = render(request, "account.html", user=user, error=str(exc))
        response.status_code = 400
        return response

    # Every session was dropped, including this one; sign them back in.
    response = RedirectResponse("/account?saved=password", status_code=303)
    set_session_cookie(response, request, accounts.start_session(user.id))
    return response


# ---------------------------------------------------------------- support


@app.get("/support", response_class=HTMLResponse)
def support_page(request: Request, kind: str = "problem"):
    token = client_token(request)
    response = render(
        request, "support.html",
        kind=kind if kind in support.KINDS else "problem",
        kinds=support.KINDS,
        mine=support.for_visitor(token),
    )
    set_client_cookie(response, request, token)
    return response


@app.post("/support", response_class=HTMLResponse)
def support_submit(request: Request, kind: str = Form("problem"),
                   subject: str = Form(""), body: str = Form(""),
                   contact: str = Form("")):
    token = client_token(request)
    user = current_user(request)
    try:
        support.submit(kind, subject, body, contact, token,
                       user.id if user else None)
    except support.SupportError as exc:
        response = render(request, "support.html", kind=kind, kinds=support.KINDS,
                          mine=support.for_visitor(token), error=str(exc),
                          subject=subject, body=body, contact=contact)
        response.status_code = 400
        set_client_cookie(response, request, token)
        return response

    response = RedirectResponse("/support?sent=1", status_code=303)
    set_client_cookie(response, request, token)
    return response


# ------------------------------------------------------------------- chat


@app.get("/chat/messages")
def chat_messages(request: Request, after: int = 0):
    token = client_token(request)
    messages = chat.history(token, after_id=after)
    response = JSONResponse({"messages": [
        {"id": m.id, "sender": m.sender, "body": m.body, "at": m.created_at}
        for m in messages
    ]})
    set_client_cookie(response, request, token)
    return response


@app.post("/chat/send")
async def chat_send(request: Request, body: str = Form("")):
    token = client_token(request)
    user = current_user(request)
    try:
        message = chat.send_from_visitor(token, body, user.id if user else None)
    except chat.ChatError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)

    response = JSONResponse({"message": {
        "id": message.id, "sender": message.sender,
        "body": message.body, "at": message.created_at}})
    set_client_cookie(response, request, token)
    return response


# ------------------------------------------------------------------ admin


@app.get("/admin", response_class=HTMLResponse)
def admin_home(request: Request):
    user, blocked = require_admin(request)
    if blocked is not None:
        return blocked
    return render(request, "admin.html", user=user,
                  counts=support.counts(), waiting=chat.waiting_count(),
                  recent=support.listing(limit=8),
                  threads=chat.conversations(limit=8))


@app.get("/admin/reports", response_class=HTMLResponse)
def admin_reports(request: Request, status: str = "", kind: str = ""):
    user, blocked = require_admin(request)
    if blocked is not None:
        return blocked
    return render(request, "admin_reports.html", user=user,
                  counts=support.counts(), waiting=chat.waiting_count(),
                  reports=support.listing(status or None, kind or None),
                  statuses=support.STATUSES, kinds=support.KINDS,
                  active_status=status, active_kind=kind)


@app.post("/admin/reports/{report_id}")
def admin_update_report(request: Request, report_id: int,
                        status: str = Form("open"), admin_note: str = Form("")):
    user, blocked = require_admin(request)
    if blocked is not None:
        return blocked
    try:
        support.update(report_id, status, admin_note)
    except support.SupportError as exc:
        return error_page(request, str(exc))
    return RedirectResponse("/admin/reports", status_code=303)


@app.get("/admin/chats", response_class=HTMLResponse)
def admin_chats(request: Request, open_id: int = 0):
    user, blocked = require_admin(request)
    if blocked is not None:
        return blocked
    threads = chat.conversations()
    active = chat.get(open_id) if open_id else (threads[0] if threads else None)
    if active is not None:
        chat.mark_read(active.id)
    return render(request, "admin_chats.html", user=user,
                  counts=support.counts(), waiting=chat.waiting_count(),
                  threads=threads, active=active,
                  messages=chat.thread(active.id) if active else [])


@app.post("/admin/chats/{conversation_id}/send")
def admin_chat_send(request: Request, conversation_id: int, body: str = Form("")):
    user, blocked = require_admin(request)
    if blocked is not None:
        return blocked
    try:
        chat.send_from_admin(conversation_id, body)
    except chat.ChatError as exc:
        return error_page(request, str(exc))
    return RedirectResponse(f"/admin/chats?open_id={conversation_id}", status_code=303)


@app.get("/admin/chats/{conversation_id}/messages")
def admin_chat_messages(request: Request, conversation_id: int, after: int = 0):
    user, blocked = require_admin(request)
    if blocked is not None:
        return JSONResponse({"error": "forbidden"}, status_code=403)
    return JSONResponse({"messages": [
        {"id": m.id, "sender": m.sender, "body": m.body, "at": m.created_at}
        for m in chat.thread(conversation_id, after_id=after)
    ]})
