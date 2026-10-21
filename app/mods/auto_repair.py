"""Auto-repair.

``[IQ] RepairSell`` is the whole mechanism. The ``[IQ]`` section holds the
minimum IQ a house needs before the engine does something for it
automatically, and ``RepairSell`` governs choosing to repair a damaged
building rather than sell it. The stock value is 1, and the rules file
notes that a human-controlled country is presumed to have an IQ of zero,
which is exactly why players never get it. Lowering the threshold to 0
brings human players in.

Deliberately nothing else. Repair then runs at the game's own pace and
costs its usual credits — the wrench simply switches itself on instead of
waiting to be clicked. Speeding that repair up or making it free turns a
base into something that cannot be destroyed, which is a different
feature living in :mod:`app.mods.never_destroyed`.

A widely played community survival map enables building auto-repair with
this single key and nothing else, which is where it came from.
"""

from __future__ import annotations

from .base import Change, Mod, Option

#: The [IQ] threshold at which a house repairs damaged buildings instead
#: of selling them. Human players count as IQ 0, so 0 includes them; the
#: stock value of 1 is what normally leaves them out.
REPAIR_SELL_IQ = "0"

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
        "The repair wrench switches itself on when a building is hit, then "
        "repairs at the normal speed and cost."
    )
    caveat = (
        "Buildings still lose health while under fire and can still be "
        "destroyed — repair just starts on its own. Repairs cost credits as "
        "usual."
    )
    options = (
        Option(
            id="auto",
            label="Buildings start repairing themselves when attacked",
            kind="bool",
            default="1",
            help=(
                "No clicking needed. Repair runs at the game's normal pace "
                "and costs its normal credits."
            ),
        ),
        Option(
            id="structures",
            label="Buildings also regenerate very slowly on their own",
            kind="bool",
            default="0",
            help=(
                "Free and needs no credits, but the engine fixes this at one "
                "hit point at a time, so it is barely visible."
            ),
        ),
        Option(
            id="forced_option",
            label="Force the CnCNet auto-repair setting on",
            kind="bool",
            default="1",
            help="Writes chkAutoRepair=true.",
            cncnet_only=True,
        ),
    )

    def apply(self, ymap, values):
        changes: list[Change] = []

        if self.enabled(values, "auto"):
            self.write(ymap, changes, "IQ", "RepairSell", REPAIR_SELL_IQ,
                       note="Human players now repair damaged buildings automatically")

        if self.enabled(values, "structures"):
            for building in BUILDINGS:
                ymap.ini.set(building, "SelfHealing", "yes")
            changes.append(
                Change(
                    section=f"{len(BUILDINGS)} building sections",
                    key="SelfHealing",
                    value="yes",
                    note="Structures regenerate one hit point at a time",
                )
            )

        if self.enabled(values, "forced_option"):
            self.write(ymap, changes, "ForcedOptions", "chkAutoRepair", "true",
                       note="CnCNet lobby auto-repair")

        return changes
