# YR Maps Editor

A web tool for Command & Conquer: Red Alert 2 — Yuri's Revenge. Upload a
map, pick the upgrades you want, download the edited map.

Live at **https://yrmapseditor.site** · deployment steps in [DEPLOY.md](DEPLOY.md)

## Upgrades in this version

| Upgrade | What it writes | Where it works |
|---|---|---|
| **Auto-repair for buildings** | `chkAutoRepair=true`, and `SelfHealing=yes` on every buildable structure | CnCNet client; the structure half also works in the stock game |
| **Maximum starting money** | `cmbCredits=0` (100,000 credits) | CnCNet client |
| **Game speed** | `cmbGameSpeedCapSkirmish` / `cmbGameSpeedCapMultiplayer`, optionally `chkDisableGameSpeed` | CnCNet client |

`[ForcedOptions]` is read by the CnCNet client and has to live inside the map
file itself, which is exactly what this tool does. The stock game ignores it,
so a map edited only with forced options behaves normally offline.

## How it handles map files

`.map`, `.mpr` and `.yrm` are all the same thing: an INI document. The parts
that are not human-readable — `IsoMapPack5` (terrain), `OverlayPack` (ore and
walls), `PreviewPack` (minimap) — are base64 payloads whose line layout the
game depends on.

So the editor never rewrites a map. It keeps every original line verbatim and
splices in only the lines an upgrade actually adds. Parsing and re-serialising
a map with no edits returns a byte-identical file, and that property is
enforced by the test suite. Terrain cannot be corrupted by an upgrade, because
no upgrade ever writes to those sections.

## Layout

```
app/
  inifile.py     byte-faithful INI reader/writer — the core guarantee
  mapfile.py     map model, validation, the facts shown in the UI
  storage.py     short-lived upload store with TTL cleanup
  main.py        FastAPI routes
  mods/          one module per upgrade
tools/
  verify_corpus.py   run the whole pipeline over a folder of real maps
tests/             550+ tests, including randomised round-trip fuzzing
```

## Adding another upgrade

Write a `Mod` subclass in `app/mods/`, declare its `options`, and add it to
`REGISTRY` in `app/mods/__init__.py`. The form, the apply route and the result
report all build themselves from the registry — there is no UI to edit.

## Running locally

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Then open http://127.0.0.1:8000

## Testing

```bash
python3 -m pytest tests/ -q                      # unit, integration, fuzz
python3 tools/verify_corpus.py ~/maps -r -v      # against real map files
```

`verify_corpus.py` exits non-zero if any map fails, so it can gate a deploy.
Run it over a few hundred real maps before every release.

## Known limits

- **Forced options need the CnCNet client.** Users on the stock Steam, Origin
  or disc game will not see them applied.
- **"Maximum money" is 100,000 credits**, the largest the lobby offers — not a
  literally endless supply. Endless income needs a repeating map trigger,
  which is a planned upgrade.
- **Structure self-repair is a map-side rules override.** This is standard
  community practice, but test an edited map in-game before sharing it widely.
- **Everyone needs the same file.** Editing a map changes it, so every player
  in a match must have the edited copy. The tool renames the map to
  `... [Edited]` so it is easy to tell the versions apart.
- **Map packages (`.mmx`, `.yro`) are not supported.** Extract the `.mpr` or
  `.yrm` from them with XCC Mixer first.
