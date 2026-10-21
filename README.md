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
| **Auto-repair for buildings** | `[IQ] RepairSell=0` | **everywhere** |
| **Never-destroyed buildings** | `RepairPercent` / `RepairStep` / `RepairRate` | everywhere |
| **Repair — slow regeneration** | `SelfHealing=yes` on every buildable structure | everywhere |
| **Repair — CnCNet lobby switch** | `chkAutoRepair=true` | CnCNet only |
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

### How auto-repair works

`[IQ] RepairSell=0`, and that is the whole trick.

The `[IQ]` section holds the minimum IQ a house needs before the engine
does something for it automatically, and `RepairSell` governs choosing to
repair a damaged building instead of selling it. The stock value is `1`,
and the rules file notes that a human-controlled country is presumed to
have an IQ of zero — which is precisely why players never get it.
Lowering the threshold to `0` brings human players in, and their buildings
start repairing the moment they take damage.

Four maps in the test corpus ship `RepairSell=0`, which is where this came
from; a fifth writes the stock `1` explicitly.

**Auto-repair deliberately changes nothing else.** Repair then runs at the
game's own pace and costs its usual credits — the wrench simply switches
itself on. Buildings still lose health under fire and can still be
destroyed, which is the point.

Making that repair free and near-instant is a separate upgrade,
**Never-destroyed buildings**, off by default. It is genuinely
overpowered: a base with it on heals about as fast as it can be damaged.
Keeping the two apart means auto-repair stays a convenience rather than
an invincibility switch.

`SelfHealing=yes` is offered separately and defaults to off. It works on
buildings, but the engine hardcodes it to **one hit point per repair
tick**, so on a thousand-hit-point structure it is invisible during an
attack. The IQ route does the job properly.

`RepairStep` is kept at 25 deliberately: a value above a structure's own
`Strength` crashes the engine when that structure is damaged and repair
begins, and walls are the weakest buildings in the game.

### What the speed upgrade does not touch

`[General] BuildupTime` — the rise-into-place animation after a building
is placed — is left alone on purpose. Shortening it saves no meaningful
time and makes buildings appear out of nowhere, which reads as a glitch.
Queue speed via `BuildSpeed` is where the real gain is, so that is the
only thing changed.

A map that sets its own `BuildupTime` keeps the author's value.

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

## The map preview

Every map carries its own minimap: `[Preview]` gives the dimensions and
`[PreviewPack]` holds the pixels, base64 over numbered lines and
compressed with LZO1X — the same scheme `IsoMapPack5` uses, in the same
chunked frame of two 16-bit sizes per block. Expanded it is three bytes
per pixel.

That means the preview can be shown **without any game assets**. Renderers
like CNCMaps and LightningMap draw a map from the game's own `.mix` files;
this reads an image the map already contains, so there is nothing to ship
or license. `app/preview.py` decodes it and writes a PNG with `zlib`
alone, so there is no imaging library in the dependency list either.

Worst case in the test corpus is 41 ms for a 328x164 preview, which is
fine to serve on request.

## Layout

```
app/
  inifile.py     byte-faithful INI reader/writer — the core guarantee
  mapfile.py     map model, validation, the facts shown in the UI
  preview.py     LZO1X decoder + PNG writer for the embedded minimap
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

It has been run over a corpus of twelve real community maps — `.map`, `.mpr`
and `.yrm`, CRLF and LF, 147 KB to 890 KB, from plain multiplayer maps to a
conversion carrying 2,227 gameplay overrides. All twelve round-trip
byte-identically and take every upgrade without losing a key or introducing
a duplicate.

## What the analysis warns about

Before applying anything, the map page flags two things the corpus showed
matter:

- **The map is heavily modified.** It carries 25 or more gameplay rules
  overrides of its own, so it is a conversion whose balance the author tuned
  deliberately. Light-post retints do not count, since maps change those for
  mood rather than play.
- **The map already pays its players.** Several community maps hand out
  credits through `ProduceCash`, and adding income stacks on top. The warning
  names the buildings and amounts so nobody doubles an economy by accident.

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
