"""Game speed.

CnCNet exposes the starting speed as a dropdown index, and the index means
different frame rates in skirmish and in multiplayer, so both keys are
written from one user-facing choice. Players can still move the slider
mid-game unless the slider is locked.
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

SPEED_CHOICES = (
    Choice("fastest", "Fastest (max FPS in skirmish, 60 FPS online)"),
    Choice("fast", "Fast (60 FPS skirmish, 45 FPS online)"),
    Choice("normal", "Normal (30 FPS, the game default)"),
)


class GameSpeedMod(Mod):
    id = "game_speed"
    name = "Game speed"
    summary = "Sets the speed the match starts at."
    options = (
        Option(
            id="speed",
            label="Starting speed",
            kind="choice",
            default="fastest",
            choices=SPEED_CHOICES,
        ),
        Option(
            id="lock",
            label="Lock the speed slider so players cannot change it",
            kind="bool",
            default="0",
            help="Writes chkDisableGameSpeed=true, hiding the slider entirely.",
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

        if self.enabled(values, "lock"):
            self.write(ymap, changes, "ForcedOptions", "chkDisableGameSpeed",
                       "true", note="Speed slider hidden in the lobby")

        return changes
