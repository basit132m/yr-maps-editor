"""YR Maps Editor — upload a Yuri's Revenge map, pick upgrades, download it."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import storage
from .config import SITE_NAME
from .mapfile import ALLOWED_EXTENSIONS, MAX_UPLOAD_BYTES, MapError, YRMap
from .mods import BY_ID, REGISTRY

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title=SITE_NAME, docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


def render(request: Request, template: str, **context) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request, name=template, context={"site_name": SITE_NAME, **context}
    )


def error_page(request: Request, message: str, status_code: int = 400) -> HTMLResponse:
    response = render(request, "error.html", message=message)
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


@app.post("/apply")
async def apply(request: Request, token: str = Form(...)):
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

    stem = Path(filename).stem
    download_name = f"{stem} [Edited].map"
    return Response(
        content=ymap.to_bytes(),
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{download_name}"',
            "X-Upgrades-Applied": str(len(applied)),
        },
    )
