"""
Comprehensive manual test script for the API Contract Evolution environment.
Tests ALL endpoints, ALL 6 scenarios, inference.py structured output format,
edge cases, and validates the complete contract.

Usage:
    python tests/manual_test_all.py
"""

import requests
import json
import sys
import re
import subprocess
import os

# Ensure project root is on sys.path so server.* imports work
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

BASE_URL = "http://127.0.0.1:7860"
PASS = 0
FAIL = 0
WARN = 0


def test(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} — {detail}")


def warn(name, detail=""):
    global WARN
    WARN += 1
    print(f"  [WARN] {name} — {detail}")


# ═══════════════════════════════════════════════════════════════════════
# PHASE 1: Health & Info Endpoints
# ═══════════════════════════════════════════════════════════════════════
print("\n" + "="*70)
print("PHASE 1: Health & Info Endpoints")
print("="*70)

# 1.1 GET /health
r = requests.get(f"{BASE_URL}/health")
test("/health returns 200", r.status_code == 200, f"got {r.status_code}")
data = r.json()
test("/health has 'status: ok'", data.get("status") == "ok", f"got {data.get('status')}")
test("/health has environment name", "environment" in data, str(data))
test("/health has version", "version" in data, str(data))
test("/health has scenarios_available", data.get("scenarios_available") == 6, f"got {data.get('scenarios_available')}")

# 1.2 GET /scenarios
r = requests.get(f"{BASE_URL}/scenarios")
test("/scenarios returns 200", r.status_code == 200, f"got {r.status_code}")
data = r.json()
test("/scenarios has total=6", data.get("total") == 6, f"got {data.get('total')}")
scenarios = data.get("scenarios", [])
test("/scenarios lists all 6", len(scenarios) == 6, f"got {len(scenarios)}")
for s in scenarios:
    test(f"  Scenario {s['id']} has name+domain+difficulty",
         all(k in s for k in ["name", "domain", "difficulty"]),
         f"missing keys in {s}")

# 1.3 GET /state (before any reset)
r = requests.get(f"{BASE_URL}/state")
test("/state returns 200", r.status_code == 200, f"got {r.status_code}")

# 1.4 GET /replay
r = requests.get(f"{BASE_URL}/replay")
test("/replay returns 200", r.status_code == 200, f"got {r.status_code}")

# ═══════════════════════════════════════════════════════════════════════
# PHASE 2: Full 3-Phase Episode for ALL 6 Scenarios
# ═══════════════════════════════════════════════════════════════════════
print("\n" + "="*70)
print("PHASE 2: Full Episode Tests (All 6 Scenarios)")
print("="*70)

