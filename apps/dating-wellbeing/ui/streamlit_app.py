"""
Dating Wellbeing Core - Streamlit UI
3-step flow: Profile Input -> Intake Assessment -> Results
Privacy-first: no data leaves the device.
"""
import streamlit as st
from core.analyzer import analyze_profile
from core.models import Profile, IntakeAnswers
from core.redflags import get_flag_explanation, get_flag_severity

st.set_page_config(page_title="Dating Wellbeing Core", page_icon="heart", layout="centered", initial_sidebar_state="collapsed")
if "step" not in st.session_state: st.session_state.step = 1
if "profile" not in st.session_state: st.session_state.profile = None
if "intake" not in st.session_state: st.session_state.intake = None
if "result" not in st.session_state: st.session_state.result = None

def go_to(step): st.session_state.step = step

st.title("Dating Wellbeing Core")
st.caption("Private. Local. No data leaves your device.")
step_labels = {1: "1. Profile", 2: "2. Context", 3: "3. Results"}
progress = (st.session_state.step - 1) / 2
st.progress(progress, text=step_labels.get(st.session_state.step, ""))
st.divider()
if st.session_state.step == 1:
    st.subheader("Their Profile")
    st.caption("Paste their bio, messages, or any text. Photos stay local.")
    bio = st.text_area("Bio / About section", height=120)
    raw_text = st.text_area("Additional text (messages, notes)", height=100)
    col1, col2 = st.columns(2)
    with col1:
        age = st.number_input("Their age (optional)", min_value=18, max_value=99, value=None, step=1)
    with col2:
        relationship_goal = st.selectbox("Their stated goal (optional)", options=["", "casual", "serious", "friendship", "unclear"])
    if st.button("Next", type="primary", use_container_width=True):
        if not bio.strip() and not raw_text.strip():
            st.warning("Add at least some profile text to analyze.")
        else:
            st.session_state.profile = Profile(bio=bio.strip(), raw_text=raw_text.strip(), age=int(age) if age else None, relationship_goal=relationship_goal or None)
            go_to(2)
            st.rerun()

elif st.session_state.step == 2:
    st.subheader("Your Context")
    st.caption("This helps calibrate the analysis for your specific situation.")
    relation = st.radio("Your relationship to this person", options=["stranger", "acquaintance", "ex", "coworker", "hurt_me"], format_func=lambda x: {"stranger": "Stranger / met online", "acquaintance": "Acquaintance / know of them", "ex": "Ex-partner", "coworker": "Coworker / professional context", "hurt_me": "Someone who has hurt me before"}.get(x, x), horizontal=False)
    why_now = st.text_input("Why are you analyzing this now?")
    emotional_state = st.text_area("How are you feeling right now?", height=80)
    work_done = st.text_area("What relationship work have you done on yourself?", height=80)
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Back", use_container_width=True): go_to(1); st.rerun()
    with col2:
        if st.button("Analyze", type="primary", use_container_width=True):
            if not why_now.strip():
                st.warning("Add a brief note about why you are analyzing this.")
            else:
                st.session_state.intake = IntakeAnswers(relation_to_person=relation, why_now=why_now.strip(), emotional_state=emotional_state.strip() or "not specified", relationship_work_done=work_done.strip() or "not specified")
                with st.spinner("Analyzing..."):
                    st.session_state.result = analyze_profile(st.session_state.profile, st.session_state.intake)
                go_to(3)
                st.rerun()

elif st.session_state.step == 3:
    result = st.session_state.result
    if result is None:
        st.error("No result found. Please start over.")
        if st.button("Start over"): go_to(1); st.rerun()
        st.stop()
    score = result.score
    cat = result.category
    level = result.intervention_level
    SCORE_COLORS = {"incompatible": "red", "surface": "orange", "good_enough": "blue", "strong": "green", "exceptional": "green"}
    cat_label = cat.replace("_", " ").title()
    col1, col2 = st.columns([1, 2])
    with col1:
        st.metric("Compatibility Score", f"{score}/100")
        st.caption(f"Category: **{cat_label}**")
    with col2:
        st.progress(score / 100)
        if level == "danger": st.error("Serious safety concerns detected.")
        elif level == "red": st.warning("Significant red flags present.")
        elif level == "yellow": st.info("Some patterns worth watching.")
        else: st.success("No major concerns detected.")
    st.divider()
    st.subheader("Analysis")
    st.write(result.recommendation)
    if result.red_flags:
        st.subheader("Red Flags")
        for flag in result.red_flags:
            with st.expander(f"[RED] {flag.replace(chr(95), chr(32)).title()}"):
                st.write(get_flag_explanation(flag))
    if result.yellow_flags:
        st.subheader("Yellow Flags")
        for flag in result.yellow_flags:
            with st.expander(f"[YELLOW] {flag.replace(chr(95), chr(32)).title()}"):
                st.write(get_flag_explanation(flag))
    if result.reflection_questions:
        st.subheader("Reflection Questions")
        for q in result.reflection_questions: st.write(f"- {q}")
    st.divider()
    st.caption(f"Confidence: {result.confidence:.0%} | Depth vs Fantasy: {result.depth_vs_fantasy.title()} | Data: {len(st.session_state.profile.bio) + len(st.session_state.profile.raw_text)} chars")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Back to Context", use_container_width=True): go_to(2); st.rerun()
    with col2:
        if st.button("Start New Analysis", type="primary", use_container_width=True):
            for k in ("step", "profile", "intake", "result"): del st.session_state[k]
            st.rerun()
    st.caption("All analysis runs locally. Nothing is stored unless you choose to save.")
