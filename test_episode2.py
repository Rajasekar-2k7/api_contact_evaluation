import requests

BASE = "http://localhost:7860"
print("Testing full episode...")
# Reset
r = requests.post(f"{BASE}/reset", params={"scenario_id": 1}, timeout=5)
data = r.json()
obs = data.get("observation", data)
print(
    "Reset: {} - Phase: {}".format(obs.get("scenario_name"), obs.get("current_phase"))
)

# Step 1: Identify
action1 = {
    "action_type": "identify",
    "changed_fields": ["optional_fields"],
    "change_category": "field_added",
    "reason": "Adding optional field is backwards compatible",
}
r = requests.post(f"{BASE}/step", json={"action": action1}, timeout=5)
data = r.json()
obs = data.get("observation", data)
print(
    "Identify: Score={}, Next phase={}".format(
        obs.get("previous_phase_score"), obs.get("current_phase")
    )
)

# Step 2: Classify
action2 = {
    "action_type": "classify",
    "is_breaking": False,
    "affected_clients": [],
    "severity": 0.0,
    "confidence": 0.9,
    "reason": "No clients affected since optional field",
}
r = requests.post(f"{BASE}/step", json={"action": action2}, timeout=5)
data = r.json()
obs = data.get("observation", data)
print(
    "Classify: Score={}, Next phase={}".format(
        obs.get("previous_phase_score"), obs.get("current_phase")
    )
)

# Step 3: Migrate
action3 = {
    "action_type": "migrate",
    "migration_steps": ["No migration needed"],
    "migration_timeline_days": 0,
    "migration_risks": ["None"],
    "rollback_plan": "Not needed",
    "backwards_compatible_alternative": "Already compatible",
}
r = requests.post(f"{BASE}/step", json={"action": action3}, timeout=5)
data = r.json()
obs = data.get("observation", data)
print(
    "Migrate: Score={}, Final reward={}, Done={}".format(
        obs.get("previous_phase_score"), data.get("reward"), data.get("done")
    )
)
print("Full episode test completed successfully!")