# Predefined correct-ish actions for each scenario
SCENARIO_ACTIONS = {
    1: {
        "p1": {"action_type": "identify", "changed_fields": ["optional_fields"], "change_category": "field_added", "reason": "optional field added, backwards compatible"},
        "p2": {"action_type": "classify", "is_breaking": False, "affected_clients": [], "severity": 0.0, "confidence": 0.9, "reason": "adding optional field is non-breaking"},
        "p3": {"action_type": "migrate", "migration_steps": ["No migration needed - optional non-breaking addition", "Add monitoring for new field usage"], "migration_timeline_days": 14, "migration_risks": ["none"], "rollback_plan": "Simply revert to not sending the optional field", "backwards_compatible_alternative": "This change is already backwards compatible and optional"},
    },
    2: {
        "p1": {"action_type": "identify", "changed_fields": ["error_codes"], "change_category": "error_code_changed", "reason": "insufficient_funds renamed to payment_declined, hardcoded strings break"},
        "p2": {"action_type": "classify", "is_breaking": True, "affected_clients": ["mobile_app", "partner_api"], "severity": 0.8, "confidence": 0.85, "reason": "mobile_app and partner_api hardcode insufficient_funds string"},
        "p3": {"action_type": "migrate", "migration_steps": ["Deploy v2 in parallel with v1", "Canary gradual rollout to 1% traffic", "Notify partner with 90 day notice", "Support both error codes during transition", "Monitor error rates"], "migration_timeline_days": 60, "migration_risks": ["Mobile 90-day update cycle", "Partner SLA requires notice"], "rollback_plan": "Immediately revert API routing back to v1 handler, rollback feature flag", "backwards_compatible_alternative": "Run v1 and v2 in parallel permanently, support both error code strings during transition with versioned endpoints"},
    },
    3: {
        "p1": {"action_type": "identify", "changed_fields": ["amount", "amount_unit"], "change_category": "behavior_changed", "reason": "cents to dollars transformation, all clients divide by 100"},
        "p2": {"action_type": "classify", "is_breaking": True, "affected_clients": ["mobile_app", "web_dashboard", "partner_api"], "severity": 1.0, "confidence": 0.95, "reason": "all clients built around buggy cents behavior"},
        "p3": {"action_type": "migrate", "migration_steps": ["Deploy v2 in parallel with v1", "Migrate clients first before deprecating", "Canary gradual rollout with feature flag", "Update mobile first", "Send partner notice for db migration", "Observability and monitoring on both versions"], "migration_timeline_days": 45, "migration_risks": ["Mobile 90-day update cycle", "Partner DB stores raw values", "Reporting service downstream impact"], "rollback_plan": "Revert API gateway routing to v1, disable v2 feature flag, rollback db migration scripts", "backwards_compatible_alternative": "Run v1 and v2 in parallel with versioned URL paths, add amount_unit field to v2 response to disambiguate"},
    },
    4: {
        "p1": {"action_type": "identify", "changed_fields": ["token_format", "validation_method"], "change_category": "type_changed", "reason": "Token changed from opaque string to JWT, validate endpoint removed, clients that parse token position or call validate endpoint break"},
        "p2": {"action_type": "classify", "is_breaking": True, "affected_clients": ["web_dashboard", "partner_api"], "severity": 0.7, "confidence": 0.85, "reason": "web_dashboard extracts user_id from token position 0-8, partner_api calls /v1/auth/validate which is removed"},
        "p3": {"action_type": "migrate", "migration_steps": ["Deploy v2 versioned endpoint in parallel", "Provide feature flag toggle for JWT vs opaque", "Canary rollout to 1% then gradual increase", "Migrate validation logic first", "Monitor error rates and latency"], "migration_timeline_days": 60, "migration_risks": ["JWT is structurally different format", "Validate endpoint removal breaks partner", "Token size increase may hit header limits"], "rollback_plan": "Revert to v1 opaque tokens, re-enable validate endpoint, rollback feature flag", "backwards_compatible_alternative": "Run v1 and v2 auth endpoints in parallel with versioned URLs, add JWT claims to carry equivalent positional data"},
    },
    5: {
        "p1": {"action_type": "identify", "changed_fields": ["rate_limiting.strategy"], "change_category": "behavior_changed", "reason": "per_ip changed to per_user, shared proxy/CDN anonymous traffic will hit limits catastrophically"},
        "p2": {"action_type": "classify", "is_breaking": True, "affected_clients": ["cdn_proxy"], "severity": 0.9, "confidence": 0.9, "reason": "cdn_proxy routes all anonymous traffic as shared user, 50k users share 1 rate limit"},
        "p3": {"action_type": "migrate", "migration_steps": ["Deploy v2 in parallel", "Inject user_id header for CDN configuration", "Exempt service accounts from per-user limits", "Canary with shadow traffic on CDN endpoints", "Gradual rollout monitoring anonymous traffic", "Monitor 429 error rates per client type"], "migration_timeline_days": 45, "migration_risks": ["CDN vendor strips auth headers", "Anonymous traffic unidentifiable", "99.96% CDN traffic could fail"], "rollback_plan": "Immediately revert rate limiting to per_ip strategy, rollback feature flag, restore CDN routing", "backwards_compatible_alternative": "Run v1 per-IP and v2 per-user in parallel, allow CDN to opt-in to per-user with special API key header"},
    },
    6: {
        "p1": {"action_type": "identify", "changed_fields": ["schema.price"], "change_category": "type_changed", "reason": "GraphQL price field changed from Float! (non-null) to Float (nullable), strongly-typed clients crash on null"},
        "p2": {"action_type": "classify", "is_breaking": True, "affected_clients": ["web_frontend_ts", "ios_app_swift"], "severity": 0.8, "confidence": 0.9, "reason": "TypeScript crashes on toFixed(null), Swift decoder fails on null Double"},
        "p3": {"action_type": "migrate", "migration_steps": ["Deploy schema versioning v1 and v2", "Update apps first with null check fallback handling", "Feature flag for nullable price rollout", "Canary deploy to small set", "Monitoring for null price errors", "Optional field migration with default values"], "migration_timeline_days": 45, "migration_risks": ["iOS 60-day App Store review cycle", "TypeScript needs interface update", "Discontinued products return null"], "rollback_plan": "Revert GraphQL schema to Float! non-null, rollback schema versioning, restore default price values", "backwards_compatible_alternative": "Keep Float! in v1 schema, return 0.0 instead of null for discontinued products, run v1 and v2 schemas in parallel"},
    },
}

