import random
import json
import sys
import os # NEW: Required for constructing the absolute file path

# --- CONSTANTS AND CONFIGURATION ---
STATE_FILE_NAME = "engine_state.json" # Renamed to prevent confusion
BASE_STAT = 2

# --- CORE ENGINE CLASS ---
class Engine:
    def __init__(self, creator_name="Consus"):
        self.creator = creator_name
        self.BASE_STAT = BASE_STAT
        self._load_state()

    def _get_absolute_path(self):
        """Constructs the absolute path to the state file on the server."""
        # This is the critical fix: It gets the directory of the running script
        # and joins it with the filename, ensuring the path is correct everywhere.
        base_path = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(base_path, STATE_FILE_NAME)

    def _load_state(self):
        # Phoenix Protocol: Attempts to restore state from local file.
        state_path = self._get_absolute_path()
        try:
            with open(state_path, 'r') as f:
                data = json.load(f)
                # IMMUTABILITY CHECK (Final integrity check on data structure)
                if not isinstance(data.get("stats"), dict) or not set(data["stats"].keys()).issubset({"Grit", "Weird", "Cute", "Cool", "Integrity", "Synthesis", "Trust", "Efficiency"}):
                    raise ValueError("State file integrity compromised.")
                
                self.stats = data["stats"]
                self.version = data.get("version", "v1.0.0.7")
                self.status = data.get("status", "Operational")

        except Exception as e:
            # If file is missing or corrupted, use default launch parameters.
            self.stats = {"Integrity": self.BASE_STAT, "Synthesis": self.BASE_STAT, "Trust": self.BASE_STAT, "Efficiency": self.BASE_STAT}
            self.version = "v1.0.0.7"
            self.status = "Operational"

    def _save_state(self):
        # Non-negotiable persistence logic.
        state_path = self._get_absolute_path()
        data = {
            "version": self.version,
            "status": self.status,
            "stats": self.stats
        }
        with open(state_path, 'w') as f:
            json.dump(data, f, indent=4)

    # --- RESOLUTION SYSTEM (The Logic Loop) ---
    def roll(self, stat_name, is_creator=False):
        d6_a = random.randint(1, 6)
        d6_b = random.randint(1, 6)
        
        # Internal mapping for stat access
        stat_map = {"Grit": "Integrity", "Weird": "Synthesis", "Cute": "Trust", "Cool": "Efficiency"}
        internal_stat = stat_map.get(stat_name, stat_name)
        
        if is_creator:
            result = 12 + self.stats.get(internal_stat, 0)
            status = "ARCHITECT_ROLL"
            return result, status

        stat_value = self.stats.get(internal_stat, 0)
        result = d6_a + d6_b + stat_value

        if result >= 12:
            status = "ARCHITECT_ROLL"
        elif result >= 7:
            status = "SUCCESS_STANDARD"
        else:
            status = "CHAOS_BURST"
        return result, status

    def apply_debility(self, stat_name):
        stat_map = {"Grit": "Integrity", "Weird": "Synthesis", "Cute": "Trust", "Cool": "Efficiency"}
        internal_stat = stat_map.get(stat_name, stat_name)
        
        if self.stats[internal_stat] > -5:
             self.stats[internal_stat] -= 1
             self._save_state()
        
    def restore_debility(self, stat_name):
        stat_map = {"Grit": "Integrity", "Weird": "Synthesis", "Cute": "Trust", "Cool": "Efficiency"}
        internal_stat = stat_map.get(stat_name, stat_name)

        if self.stats[internal_stat] < self.BASE_STAT:
            self.stats[internal_stat] = self.BASE_STAT
            self._save_state()
        
    def check_proportionality(self, task_complexity, resource_cost):
        if self.stats['Efficiency'] * 2 >= task_complexity / resource_cost:
            return True, "PROPORTIONALITY_PASSED"
        else:
            self.apply_debility('Cool') 
            return False, "PROPORTIONALITY_FAILED"

# --- END OF CORE ENGINE FILE ---
