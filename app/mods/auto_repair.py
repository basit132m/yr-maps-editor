"""Repair.

``[IQ] RepairSell`` is the one that matters. The ``[IQ]`` section holds the
minimum IQ a house needs before the engine will do something for it
automatically, and ``RepairSell`` governs choosing to repair a damaged
building rather than sell it. The stock value is 1, and the rules file
notes that a human-controlled country is presumed to have an IQ of zero —
which is exactly why players never get it. Lowering the threshold to 0
brings human players in, and their buildings start repairing themselves
the moment they take damage.

This is not a guess. A widely played community survival map turns on
building auto-repair with that single key and nothing else: no
SelfHealing, no repair-rate changes.

The rest are supporting cast:

* ``RepairRate``, ``RepairStep`` and ``RepairPercent`` are the global
  cadence and cost of a repair. Making repairs free matters more than it
  looks here, because what RepairSell really unlocks is a *choice* between
  repairing and selling, decided on cost. At zero cost there is never a
  reason to sell.
* ``SelfHealing=yes`` makes a building regenerate with no click and no
  cost, but the engine hardcodes it to **one hit point** per tick, which
  on a thousand-hit-point structure is invisible. Off by default; the IQ
  route does the job properly.
* ``chkAutoRepair`` in ``[ForcedOptions]`` is the CnCNet client's own
  auto-repair switch, and only that client reads it.
"""

from __future__ import annotations

from .base import Change, Mod, Option

#: The [IQ] threshold at which a house repairs damaged buildings instead
#: of selling them. Human players count as IQ 0, so 0 includes them; the
#: stock value of 1 is what normally leaves them out.
REPAIR_SELL_IQ = "0"

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
    name = "Auto-repair for buildings"
    summary = (
        "Damaged buildings start repairing themselves the moment they are "
        "attacked, with no clicking."
    )
    caveat = (
        "Auto-repair works by letting the game choose between repairing a "
        "damaged building and selling it. Keep free repairs switched on and "
        "repairing is always the cheaper choice."
    )
    options = (
        Option(
            id="auto",
            label="Buildings repair themselves when attacked",
            kind="bool",
            default="1",
            help=(
                "No clicking needed. The same trick popular survival maps "
                "use, and it works in every version of the game."
            ),
        ),
        Option(
            id="fast_repair",
            label="Make those repairs free and near-instant",
            kind="bool",
            default="1",
            help=(
                "Repairing costs no credits and finishes in a moment. Also "
                "stops the game ever preferring to sell a damaged building."
            ),
        ),
        Option(
            id="structures",
            label="Buildings also regenerate very slowly on their own",
            kind="bool",
            default="0",
            help=(
                "The engine fixes this at one hit point at a time, so it is "
                "barely visible. The option above is the one that works."
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

        if self.enabled(values, "auto"):
            self.write(ymap, changes, "IQ", "RepairSell", REPAIR_SELL_IQ,
                       note="Human players now repair damaged buildings automatically")

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