for scenario_id in range(1, 7):
    print(f"\n--- Scenario {scenario_id} ---")
    actions = SCENARIO_ACTIONS[scenario_id]

    # Step 1: Reset
    r = requests.post(f"{BASE_URL}/reset", params={"scenario_id": scenario_id})
    test(f"S{scenario_id} /reset returns 200", r.status_code == 200, f"got {r.status_code}")
    obs = r.json()
    test(f"S{scenario_id} has scenario_id", obs.get("scenario_id") == scenario_id, f"got {obs.get('scenario_id')}")
    test(f"S{scenario_id} has scenario_name", len(obs.get("scenario_name", "")) > 0, "missing name")
    test(f"S{scenario_id} current_phase=identify", obs.get("current_phase") == "identify", f"got {obs.get('current_phase')}")
    test(f"S{scenario_id} done=False after reset", obs.get("done") == False, f"got {obs.get('done')}")
    test(f"S{scenario_id} has spec_v1", len(obs.get("spec_v1", {})) > 0, "missing spec_v1")
    test(f"S{scenario_id} has spec_v2", len(obs.get("spec_v2", {})) > 0, "missing spec_v2")
    test(f"S{scenario_id} has client_code", len(obs.get("client_code", {})) > 0, "missing client_code")
    test(f"S{scenario_id} has 3 phases remaining", len(obs.get("phases_remaining", [])) == 3, f"got {obs.get('phases_remaining')}")

    # Step 2: Phase 1 (Identify)
    r = requests.post(f"{BASE_URL}/step", json=actions["p1"])
    test(f"S{scenario_id} P1 /step returns 200", r.status_code == 200, f"got {r.status_code}")
    obs = r.json()
    p1_score = obs.get("previous_phase_score", -1)
    test(f"S{scenario_id} P1 score strictly in (0,1)", 0.0 < p1_score < 1.0, f"got {p1_score} — must be strictly (0,1), never 0.0 or 1.0")
    test(f"S{scenario_id} P1 current_phase=classify", obs.get("current_phase") == "classify", f"got {obs.get('current_phase')}")
    test(f"S{scenario_id} P1 done=False", obs.get("done") == False, f"got {obs.get('done')}")
    test(f"S{scenario_id} P1 has feedback", len(obs.get("previous_phase_feedback", "")) > 0, "no feedback")
    print(f"      Phase 1 score: {p1_score:.4f}")

    # Step 3: Phase 2 (Classify)
    r = requests.post(f"{BASE_URL}/step", json=actions["p2"])
    test(f"S{scenario_id} P2 /step returns 200", r.status_code == 200, f"got {r.status_code}")
    obs = r.json()
    p2_score = obs.get("previous_phase_score", -1)
    test(f"S{scenario_id} P2 score strictly in (0,1)", 0.0 < p2_score < 1.0, f"got {p2_score} — must be strictly (0,1), never 0.0 or 1.0")
    test(f"S{scenario_id} P2 current_phase=migrate", obs.get("current_phase") == "migrate", f"got {obs.get('current_phase')}")
    test(f"S{scenario_id} P2 done=False", obs.get("done") == False, f"got {obs.get('done')}")
    print(f"      Phase 2 score: {p2_score:.4f}")

    # Step 4: Phase 3 (Migrate)
    r = requests.post(f"{BASE_URL}/step", json=actions["p3"])
    test(f"S{scenario_id} P3 /step returns 200", r.status_code == 200, f"got {r.status_code}")
    obs = r.json()
    p3_score = obs.get("previous_phase_score", -1)
    final_score = obs.get("reward", -1)
    test(f"S{scenario_id} P3 score strictly in (0,1)", 0.0 < p3_score < 1.0, f"got {p3_score} — must be strictly (0,1), never 0.0 or 1.0")
    test(f"S{scenario_id} P3 done=True", obs.get("done") == True, f"got {obs.get('done')}")
    test(f"S{scenario_id} final reward strictly in (0,1)", 0.0 < final_score < 1.0, f"got {final_score} — must be strictly (0,1), never 0.0 or 1.0")
    test(f"S{scenario_id} P3 current_phase=done", obs.get("current_phase") == "done", f"got {obs.get('current_phase')}")
    test(f"S{scenario_id} cumulative_score strictly in (0,1)", 0.0 < obs.get("cumulative_score", -1) < 1.0, f"got {obs.get('cumulative_score')} — must be strictly (0,1)")
    print(f"      Phase 3 score: {p3_score:.4f}")
    print(f"      Final reward:  {final_score:.4f}")

    # Step 5: Check /state after done
    r = requests.get(f"{BASE_URL}/state")
    state = r.json()
    test(f"S{scenario_id} /state is_done=True", state.get("is_done") == True, f"got {state.get('is_done')}")
    test(f"S{scenario_id} /state step_count=3", state.get("step_count") == 3, f"got {state.get('step_count')}")

    # Step 6: Check /replay after done
    r = requests.get(f"{BASE_URL}/replay")
    replay = r.json()
    test(f"S{scenario_id} /replay has 3 actions", len(replay.get("action_history", [])) == 3, f"got {len(replay.get('action_history', []))}")
    test(f"S{scenario_id} /replay is_done=True", replay.get("is_done") == True, f"got {replay.get('is_done')}")

    # Step 7: Stepping after done should return harmlessly
    r = requests.post(f"{BASE_URL}/step", json=actions["p1"])
    test(f"S{scenario_id} step-after-done returns 200", r.status_code == 200, f"got {r.status_code}")
    obs = r.json()
    test(f"S{scenario_id} step-after-done done=True", obs.get("done") == True, f"got {obs.get('done')}")


