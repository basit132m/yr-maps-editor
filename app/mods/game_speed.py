"""Game speed.

Two different things wear the name "speed", and only one of them is a map
setting:

* **Match speed** is a lobby setting. CnCNet exposes it as a dropdown
  index, and the index means different frame rates in skirmish and in
  multiplayer, so both keys are written from one user-facing choice.
  The stock game has no equivalent a map can set.
* **Production speed** is ``[General] BuildSpeed``, a genuine rules value
  a map can override, so it works in every version of the game. It is the
  number of minutes a 1000-credit item takes to build, calculated as
  ``(Cost / 1000) * BuildSpeed``, so lower is faster. The stock value is
  0.7, and community maps run anywhere from 0.1 to 0.55.
``[General] BuildupTime`` is deliberately left alone. It is the rise-into-
place animation after a building is placed, and shortening it does not
save meaningful time — it just makes buildings appear out of nowhere,
which looks broken. Queue speed is where the real gain is.
"""

from __future__ import annotations

from .base import Change, Choice, Mod, Option

#: user choice -> (skirmish index, multiplayer index)
#: Skirmish: 0 = MAX FPS, 1 = 60, 2 = 30. Multiplayer: 0 = 60, 1 = 45, 2 = 30.
SPEED_MAP = {
    "fastest": ("0", "0"),
    "fast": ("1", "1"),
    "normal": ("2", "2"),
}

#: [General] BuildSpeed. "normal" leaves the game's own value alone.
BUILD_SPEED_MAP = {
    "normal": None,
    "fast": "0.35",
    "faster": "0.15",
    "instant": "0.10",
}

BUILD_SPEED_CHOICES = (
    Choice("fast", "Fast — about twice as quick"),
    Choice("faster", "Very fast — about four times as quick"),
    Choice("instant", "Near-instant — about seven times quicker"),
    Choice("normal", "Leave unchanged"),
)

SPEED_CHOICES = (
    Choice("fastest", "Fastest (max FPS in skirmish, 60 FPS online)"),
    Choice("fast", "Fast (60 FPS skirmish, 45 FPS online)"),
    Choice("normal", "Normal (30 FPS, the game default)"),
)


class GameSpeedMod(Mod):
    id = "game_speed"
    name = "Game speed"
    summary = "Sets the speed the match starts at."
    caveat = (
        "Game speed is a lobby setting, so only the CnCNet client can be "
        "told to force it. Players on the stock game set their own speed."
    )
    options = (
        Option(
            id="speed",
            label="Starting speed",
            kind="choice",
            default="fastest",
            choices=SPEED_CHOICES,
            cncnet_only=True,
        ),
        Option(
            id="build_speed",
            label="Production speed (works in every version of the game)",
            kind="choice",
            default="fast",
            choices=BUILD_SPEED_CHOICES,
            help=(
                "Overrides [General] BuildSpeed so buildings and units come "
                "out of the queue sooner. No CnCNet client needed."
            ),
        ),
        Option(
            id="lock",
            label="Lock the speed slider so players cannot change it",
            kind="bool",
            default="0",
            help="Writes chkDisableGameSpeed=true, hiding the slider entirely.",
            cncnet_only=True,
        ),
    )

    def apply(self, ymap, values):
        changes: list[Change] = []
        speed = str(values.get("speed", "fastest")).strip().lower()
        if speed not in SPEED_MAP:
            speed = "fastest"
        skirmish, multiplayer = SPEED_MAP[speed]
        label = next(c.label for c in SPEED_CHOICES if c.value == speed)

        self.write(ymap, changes, "ForcedOptions", "cmbGameSpeedCapSkirmish",
                   skirmish, note=label)
        self.write(ymap, changes, "ForcedOptions", "cmbGameSpeedCapMultiplayer",
                   multiplayer, note=label)

        build_speed = str(values.get("build_speed", "fast")).strip().lower()
        if build_speed in BUILD_SPEED_MAP and BUILD_SPEED_MAP[build_speed]:
            label = next(c.label for c in BUILD_SPEED_CHOICES if c.value == build_speed)
            self.write(ymap, changes, "General", "BuildSpeed",
                       BUILD_SPEED_MAP[build_speed], note=label)

        if self.enabled(values, "lock"):
            self.write(ymap, changes, "ForcedOptions", "chkDisableGameSpeed",
                       "true", note="Speed slider hidden in the lobby")

        return changes
