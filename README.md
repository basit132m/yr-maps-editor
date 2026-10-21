# YR Maps Editor

A web tool for Command & Conquer: Red Alert 2 — Yuri's Revenge. Upload a
map, pick the upgrades you want, download the edited map.

Live at **https://yrmapseditor.site** · deployment steps in [DEPLOY.md](DEPLOY.md)

## Upgrades in this version

Players are split between the CnCNet client and the stock Steam/Origin/disc
game, so each option says which it needs, and the important ones work on
both.

| Upgrade | What it writes | Where it works |
|---|---|---|
| **Auto-repair — structures** | `SelfHealing=yes` on every buildable structure | everywhere |
| **Auto-repair — lobby setting** | `chkAutoRepair=true` | CnCNet only |
| **Unlimited money — income** | `ProduceCashDelay` / `ProduceCashAmount` / `ProduceCashStartup` on each faction's Construction Yard | everywhere |
| **Unlimited money — starting credits** | `cmbCredits` | CnCNet only |
| **Speed — production** | `[General] BuildSpeed` | everywhere |
| **Speed — match speed** | `cmbGameSpeedCapSkirmish` / `cmbGameSpeedCapMultiplayer`, optionally `chkDisableGameSpeed` | CnCNet only |

### How the money actually works

Credits climb during the match rather than draining, using the engine's own
Oil Derrick mechanic. Each faction's Construction Yard is given the
`ProduceCash*` rules, so every player collects on a timer whether or not
they are on CnCNet.

Two engine requirements decide whether this works at all, and breaking
either produces no money with no error:

- `ProduceCashDelay` must be **greater than 1**, or the timer never runs.
- `ProduceCashStartup` must be **non-zero**, or the timer never starts.

Every preset therefore ships a real startup payment. The test suite asserts
both rules for every rate, so a future preset cannot quietly break them.

### Why map-side rules overrides are safe

A map can carry `rulesmd.ini` sections, and the engine merges them over the
global rules **key by key** — it does not replace the whole section. That is
what makes a one-line `[GACNST] SelfHealing=yes` safe rather than a way to
erase the Construction Yard.

This is confirmed by real maps in the wild, not just inference: popular
survival maps ship sections such as `[GAREFN] TechLevel=11` with that single
key and play fine. If sections were replaced wholesale, those maps could not
load.

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

- **Forced options need the CnCNet client.** Each one is badged in the UI.
  The upgrades that matter most — income, self-repair, production speed —
  are rules overrides and work everywhere.
- **Income comes from the Construction Yard**, so it stops if that building
  is destroyed or sold, and the AI collects it too.
- **Match speed cannot be forced in the stock game.** It is a lobby setting,
  not a map setting. Production speed is offered instead for those players.
- **Everyone needs the same file.** Editing a map changes it, so every player
  in a match must have the edited copy. The tool renames the map to
  `... [Edited]` so it is easy to tell the versions apart.
- **Map packages (`.mmx`, `.yro`) are not supported.** Extract the `.mpr` or
  `.yrm` from them with XCC Mixer first.
