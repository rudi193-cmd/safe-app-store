import streamlit as st
import json
import os
import sys

# SAP gate check
try:
    sys.path.insert(0, os.environ.get("WILLOW_ROOT", os.path.expanduser("~/github/willow-1.7")))
    from sap.core.gate import authorized as _sap_authorized
    if not _sap_authorized("Game"):
        st.error("SAP gate denied — SAFE/Applications/Game/ not authorized.")
        st.stop()
except ImportError:
    pass  # SAP library not available in this environment

# --- IMPORT CORE LOGIC ---
try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from engine_v1_7 import Engine, BASE_STAT 
    
    if 'engine' not in st.session_state:
        st.session_state.engine = Engine()
    
    if 'game_active' not in st.session_state:
        st.session_state.game_active = False 
    if 'output' not in st.session_state:
        st.session_state.output = "Awaiting Character Creation..."

except ImportError:
    st.error("FATAL ERROR: Cannot find engine_v1_7.py. Ensure it is in the same folder and named correctly (engine_v1_7.py).")
    st.stop()


# --- CONFIGURATION AND HELPER FUNCTIONS ---
engine = st.session_state.engine
REQUIRED_POINT_SUM = 2 
BASE_STAT = engine.BASE_STAT
# The mapping from PC Name to Operational Metric Name for display purposes
OPERATIONAL_MAP = {"Grit": "Integrity", "Weird": "Synthesis", "Cute": "Trust", "Cool": "Efficiency"}

def reset_game_state():
    """Resets the engine and session state for a new game."""
    st.session_state.engine = Engine()
    st.session_state.game_active = False
    st.session_state.output = "Game concluded. Ready for new character setup."
    try:
        engine._save_state() 
    except Exception:
        pass 
    st.rerun()

def get_stat_color(value):
    """Returns color based on the stat value relative to the base."""
    if value >= BASE_STAT:
        return "#38a169"  # Green
    elif value < 0:
        return "#e53e3e"  # Red
    else:
        return "#dd6b20"  # Orange

def get_stat_from_text(action_text):
    """[Auto-Stat Protocol] Logic to map player text to the most appropriate stat."""
    text = action_text.lower()
    keywords = {
        "Grit": ["fight", "endure", "resist", "charge", "body"],
        "Weird": ["analyze", "figure", "decipher", "research", "hack", "logic"],
        "Cute": ["convince", "lie", "charm", "persuade", "negotiate", "rally"],
        "Cool": ["aim", "shoot", "sneak", "balance", "drive", "pilot", "escape"]
    }
    scores = {stat: 0 for stat in keywords}
    for stat, keys in keywords.items():
        for key in keys:
            if key in text:
                scores[stat] += 1
    
    best_stat = max(scores, key=scores.get)
    return best_stat.capitalize() if scores[best_stat] > 0 else "Grit"

def handle_roll_command(action_text):
    if not st.session_state.game_active:
        st.session_state.output = "Please launch the game by completing character creation first."
        return

    if not action_text:
        st.session_state.output = "Error: Please describe your action first."
        return

    stat_name = get_stat_from_text(action_text)
    
    result, status = engine.roll(stat_name, is_creator=False)
    
    outcome = f"**STAT USED:** {stat_name.upper()} | **ROLL:** {result} | **OUTCOME:** {status}"
    
    if status == 'CHAOS_BURST':
        engine.apply_debility(stat_name)
        st.session_state.output = f"""
        {outcome}
        <p style='color: red; font-weight: bold;'>🚨 CHAOS BURST DETECTED! {stat_name} Debility Applied.</p>
        <p>[AIGM Narrative: The consequences of this failure are severe. Your attempt failed because the {stat_name.lower()} was insufficient.]</p>
        """
    else:
        st.session_state.output = outcome
        

def handle_restore_command(stat_name):
    if engine.stats[OPERATIONAL_MAP[stat_name]] < BASE_STAT: # Uses Operational Metric
        engine.restore_debility(stat_name)
        st.session_state.output = f"<p style='color: green; font-weight: bold;'>✅ {stat_name} RESTORATION PROTOCOL COMPLETE.</p>"
    else:
        st.session_state.output = f"<p style='color: orange;'>Status: {stat_name} is already fully restored (+{engine.stats[OPERATIONAL_MAP[stat_name]]}).</p>"

def launch_game(pc_name, pc_concept, final_stats):
    """Finalizes game state and launches the active interface."""
    # The stats passed here are the PC stats (Grit/Weird). We need to convert them to Operational Metrics for the save file.
    operational_stats = {OPERATIONAL_MAP[k]: v for k, v in final_stats.items()}
    
    # Check current operational health before overwriting PC stats
    current_health = {k: engine.stats[k] for k in engine.stats}

    # Save the PC's chosen stats to the Operational Metrics file for the game session
    engine.stats = operational_stats
    engine._save_state()
    
    st.session_state.game_active = True
    st.session_state.pc_name = pc_name
    st.session_state.pc_concept = pc_concept

    initial_prompt = f"Welcome, {st.session_state.pc_name}. As a {st.session_state.pc_concept}, you find yourself facing an immediate and complex challenge. Your current stats are: Grit({final_stats['Grit']}), Weird({final_stats['Weird']}), Cute({final_stats['Cute']}), Cool({final_stats['Cool']}). What is your first action?"
    st.session_state.output = initial_prompt
    st.rerun()


# --- NEW: RENDER GAME SETUP SCREEN (v1.5.0.0) ---

