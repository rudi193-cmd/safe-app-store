from .models import Profile, IntakeAnswers, AnalysisResult
from .redflags import scan_red_flags, get_flag_explanation
from .scoring import calculate_score, score_to_category, apply_intake_modifiers
from .interventions import (
    generate_response, get_reflection_questions, determine_intervention_level
)


def analyze_profile(profile: Profile, intake: IntakeAnswers, history=None) -> AnalysisResult:
    """Full profile analysis pipeline."""
    red_flags, yellow_flags = scan_red_flags(profile)

    base_score = calculate_score(
        profile,
        user_prefs={},
        red_flags=red_flags,
        yellow_flags=yellow_flags,
    )
    score = apply_intake_modifiers(base_score, intake)
    category = score_to_category(score)
    intervention_level = determine_intervention_level(red_flags, yellow_flags, score)

    # Depth vs fantasy heuristic
    bio_len = len(getattr(profile, "bio", ""))
    has_photos = bool(getattr(profile, "photos", []))
    if bio_len > 150 and not red_flags:
        depth_vs_fantasy = "depth"
    elif red_flags or bio_len < 50:
        depth_vs_fantasy = "fantasy"
    else:
        depth_vs_fantasy = "mixed"

    reflection_qs = get_reflection_questions(intervention_level, count=3)

    result = AnalysisResult(
        score=score,
        category=category,
        depth_vs_fantasy=depth_vs_fantasy,
        red_flags=red_flags,
        yellow_flags=yellow_flags,
        intervention_level=intervention_level,
        recommendation=generate_response(
            type("R", (), {
                "intervention_level": intervention_level,
                "red_flags": red_flags,
                "yellow_flags": yellow_flags,
                "score": score,
            })(),
            intake,
        ),
        reflection_questions=reflection_qs,
        confidence=_confidence(profile, red_flags, yellow_flags),
    )
    return result


def _confidence(profile, red_flags, yellow_flags) -> float:
    """Estimate confidence in analysis based on data richness."""
    bio_len = len(getattr(profile, "bio", ""))
    raw_len = len(getattr(profile, "raw_text", ""))
    total_text = bio_len + raw_len
    if total_text > 500:
        base = 0.85
    elif total_text > 200:
        base = 0.70
    else:
        base = 0.50
    # More flags = higher confidence (we found something)
    if red_flags:
        base = min(0.95, base + 0.05)
    return round(base, 2)
