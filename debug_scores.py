import requests

BASE = "http://localhost:7860"
print("=== DEBUGGING SCORES ===")
# Reset
r = requests.post(f"{BASE}/reset", params={"scenario_id": 1}, timeout=5)
obs = r.json()
print("Reset observation:")
print("  scenario_name:", obs.get("scenario_name"))
print("  current_phase:", obs.get("current_phase"))
print("  previous_phase_score:", obs.get("previous_phase_score"))
print("  cumulative_score:", obs.get("cumulative_score"))

# Step 1: Identify
print("\n--- STEP 1: IDENTIFY ---")
action1 = {
    "action_type": "identify",
    "changed_fields": ["optional_fields"],
    "change_category": "field_added",
    "reason": "Adding optional field is backwards compatible",
}
r = requests.post(f"{BASE}/step", json={"action": action1}, timeout=5)
obs = r.json()
print("Response keys:", list(obs.keys()))
print("Identify observation:")
print("  previous_phase_score:", obs.get("previous_phase_score"))
print("  cumulative_score:", obs.get("cumulative_score"))
print("  current_phase:", obs.get("current_phase"))
print("  reward:", r.json().get("reward"))  # This should be the step reward
print("  done:", r.json().get("done"))

# Check if we need to look at observation vs reward differently
print("\nFull response:")
import json

print(json.dumps(r.json(), indent=2)[:500])  # First 500 chars
