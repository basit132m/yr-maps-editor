"""Repair.

Three levers, because the engine offers no single good answer:

* ``SelfHealing=yes`` on a building makes it regenerate with no click and
  no cost, but the engine hardcodes the amount to **one hit point** per
  repair tick. On a structure with a thousand hit points that is invisible
  during a fight. It is worth having for recovery between attacks, not as
  a defence during one.
* The repair cadence and cost are global: ``RepairRate`` is the wait
  between steps, ``RepairStep`` the health each step restores, and
  ``RepairPercent`` the cost of a full repair as a share of the building's
  price. Tightening those makes the repair wrench free and near-instant,
  which is the fastest real repair available without the CnCNet client. It
  still needs the player to click once.
* ``chkAutoRepair`` in ``[ForcedOptions]`` is genuine hands-off
  auto-repair, and only the CnCNet client reads it.

So players on the stock game get fast free repair plus slow regeneration;
players on CnCNet get all of it.
"""

from __future__ import annotations

from .base import Change, Mod, Option

#: Minutes between repair steps. Retail is 0.016, about one step every 14
#: frames; this is roughly eight times quicker.
REPAIR_RATE = ".002"

#: Health restored per step, up from a retail 5-8. Deliberately modest:
#: a RepairStep larger than a structure's own Strength crashes the game
#: when that structure is damaged and repair begins, and the weakest
#: buildings in the game are walls. A real community map ships 35 without
#: trouble, so 25 leaves room.
REPAIR_STEP = "25"

#: Cost of a full repair as a share of the building's price. Zero is free.
REPAIR_PERCENT = "0%"

#: Player-buildable structures across the three YR factions, taken from the
#: [BuildingTypes] list in rulesmd.ini. Civilian props, lamps and dummies are
#: deliberately excluded. An ID the running game does not know is ignored by
#: the engine, so a mod that renames structures costs nothing here.
BUILDINGS: tuple[str, ...] = (
    # Allied
    "GACNST", "GAPOWR", "GAREFN", "GAPILE", "GAWEAP", "GAYARD", "GADEPT",
    "GATECH", "GAAIRC", "GAOREP", "GASPYSAT", "GACSPH", "GAWEAT", "GAGAP",
    "GAROBO", "GAPILL", "ATESLA", "GTGCAN", "GAWALL", "GAFWLL", "GASAND",
    "GAGATE_A", "GAGATE_B",
    # Soviet
    "NACNST", "NAPOWR", "NANRCT", "NAREFN", "NAHAND", "NAWEAP", "NAYARD",
    "NADEPT", "NATECH", "NARADR", "NAINDP", "NACLON", "NAMISL", "NAIRON",
    "NAPSIS", "NALASR", "NAFLAK", "NASAM", "TESLA", "NATBNK", "NABNKR",
    "NAWALL",
    # Yuri
    "YACNST", "YAPOWR", "YAREFN", "YABRCK", "YAWEAP", "YAYARD", "YADEPT",
    "YATECH", "YAGRND", "YAGNTC", "YAPPET", "YAGGUN", "YAPSYT", "YAROCK",
    "YACOMD", "YAPPPT", "YAWALL",
)


class AutoRepairMod(Mod):
    id = "auto_repair"
    name = "Repair"
    summary = "Keeps your base standing: free, fast repairs and slow regeneration."
    caveat = (
        "Only the CnCNet client can repair buildings with no click at all. "
        "In the stock game the wrench still has to be switched on once per "
        "building, but with free repair selected it then costs nothing and "
        "finishes almost instantly."
    )
    options = (
        Option(
            id="fast_repair",
            label="Make repairs free and near-instant",
            kind="bool",
            default="1",
            help=(
                "Repairing costs no credits and finishes in a moment instead "
                "of draining your money while you wait."
            ),
        ),
        Option(
            id="structures",
            label="Buildings also regenerate slowly on their own",
            kind="bool",
            default="1",
            help=(
                "Free and needs no click, but the engine fixes this at one "
                "hit point at a time, so it recovers a base between attacks "
                "rather than surviving one."
            ),
        ),
        Option(
            id="forced_option",
            label="Force the CnCNet auto-repair setting on",
            kind="bool",
            default="1",
            help="Real hands-off auto-repair. Writes chkAutoRepair=true.",
            cncnet_only=True,
        ),
    )

    def apply(self, ymap, values):
        changes: list[Change] = []

        if self.enabled(values, "fast_repair"):
            self.write(ymap, changes, "General", "RepairPercent", REPAIR_PERCENT,
                       note="Repairing costs nothing")
            self.write(ymap, changes, "General", "RepairStep", REPAIR_STEP,
                       note=f"{REPAIR_STEP} health restored per step")
            self.write(ymap, changes, "General", "RepairRate", REPAIR_RATE,
                       note="Steps come about eight times quicker")

        if self.enabled(values, "structures"):
            for building in BUILDINGS:
                ymap.ini.set(building, "SelfHealing", "yes")
            changes.append(
                Change(
                    section=f"{len(BUILDINGS)} building sections",
                    key="SelfHealing",
                    value="yes",
                    note="Structures regenerate slowly with no click",
                )
            )

        if self.enabled(values, "forced_option"):
            self.write(ymap, changes, "ForcedOptions", "chkAutoRepair", "true",
                       note="CnCNet hands-off auto-repair")

        return changes