# ═══════════════════════════════════════════════════════════════════════
# PHASE 3: Edge Cases & Error Handling
# ═══════════════════════════════════════════════════════════════════════
print("\n" + "="*70)
print("PHASE 3: Edge Cases & Error Handling")
print("="*70)

# 3.1 Invalid scenario_id defaults to 1
r = requests.post(f"{BASE_URL}/reset", params={"scenario_id": 999})
test("Invalid scenario_id=999 defaults to 1", r.json().get("scenario_id") == 1, f"got {r.json().get('scenario_id')}")

# 3.2 scenario_id=0 defaults to 1
r = requests.post(f"{BASE_URL}/reset", params={"scenario_id": 0})
test("scenario_id=0 defaults to 1", r.json().get("scenario_id") == 1, f"got {r.json().get('scenario_id')}")

# 3.3 Reset with no param defaults to 1
r = requests.post(f"{BASE_URL}/reset")
test("/reset with no param defaults to scenario 1", r.json().get("scenario_id") == 1, f"got {r.json().get('scenario_id')}")

# 3.4 Minimal action body (empty fields should use defaults)
r = requests.post(f"{BASE_URL}/reset", params={"scenario_id": 1})
r = requests.post(f"{BASE_URL}/step", json={"action_type": "identify"})
test("Minimal action body accepted", r.status_code == 200, f"got {r.status_code}")
test("Minimal action still scores", 0.0 <= r.json().get("previous_phase_score", -1) <= 1.0, f"got {r.json()}")


# ═══════════════════════════════════════════════════════════════════════
# PHASE 4: Inference.py Structured Output Verification
# ═══════════════════════════════════════════════════════════════════════
print("\n" + "="*70)
print("PHASE 4: Inference.py Structured Output Format Check")
print("="*70)

# Read inference.py and check for the required patterns
inference_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "inference.py")
with open(inference_path, "r") as f:
    inference_code = f.read()

# Check emit functions exist
test("emit_start() function defined", "def emit_start(" in inference_code, "missing emit_start function")
test("emit_step() function defined", "def emit_step(" in inference_code, "missing emit_step function")
test("emit_end() function defined", "def emit_end(" in inference_code, "missing emit_end function")

