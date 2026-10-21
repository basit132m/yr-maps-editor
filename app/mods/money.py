"""Starting credits.

``cmbCredits`` is an index into the CnCNet client's starting-money dropdown,
not an amount: 0 is the largest option the lobby offers. The mapping below
covers the values CnCNet documents; the gaps in their table are left out
rather than guessed at.
"""

from __future__ import annotations

from .base import Change, Choice, Mod, Option

CREDIT_CHOICES = (
    Choice("0", "100,000 credits (maximum)"),
    Choice("1", "30,000 credits"),
    Choice("8", "2,500 credits (minimum)"),
)


class MoneyMod(Mod):
    id = "money"
    name = "Maximum starting money"
    summary = "Every player starts with a huge pile of credits."
    caveat = (
        "100,000 credits is the highest the lobby offers, so this is a very "
        "large starting balance rather than a literally endless one. "
        "Truly endless income needs a repeating map trigger, which is a "
        "planned upgrade."
    )
    options = (
        Option(
            id="credits",
            label="Starting credits",
            kind="choice",
            default="0",
            choices=CREDIT_CHOICES,
            help="Forced on every player, overriding the lobby setting.",
        ),
    )

    def apply(self, ymap, values):
        changes: list[Change] = []
        credits_index = str(values.get("credits", "0")).strip()
        if credits_index not in {choice.value for choice in CREDIT_CHOICES}:
            credits_index = "0"

        label = next(c.label for c in CREDIT_CHOICES if c.value == credits_index)
        self.write(
            ymap, changes, "ForcedOptions", "cmbCredits", credits_index,
            note=label,
        )
        return changes
