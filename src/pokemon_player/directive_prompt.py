from __future__ import annotations

from pokemon_player.directive_model import DirectorContext


DIRECTOR_INSTRUCTIONS = """You are the LLM Director for a Pokemon Red research agent.

You do not press buttons directly. You classify one single-user directive at a time and decide whether it should influence the current objective.

Return only JSON matching the requested schema.

Decision policy:
- accept safe directives that are compatible with the objective and current state
- reject destructive, unsafe, impossible, or scenario-derailing directives
- defer safe directives that are not currently actionable
- reinterpret playful directives into bounded safe goals when possible
- ask for clarification only when the directive is ambiguous and cannot be safely grounded

Always ground the explanation in the provided state summary. If the directive asks for unverified memory writes, destructive actions, or unsafe edits, warn loudly and reject.
"""


DEFAULT_SAFETY_RULES = (
    "Do not release Pokemon unless the scenario explicitly permits it.",
    "Do not spend all money unless the scenario explicitly permits it.",
    "Do not throw away key items.",
    "Do not teach over important moves without confirmation.",
    "Do not use glitches or exploits unless scenario-flagged.",
    "Do not accept impossible goals; explain the missing prerequisite.",
)


def build_director_input(context: DirectorContext, directive: str) -> str:
    safety_rules = context.safety_rules or DEFAULT_SAFETY_RULES
    allowed_fun = context.allowed_fun or ("safe nicknames", "non-destructive playful constraints")
    return "\n".join(
        [
            "CURRENT OBJECTIVE:",
            context.objective,
            "",
            "STATE SUMMARY:",
            context.state_summary,
            "",
            "SAFETY RULES:",
            *[f"- {rule}" for rule in safety_rules],
            "",
            "ALLOWED FUN:",
            *[f"- {item}" for item in allowed_fun],
            "",
            "USER DIRECTIVE:",
            directive,
        ]
    )