# Check format strings
test("[START] format correct", '[START] task=' in inference_code, "missing [START] tag format")
test("[STEP] format correct", '[STEP] step=' in inference_code, "missing [STEP] tag format")
test("[END] format correct", '[END] task=' in inference_code, "missing [END] tag format")

# Check flush=True in emit functions
test("emit_start uses flush=True", 'flush=True' in inference_code, "missing flush=True")

# Check sys.stdout.reconfigure guard
test("stdout buffering guard exists", 'sys.stdout.reconfigure' in inference_code, "missing stdout reconfigure")

# Check emit calls in run_scenario
test("emit_start called in run_scenario", 'emit_start(task_name)' in inference_code, "emit_start not called")
test("emit_step called after phase step", 'emit_step(step_count,' in inference_code, "emit_step not called")
test("emit_end called at episode end", 'emit_end(task_name,' in inference_code, "emit_end not called")

# Check error path also emits structured output
test("Error path emits START", inference_code.count('emit_start(') >= 2, "error path missing emit_start")
test("Error path emits END", inference_code.count('emit_end(') >= 2, "error path missing emit_end")

# Simulate what validator sees — parse emit patterns
start_pattern = re.compile(r'\[START\] task=\w+')
step_pattern = re.compile(r'\[STEP\] step=\d+ reward=[\d.]+')
end_pattern = re.compile(r'\[END\] task=\w+ score=[\d.]+ steps=\d+')

# Generate sample output lines to test parsing
test_lines = [
    "[START] task=scenario_1",
    "[STEP] step=1 reward=0.8500",
    "[STEP] step=2 reward=0.7200",
    "[STEP] step=3 reward=0.9000",
    "[END] task=scenario_1 score=0.9000 steps=3",
]

for line in test_lines:
    if "[START]" in line:
        test(f"Validator parses '{line}'", start_pattern.match(line) is not None, "parse failed")
    elif "[STEP]" in line:
        test(f"Validator parses '{line}'", step_pattern.match(line) is not None, "parse failed")
    elif "[END]" in line:
        test(f"Validator parses '{line}'", end_pattern.match(line) is not None, "parse failed")


# ═══════════════════════════════════════════════════════════════════════
# PHASE 5: Score Quality Checks
# ═══════════════════════════════════════════════════════════════════════
print("\n" + "="*70)
print("PHASE 5: Score Quality / Discrimination Checks")
print("="*70)

from server.graders import grade_phase_1_identify, grade_phase_2_classify, grade_phase_3_migrate, compute_episode_score
from server.scenarios import SCENARIOS

# For each scenario, run through perfect action, compute score
for sid in range(1, 7):
    gt = SCENARIOS[sid]["ground_truth"]
    actions = SCENARIO_ACTIONS[sid]
    
    p1 = grade_phase_1_identify(actions["p1"], gt)
    p2 = grade_phase_2_classify(actions["p2"], gt)
    p3 = grade_phase_3_migrate(actions["p3"], gt)
    
    ep = compute_episode_score({"identify": p1["score"], "classify": p2["score"], "migrate": p3["score"]})
    
    # Strict (0, 1) bounds — validator rejects exactly 0.0 and 1.0
    test(f"S{sid} P1 score strictly in (0,1)", 0.0 < p1["score"] < 1.0, f"got {p1['score']}")
    test(f"S{sid} P2 score strictly in (0,1)", 0.0 < p2["score"] < 1.0, f"got {p2['score']}")
    test(f"S{sid} P3 score strictly in (0,1)", 0.0 < p3["score"] < 1.0, f"got {p3['score']}")
    test(f"S{sid} episode strictly in (0,1)", 0.0 < ep < 1.0, f"got {ep}")
    test(f"S{sid} correct answer scores > 0.5", ep > 0.5, f"got {ep:.4f} (P1={p1['score']:.4f} P2={p2['score']:.4f} P3={p3['score']:.4f})")
    
    # Test that a completely wrong answer scores < correct
    wrong = {
        "changed_fields": ["nonexistent_field"],
        "change_category": "field_removed",
        "is_breaking": not gt.get("is_breaking", False),
        "affected_clients": ["fake_client"],
        "severity": 0.0 if gt.get("severity", 0.5) > 0.5 else 1.0,
        "confidence": 0.99,
        "reason": "completely wrong",
        "migration_steps": ["just deploy"],
        "migration_risks": [],
        "rollback_plan": "no plan",
        "backwards_compatible_alternative": "",
        "migration_timeline_days": 1,
    }
    
    wp1 = grade_phase_1_identify(wrong, gt)
    wp2 = grade_phase_2_classify(wrong, gt)
    wp3 = grade_phase_3_migrate(wrong, gt)
    wrong_ep = compute_episode_score({"identify": wp1["score"], "classify": wp2["score"], "migrate": wp3["score"]})
    
    test(f"S{sid} correct ({ep:.3f}) > wrong ({wrong_ep:.3f})", ep > wrong_ep,
         f"DISCRIMINATION FAIL: correct={ep:.4f} wrong={wrong_ep:.4f}")


