"""
Scoring - Dating Wellbeing Core
0-100 compatibility score with intake modifiers.

Scoring logic:
- Start at 50 (neutral)
- +/- based on profile signals
- Red flags: -12 each (capped at -40 total)
- Yellow flags: -5 each (capped at -15 total)
- Intake modifiers: emotional state, relation type
- Category thresholds: 0-20=incompatible, 21-40=surface, 41-60=good_enough, 61-80=strong, 81-100=exceptional
"""


def calculate_score(profile, user_prefs: dict, red_flags=None, yellow_flags=None) -> int:
    """
    Calculate 0-100 compatibility score.

    Args:
        profile: Profile object with bio, raw_text, age, relationship_goal
        user_prefs: Dict with optional keys: preferred_age_range, relationship_goals
        red_flags: List of red flag categories already detected
        yellow_flags: List of yellow flag categories already detected

    Returns:
        int: 0-100 score
    """
    if red_flags is None:
        red_flags = []
    if yellow_flags is None:
        yellow_flags = []

    score = 50  # neutral baseline

    # Red flag deductions (serious)
    red_penalty = min(40, len(red_flags) * 12)
    score -= red_penalty

    # Yellow flag deductions (cautionary)
    yellow_penalty = min(15, len(yellow_flags) * 5)
    score -= yellow_penalty

    # Goal alignment bonus
    if user_prefs.get("relationship_goals") and getattr(profile, "relationship_goal", None):
        if profile.relationship_goal == user_prefs["relationship_goals"]:
            score += 10
        else:
            score -= 8

    # Age compatibility bonus (if both parties have ages)
    age_range = user_prefs.get("preferred_age_range")
    profile_age = getattr(profile, "age", None)
    if age_range and profile_age:
        try:
            min_age, max_age = age_range
            if min_age <= profile_age <= max_age:
                score += 5
            elif abs(profile_age - min_age) <= 5 or abs(profile_age - max_age) <= 5:
                score += 2
            else:
                score -= 5
        except (TypeError, ValueError):
            pass

    # Bio length signal (engaged profiles tend to have more substance)
    bio = getattr(profile, "bio", "")
    if len(bio) > 200:
        score += 3
    elif len(bio) < 30:
        score -= 3

    return max(0, min(100, score))


def score_to_category(score: int) -> str:
    if score <= 20:
        return "incompatible"
    elif score <= 40:
        return "surface"
    elif score <= 60:
        return "good_enough"
    elif score <= 80:
        return "strong"
    else:
        return "exceptional"


def apply_intake_modifiers(base_score: int, intake) -> int:
    """
    Adjust score based on user intake answers.

    - Ex-partner: additional -10 (reflection period bias)
    - Hurt me: additional -15 (high scrutiny)
    - Poor emotional state: results are less reliable, apply caution cap
    """
    score = base_score
    relation = getattr(intake, "relation_to_person", "stranger")

    if relation == "ex":
        score -= 10
    elif relation == "hurt_me":
        score -= 15

    # Emotional state check - cap optimistic scores when user is vulnerable
    emotional_state = getattr(intake, "emotional_state", "").lower()
    vulnerable_signals = ("lonely", "desperate", "heartbroken", "depressed", "isolated",
                          "needy", "anxious", "scared", "afraid")
    if any(s in emotional_state for s in vulnerable_signals):
        # Cap at 70 - over-optimistic readings when vulnerable are unreliable
        score = min(score, 70)

    return max(0, min(100, score))
