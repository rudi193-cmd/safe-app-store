"""
Interventions - Dating Wellbeing Core
Context-aware responses based on analysis results and intake.
"""
from __future__ import annotations


# Reflection questions by intervention level
REFLECTION_QUESTIONS = {
    "none": [
        "What drew you to this person specifically?",
        "How do you feel after interactions with them?",
        "What would your best friend say about this connection?",
        "What pattern from your past might this continue?",
    ],
    "yellow": [
        "What specific behavior is giving you pause?",
        "Have you seen this pattern before in relationships?",
        "What would need to change for you to feel fully comfortable?",
        "Are you rationalizing anything you noticed?",
        "What does your gut say when you're not excited?",
    ],
    "red": [
        "What made you decide to analyze this profile?",
        "How would you feel if a friend described this situation to you?",
        "What would walking away cost you? What would staying cost you?",
        "Is there someone safe you can talk to about this?",
        "What do you need to see change before proceeding?",
    ],
    "danger": [
        "Are you currently safe?",
        "Do you have a trusted person you can contact right now?",
        "What would it take for you to create distance?",
        "What support do you have available to you?",
    ],
}

# Safety resources for danger-level situations
SAFETY_RESOURCES = """
If you are in an unsafe situation:
- National DV Hotline: 1-800-799-7233 (thehotline.org)
- Crisis Text Line: Text HOME to 741741
- RAINN: 1-800-656-4673 (rainn.org)
"""


def generate_response(result, intake) -> str:
    """
    Generate a contextual intervention response.

    Args:
        result: AnalysisResult object
        intake: IntakeAnswers object

    Returns:
        str: Response message tailored to the situation
    """
    level = getattr(result, "intervention_level", "none")
    red_flags = getattr(result, "red_flags", [])
    yellow_flags = getattr(result, "yellow_flags", [])
    score = getattr(result, "score", 50)
    relation = getattr(intake, "relation_to_person", "stranger")

    if level == "danger":
        return _danger_response(red_flags, relation)
    elif level == "red":
        return _red_response(red_flags, relation, score)
    elif level == "yellow":
        return _yellow_response(yellow_flags, relation, score)
    else:
        return _neutral_response(score, relation)


def _neutral_response(score: int, relation: str) -> str:
    if score >= 75:
        msg = "This connection shows real promise. Stay grounded and let it develop naturally."
    elif score >= 55:
        msg = "Nothing critical stands out. Take it at a pace that feels right for you."
    else:
        msg = "Some friction is present - not necessarily a dealbreaker, but worth staying aware."

    if relation == "ex":
        msg += " Given this is an ex-partner, give yourself time to ensure your assessment isn't clouded by history."

    return msg


def _yellow_response(flags: list, relation: str, score: int) -> str:
    flag_names = ", ".join(f.replace("_", " ") for f in flags[:3])
    msg = (
        f"A few patterns worth noticing: {flag_names}. "
        "These aren't dealbreakers on their own, but they deserve attention. "
        "Watch for whether these patterns persist or intensify."
    )
    if relation in ("ex", "hurt_me"):
        msg += " Your history with this person adds additional weight to these signals."
    return msg


def _red_response(flags: list, relation: str, score: int) -> str:
    flag_names = ", ".join(f.replace("_", " ") for f in flags[:3])
    msg = (
        f"Serious concerns detected: {flag_names}. "
        "These patterns are associated with harm in relationships. "
        "Proceed with significant caution - or consider not proceeding at all. "
        "Trust what you noticed enough to analyze."
    )
    if relation == "hurt_me":
        msg += " This person has hurt you before. That history matters."
    return msg


def _danger_response(flags: list, relation: str) -> str:
    return (
        "The patterns here describe potentially unsafe behavior. "
        "Your safety is the priority. "
        "Please consider talking to someone you trust before any further contact. "
        + SAFETY_RESOURCES
    )


def get_reflection_questions(intervention_level: str, count: int = 3) -> list:
    """Return reflection questions appropriate to the intervention level."""
    questions = REFLECTION_QUESTIONS.get(intervention_level, REFLECTION_QUESTIONS["none"])
    return questions[:count]


def determine_intervention_level(red_flags: list, yellow_flags: list, score: int) -> str:
    """Determine intervention level from flag counts and score."""
    danger_flags = {"boundary_violations", "isolation_attempt", "manipulation_tactics", "gaslighting"}
    if any(f in danger_flags for f in red_flags) and len(red_flags) >= 3:
        return "danger"
    elif len(red_flags) >= 2 or score <= 25:
        return "red"
    elif len(red_flags) == 1 or len(yellow_flags) >= 3 or score <= 40:
        return "yellow"
    else:
        return "none"
