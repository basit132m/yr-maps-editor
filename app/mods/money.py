"""Money.

Two separate levers, because the audience is split between the CnCNet
client and the stock game:

* **Continuous income** writes the ``ProduceCash*`` rules onto each
  faction's Construction Yard, the one structure every player owns exactly
  one of. This is the engine's own Oil Derrick mechanic, so it needs no
  client support and works offline, in skirmish and online alike. It is
  what makes money climb during a match instead of draining away.
* **Starting credits** sets ``cmbCredits`` in ``[ForcedOptions]``, which
  only the CnCNet client reads.

Two engine rules shape how the income tags have to be written, and getting
either wrong silently produces no money at all:

* ``ProduceCashDelay`` must be greater than 1, or the timer never runs.
* ``ProduceCashStartup`` must be non-zero, or the timer never starts.

So every income preset ships a real startup payment, never zero.
"""

from __future__ import annotations

from .base import Change, Choice, Mod, Option

#: One per faction. A player has exactly one Construction Yard, so income
#: does not multiply with the number of refineries or power plants they
#: happen to have built.
CONSTRUCTION_YARDS = ("GACNST", "NACNST", "YACNST")

#: Frames between payments. The game runs at 30 FPS at normal speed, so 30
#: frames is roughly one payment a second. Must be greater than 1.
INCOME_DELAY = 30

#: label -> (credits per payment, one-off payment on game start)
INCOME_RATES = {
    "steady": (50, 2000),
    "generous": (200, 5000),
    "endless": (1000, 10000),
}

INCOME_CHOICES = (
    Choice("generous", "Generous — about 200 credits a second"),
    Choice("steady", "Steady — about 50 credits a second"),
    Choice("endless", "Endless — about 1,000 credits a second"),
)

CREDIT_CHOICES = (
    Choice("0", "100,000 credits (maximum)"),
    Choice("1", "30,000 credits"),
    Choice("8", "2,500 credits (minimum)"),
)


class MoneyMod(Mod):
    id = "money"
    name = "Unlimited money"
    summary = (
        "Credits climb throughout the match instead of running out."
    )
    caveat = (
        "Income is paid by each player's Construction Yard, so it stops if "
        "that Construction Yard is destroyed or sold. The AI benefits from "
        "it too."
    )
    options = (
        Option(
            id="income",
            label="Continuous income (works in every version of the game)",
            kind="bool",
            default="1",
            help=(
                "Each player's Construction Yard pays out on a timer, the "
                "same way an Oil Derrick does. No CnCNet client needed."
            ),
        ),
        Option(
            id="rate",
            label="How fast the money comes in",
            kind="choice",
            default="generous",
            choices=INCOME_CHOICES,
        ),
        Option(
            id="starting",
            label="Also force maximum starting credits (CnCNet only)",
            kind="bool",
            default="1",
            help="Writes cmbCredits.",
            cncnet_only=True,
        ),
        Option(
            id="credits",
            label="Starting credits",
            kind="choice",
            default="0",
            choices=CREDIT_CHOICES,
            cncnet_only=True,
        ),
    )

    def apply(self, ymap, values):
        changes: list[Change] = []

        if self.enabled(values, "income"):
            rate = str(values.get("rate", "generous")).strip().lower()
            if rate not in INCOME_RATES:
                rate = "generous"
            amount, startup = INCOME_RATES[rate]

            for yard in CONSTRUCTION_YARDS:
                ymap.ini.set(yard, "ProduceCashDelay", str(INCOME_DELAY))
                ymap.ini.set(yard, "ProduceCashAmount", str(amount))
                ymap.ini.set(yard, "ProduceCashStartup", str(startup))

            changes.append(
                Change(
                    section="Construction Yards",
                    key="ProduceCashAmount",
                    value=str(amount),
                    note=(
                        f"{amount} credits every {INCOME_DELAY} frames, "
                        f"plus {startup:,} on start"
                    ),
                )
            )

        if self.enabled(values, "starting"):
            credits_index = str(values.get("credits", "0")).strip()
            if credits_index not in {choice.value for choice in CREDIT_CHOICES}:
                credits_index = "0"
            label = next(c.label for c in CREDIT_CHOICES if c.value == credits_index)
            self.write(ymap, changes, "ForcedOptions", "cmbCredits",
                       credits_index, note=label)

        return changes
