"""Auto-repair for base structures.

Two independent levers, because they work in different places:

* ``chkAutoRepair`` in ``[ForcedOptions]`` is read by the CnCNet client and
  forces the lobby's auto-repair setting on. It needs the CnCNet client
  (2.0.9.1 or newer) and does nothing in the stock game.
* ``SelfHealing=yes`` written onto each building type is a map-embedded
  rules override. ModEnc records SelfHealing as valid for buildings, and in
  RA2/YR a self-healing object repairs all the way back to full health.
  This one also works offline and in the stock game.
"""

from __future__ import annotations

from .base import Change, Mod, Option

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
        "Damaged base structures repair themselves instead of needing the "
        "repair wrench."
    )
    caveat = (
        "Structure self-repair is written as a map-side rules override. "
        "Test the output map once in-game before sharing it widely."
    )
    options = (
        Option(
            id="forced_option",
            label="Force the CnCNet auto-repair lobby setting on",
            kind="bool",
            default="1",
            help="Writes chkAutoRepair=true.",
            cncnet_only=True,
        ),
        Option(
            id="structures",
            label="Make all base structures self-repair",
            kind="bool",
            default="1",
            help=(
                "Writes SelfHealing=yes for every buildable structure. "
                "Also works in the stock game and offline."
            ),
        ),
    )

    def apply(self, ymap, values):
        changes: list[Change] = []

        if self.enabled(values, "forced_option"):
            self.write(
                ymap, changes, "ForcedOptions", "chkAutoRepair", "true",
                note="CnCNet lobby setting forced on",
            )

        if self.enabled(values, "structures"):
            for building in BUILDINGS:
                ymap.ini.set(building, "SelfHealing", "yes")
            changes.append(
                Change(
                    section=f"{len(BUILDINGS)} building sections",
                    key="SelfHealing",
                    value="yes",
                    note="Every buildable structure regenerates health",
                )
            )

        return changes