# ═══════════════════════════════════════════════════════════════════════
# PHASE 6: OpenEnv Compliance Checks
# ═══════════════════════════════════════════════════════════════════════
print("\n" + "="*70)
print("PHASE 6: OpenEnv & Submission Compliance")
print("="*70)

# Check required files exist
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
required_files = [
    "inference.py",
    "openenv.yaml",
    "pyproject.toml",
    "Dockerfile",
    "README.md",
    "models.py",
    "server/app.py",
    "server/graders.py",
    "server/scenarios.py",
    "server/api_contract_evolution_environment.py",
]

for f in required_files:
    path = os.path.join(project_root, f)
    test(f"File exists: {f}", os.path.exists(path), f"MISSING: {path}")

# Check openenv.yaml content (parse manually to avoid PyYAML dependency)
with open(os.path.join(project_root, "openenv.yaml"), "r") as f:
    oe_text = f.read()
test("openenv.yaml has spec_version: 1", "spec_version: 1" in oe_text, "missing spec_version")
test("openenv.yaml has name: api_contract_evolution", "name: api_contract_evolution" in oe_text, "wrong name")
test("openenv.yaml has app entry point", "app:" in oe_text, "missing app")
test("openenv.yaml has port: 7860", "port: 7860" in oe_text, "wrong port")

# Check pyproject.toml entry points
with open(os.path.join(project_root, "pyproject.toml"), "r") as f:
    toml_content = f.read()
test("pyproject.toml has server entry point", 'server = "server.app:main"' in toml_content, "missing server entry point")
test("pyproject.toml has openenv-core dependency", "openenv-core" in toml_content, "missing openenv-core dependency")

# Check inference.py required elements
test("inference.py reads API_BASE_URL from env", 'os.getenv("API_BASE_URL"' in inference_code or "os.getenv('API_BASE_URL'" in inference_code, "missing API_BASE_URL env var")
test("inference.py reads MODEL_NAME from env", 'os.getenv("MODEL_NAME"' in inference_code or "os.getenv('MODEL_NAME'" in inference_code, "missing MODEL_NAME env var")
test("inference.py reads HF_TOKEN from env", 'os.getenv("HF_TOKEN"' in inference_code or "os.getenv('HF_TOKEN'" in inference_code, "missing HF_TOKEN env var")
test("inference.py uses OpenAI client", "from openai import OpenAI" in inference_code, "must use OpenAI client per rules")
test("inference.py has main() function", "def main():" in inference_code, "missing main()")
test("inference.py has __main__ guard", '__name__ == "__main__"' in inference_code, "missing __main__ guard")


# ═══════════════════════════════════════════════════════════════════════
# FINAL REPORT
# ═══════════════════════════════════════════════════════════════════════
print("\n" + "="*70)
print("FINAL TEST REPORT")
print("="*70)
total = PASS + FAIL
print(f"\n  PASSED: {PASS}/{total}")
print(f"  FAILED: {FAIL}/{total}")
if WARN > 0:
    print(f"  WARNINGS: {WARN}")

if FAIL == 0:
    print("\n  [SUCCESS] ALL TESTS PASSED — READY TO SUBMIT!")
else:
    print(f"\n  [ERROR] {FAIL} TESTS FAILED — FIX BEFORE SUBMITTING")

print("="*70 + "\n")
sys.exit(1 if FAIL > 0 else 0)