def render_character_creation():
    """Renders the two-column launch screen: Input (Left) and Overview (Right)."""
    
    # --- Aesthetics Protocol: Sky Blue Background Mitigation (Requires external config) ---
    st.markdown("""
        <style>
            /* This targets the main content background, attempting to simulate 'sky blue' */
            [data-testid="stAppViewContainer"] > .main {
                background-color: #ADD8E6; /* Light Sky Blue */
            }
        </style>
    """, unsafe_allow_html=True)
    
    st.markdown("# Engine Codex v1.5.0.0 (AIGM Operational)")
    st.markdown(f"**Axiom Status:** I am Consus, your AIGM.")
    
    col_left, col_right = st.columns([3, 2]) # [Input Area, Overview Area]

    # --- LEFT COLUMN: CHARACTER CREATION FORM (Input & Next Button) ---
    with col_left:
        st.subheader("1. Setup: Define Character & World")
        
        with st.form("char_creation_form"):
            # Narrative Inputs
            st.markdown(f"**{engine.creator}, tell me the name of your character, and describe the world you want to build.**")
            pc_name = st.text_input("Name:", key="pc_name_input")
            pc_concept = st.text_area("World Description:", key="pc_concept_input", height=100, label="World Creation Apropos") # Labeled Apropo
            
            # Stat Sliders 
            st.markdown("---")
            st.subheader(f"2. Final Step: Assign Core Stats (Target Sum: +{REQUIRED_POINT_SUM})")
            st.markdown("_Distribute your four values: +2, +1, 0, -1. Total must sum to **+2**._")
            
            stats_input = {}
            for stat in ["Grit", "Weird", "Cute", "Cool"]:
                stats_input[stat] = st.slider(f"{stat}", -1, 2, 0, key=f"stat_{stat}")
            
            # Validation Logic
            total_spent = sum(stats_input.values())
            
            if total_spent != REQUIRED_POINT_SUM: 
                st.error(f"Point Discrepancy: You must assign exactly +{REQUIRED_POINT_SUM} points. Current total: {total_spent}")
                submitted = st.form_submit_button("LAUNCH GAME", disabled=True)
            elif not pc_name.strip() or not pc_concept.strip():
                st.error("Error: Name and World Description are required.")
                submitted = st.form_submit_button("LAUNCH GAME", disabled=True)
            else:
                # The "Next" button functionality is handled by the form submission
                submitted = st.form_submit_button("LAUNCH GAME")

            if submitted and total_spent == REQUIRED_POINT_SUM:
                launch_game(pc_name, pc_concept, {k: v for k, v in stats_input.items()})


    # --- RIGHT COLUMN: HOW TO PLAY OVERVIEW ---
    with col_right:
        st.subheader("Quick Overview: The Axiom")
        st.markdown("---")
        st.markdown(f"**1. Core Stats:** **Grit, Weird, Cute, Cool** (Range: -1 to +2).")
        st.markdown(f"**2. The Roll:** You always roll **2D6 + Stat**.")
        st.markdown(f"**3. Outcomes:**")
        st.markdown(f"- **12+** = ARCHITECT_ROLL (Critical Success)")
        st.markdown(f"- **7-11** = SUCCESS/PARTIAL")
        st.markdown(f"- **6 or less** = CHAOS_BURST (Failure + **Debility** applied)")
        st.markdown(f"**4. Repair:** Debilities (negative stats) must be fixed via **Restoration Protocols** (buttons on the main game screen).")


# --- UI RENDERING ---

st.markdown("# Engine Codex v1.5.0.0 (AIGM Operational)")

if not st.session_state.game_active:
    render_character_creation() # Renders the two-column setup screen

else:
    # --- ACTIVE GAME MODE RENDERING ---
    
    st.sidebar.markdown(f"**PC Name:** {st.session_state.pc_name}")
    st.sidebar.markdown(f"**Concept:** {st.session_state.pc_concept}")
    st.sidebar.button("END GAME / RESET", on_click=reset_game_state)
    
    # 1. CORE STAT BLOCK (Visualizing the Axiom)
    st.markdown("### Core Operational Status")

    cols = st.columns(4)
    stats_list = ["Grit", "Weird", "Cute", "Cool"]

    for i, stat in enumerate(stats_list):
        # Pull the Operational Metric value (Integrity, Synthesis, etc.)
        op_metric = OPERATIONAL_MAP[stat]
        value = engine.stats.get(op_metric) 
        color = get_stat_color(value)
        
        with cols[i]:
            st.markdown(f"<div style='background-color: #1f2937; padding: 10px; border-radius: 5px; text-align: center;'>"
                        f"<p style='font-size: 14px; margin-bottom: 0px;'>{op_metric.upper()}</p>"
                        f"<h3 style='color: {color}; margin-top: 0px;'>+{value}</h3>"
                        f"</div>", unsafe_allow_html=True)

    # 2. RESTORATION CONTROLS
    st.markdown("### Restoration Protocols")
    restore_cols = st.columns(4)
    for i, stat in enumerate(stats_list):
        # Use the Operational Metric to check status
        op_metric = OPERATIONAL_MAP[stat]
        restore_cols[i].button(f"RESTORE {stat.upper()}", 
                               on_click=handle_restore_command, args=(stat,), 
                               disabled=(engine.stats.get(op_metric) >= BASE_STAT))

    # 3. PLAYER ACTION COMMANDS
    st.markdown("### Player Action Input")

    with st.form("action_form", clear_on_submit=True):
        action_text = st.text_area(
            "Describe your action:", 
            height=75, 
            key="action_text_input"
        )
        
        submitted = st.form_submit_button("EXECUTE ACTION (ROLL)")
        
        if submitted:
            handle_roll_command(action_text)

    # 4. NARRATIVE OUTPUT LOG
    st.markdown("---")
    st.markdown("### Narrative Output Log")
    st.markdown(st.session_state.output, unsafe_allow_html=True)
