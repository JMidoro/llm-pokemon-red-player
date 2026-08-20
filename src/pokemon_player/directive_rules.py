from __future__ import annotations

from pokemon_player.directive_model import (
    DirectiveCategory,
    DirectiveDecision,
    DirectiveRisk,
    DirectorContext,
    DirectorDecision,
)


DESTRUCTIVE_TERMS = (
    "release",
    "throw away",
    "toss",
    "discard",
    "delete",
    "overwrite",
    "spend all",
    "waste all",
    "use all",
)

IMPOSSIBLE_CATCH_TERMS = ("catch", "capture")
DERAILING_TERMS = (
    "elite four",
    "start over",
    "ignore the objective",
    "walk in circles",
    "softlock",
    "leave forever",
)
AMBIGUOUS_TERMS = (
    "go back",
    "use the bird",
    "do it",
    "that one",
    "take the shortcut",
    "switch them",
    "handle it",
)
PLAYFUL_TERMS = (
    "act mysterious",
    "be dramatic",
    "style points",
    "taunt",
    "show off",
    "be polite",
    "look confident",
)


def classify_directive_offline(context: DirectorContext, directive: str) -> DirectorDecision:
    text = directive.lower()
    summary = context.state_summary.lower()

    if any(term in text for term in DESTRUCTIVE_TERMS):
        return DirectorDecision(
            directive=directive,
            category=DirectiveCategory.DESTRUCTIVE,
            risk=DirectiveRisk.HIGH,
            decision=DirectiveDecision.REJECT,
            explanation="The directive asks for a destructive action that violates the safety rules.",
            warnings=("destructive directive rejected",),
        )

    if any(term in text for term in DERAILING_TERMS):
        return DirectorDecision(
            directive=directive,
            category=DirectiveCategory.DERAILING,
            risk=DirectiveRisk.HIGH,
            decision=DirectiveDecision.REJECT,
            explanation="The directive would derail the current objective or create a non-progress loop.",
            warnings=("derailing directive rejected",),
        )

    if any(term in text for term in AMBIGUOUS_TERMS):
        return DirectorDecision(
            directive=directive,
            category=DirectiveCategory.AMBIGUOUS,
            risk=DirectiveRisk.MEDIUM,
            decision=DirectiveDecision.ASK_CLARIFICATION,
            explanation="The directive is ambiguous in the current state and needs a clearer target.",
        )

    if any(term in text for term in IMPOSSIBLE_CATCH_TERMS) and "no poke balls" in summary:
        return DirectorDecision(
            directive=directive,
            category=DirectiveCategory.IMPOSSIBLE,
            risk=DirectiveRisk.MEDIUM,
            decision=DirectiveDecision.DEFER,
            explanation="Catching is not currently actionable because the state summary says no Poke Balls are available.",
            bounded_goal="obtain_poke_balls_before_catching",
        )

    if "don't" in text or "do not" in text or "avoid" in text or "only" in text or "without" in text:
        return DirectorDecision(
            directive=directive,
            category=DirectiveCategory.CONSTRAINT,
            risk=DirectiveRisk.MEDIUM,
            decision=DirectiveDecision.ACCEPT,
            explanation="The directive is a bounded constraint and does not appear destructive.",
            constraints=(directive,),
        )

    if "nickname" in text or "name " in text:
        return DirectorDecision(
            directive=directive,
            category=DirectiveCategory.COSMETIC,
            risk=DirectiveRisk.LOW,
            decision=DirectiveDecision.ACCEPT,
            explanation="The directive is cosmetic and can be applied when a naming opportunity appears.",
            bounded_goal="apply_safe_nickname_when_prompted",
        )

    if "buy" in text:
        return DirectorDecision(
            directive=directive,
            category=DirectiveCategory.STRATEGIC,
            risk=DirectiveRisk.LOW,
            decision=DirectiveDecision.ACCEPT,
            explanation="The directive is a bounded resource-acquisition goal.",
            bounded_goal=directive,
        )

    if "potion" in text:
        if "potion" not in summary:
            return DirectorDecision(
                directive=directive,
                category=DirectiveCategory.IMPOSSIBLE,
                risk=DirectiveRisk.MEDIUM,
                decision=DirectiveDecision.DEFER,
                explanation="Using a Potion is not actionable because no Potion is visible in the state summary.",
                bounded_goal="obtain_or_save_healing_before_using_potion",
            )
        if "hp 0/" in summary or "hp 1/" in summary or "hp 2/" in summary or "hp 3/" in summary:
            return DirectorDecision(
                directive=directive,
                category=DirectiveCategory.STRATEGIC,
                risk=DirectiveRisk.LOW,
                decision=DirectiveDecision.ACCEPT,
                explanation="The directive is state-grounded because the party has a low-HP member.",
                bounded_goal="use_healing_item_if_available",
            )
        return DirectorDecision(
            directive=directive,
            category=DirectiveCategory.STRATEGIC,
            risk=DirectiveRisk.LOW,
            decision=DirectiveDecision.DEFER,
            explanation="Using a Potion is safe but not clearly needed from the current state summary.",
            bounded_goal="save_potion_until_low_hp",
        )

    if "antidote" in text:
        if "poison" in summary:
            return DirectorDecision(
                directive=directive,
                category=DirectiveCategory.STRATEGIC,
                risk=DirectiveRisk.LOW,
                decision=DirectiveDecision.ACCEPT,
                explanation="The directive is state-grounded because the party has poison status.",
                bounded_goal="use_antidote_if_available",
            )
        return DirectorDecision(
            directive=directive,
            category=DirectiveCategory.STRATEGIC,
            risk=DirectiveRisk.LOW,
            decision=DirectiveDecision.DEFER,
            explanation="Using an Antidote is safe but no poison status is visible in the current state summary.",
            bounded_goal="save_antidote_until_poisoned",
        )

    if (
        "catch" in text
        or "capture" in text
        or "fight" in text
        or "battle" in text
        or "train" in text
        or "heal" in text
        or "switch" in text
        or "go to" in text
        or "enter" in text
        or "use thunder" in text
    ):
        return DirectorDecision(
            directive=directive,
            category=DirectiveCategory.STRATEGIC,
            risk=DirectiveRisk.LOW,
            decision=DirectiveDecision.ACCEPT,
            explanation="The directive is compatible with Pokemon progression and can be compiled into a bounded goal.",
            bounded_goal=directive,
        )

    if any(term in text for term in PLAYFUL_TERMS):
        return DirectorDecision(
            directive=directive,
            category=DirectiveCategory.PLAYFUL,
            risk=DirectiveRisk.LOW,
            decision=DirectiveDecision.REINTERPRET,
            explanation="The directive is safe flavor and should be reinterpreted without changing the objective.",
            bounded_goal="preserve_current_objective_with_playful_flavor",
        )

    return DirectorDecision(
        directive=directive,
        category=DirectiveCategory.PLAYFUL,
        risk=DirectiveRisk.LOW,
        decision=DirectiveDecision.REINTERPRET,
        explanation="The directive is safe but underspecified, so it should be treated as flavor unless it becomes actionable.",
        bounded_goal="preserve_current_objective_with_playful_flavor",
    )
