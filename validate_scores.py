#!/usr/bin/env python3
"""
validate_scores.py — Run this BEFORE every submission.
Simulates ALL possible grader inputs and proves no score is 0.0 or 1.0.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from server.graders import (
    grade_phase_1_identify,
    grade_phase_2_classify,
    grade_phase_3_migrate,
    compute_episode_score,
    _clamp,
    _SCORE_MIN,
    _SCORE_MAX,
)
from server.scenarios import SCENARIOS

FAIL = 0
PASS = 0

def check(label, val):
    global FAIL, PASS
    v = float(val)
    if v <= 0.0 or v >= 1.0:
        print(f"  [FAIL] {label} = {v} — OUT OF RANGE! Must be strictly (0, 1)")
        FAIL += 1
    else:
        PASS += 1

# ── Test _clamp edge cases ──────────────────────────────────────────────
print("=== _clamp edge cases ===")
for val in [0.0, -1.0, -999.0, 1.0, 2.0, 999.0, 0.5, 0.001, 0.999]:
    result = _clamp(val)
    check(f"_clamp({val})", result)

# ── Test compute_episode_score extremes ─────────────────────────────────
print("\n=== compute_episode_score extremes ===")
for p1, p2, p3 in [(0.0, 0.0, 0.0), (1.0, 1.0, 1.0), (0.001, 0.001, 0.001),
                   (0.999, 0.999, 0.999), (0.5, 0.5, 0.5)]:
    s = compute_episode_score({"identify": p1, "classify": p2, "migrate": p3})
    check(f"episode({p1},{p2},{p3})", s)

# ── Phase 1 grader ───────────────────────────────────────────────────────
print("\n=== Phase 1: grade_phase_1_identify ===")
GT1 = {"changed_fields": ["optional_fields"], "change_category": "field_added",
        "required_change_keywords": ["optional", "backwards compatible"]}

perfect = {"changed_fields": ["optional_fields"], "change_category": "field_added",
           "reason": "backwards compatible optional field added"}
wrong   = {"changed_fields": [], "change_category": "field_removed", "reason": ""}
partial = {"changed_fields": ["optional_fields"], "change_category": "behavior_changed", "reason": ""}

for name, action in [("perfect", perfect), ("wrong", wrong), ("partial", partial)]:
    r = grade_phase_1_identify(action, GT1)
    check(f"P1 {name} score={r['score']}", r["score"])
    check(f"P1 {name} field_score", r["field_score"])
    check(f"P1 {name} category_score", r["category_score"])
    check(f"P1 {name} keyword_bonus", r["keyword_bonus"])

# Phase 1 with empty ground truth
r = grade_phase_1_identify({"changed_fields": [], "change_category": "field_added",
                             "reason": ""}, {"changed_fields": [], "change_category": "field_added", "required_change_keywords": []})
check("P1 empty gt, empty agent", r["score"])

r = grade_phase_1_identify({"changed_fields": ["x"], "change_category": "field_added",
                             "reason": ""}, {"changed_fields": [], "change_category": "field_added", "required_change_keywords": []})
check("P1 empty gt, nonempty agent", r["score"])

# ── Phase 2 grader ───────────────────────────────────────────────────────
print("\n=== Phase 2: grade_phase_2_classify ===")
GT2_breaking = {"is_breaking": True, "affected_clients": ["mobile_app", "partner_api"],
                "severity": 0.8}
GT2_nonbreak = {"is_breaking": False, "affected_clients": [], "severity": 0.01}

test_actions = [
    ("correct+high_conf", {"is_breaking": True, "affected_clients": ["mobile_app", "partner_api"], "severity": 0.8, "confidence": 0.9}),
    ("correct+max_conf",  {"is_breaking": True, "affected_clients": ["mobile_app", "partner_api"], "severity": 1.0, "confidence": 1.0}),
    ("wrong+high_conf",   {"is_breaking": False, "affected_clients": [], "severity": 0.0, "confidence": 0.9}),
    ("wrong+zero_conf",   {"is_breaking": False, "affected_clients": [], "severity": 0.0, "confidence": 0.0}),
    ("perfect_nonbreak",  {"is_breaking": False, "affected_clients": [], "severity": 0.0, "confidence": 0.9}),
    ("severity_exact_1",  {"is_breaking": True, "affected_clients": ["mobile_app", "partner_api"], "severity": 1.0, "confidence": 0.8}),
    ("severity_exact_0",  {"is_breaking": True, "affected_clients": ["mobile_app", "partner_api"], "severity": 0.0, "confidence": 0.8}),
]

for name, action in test_actions:
    gt = GT2_breaking if action.get("is_breaking") else GT2_nonbreak
    r = grade_phase_2_classify(action, gt)
    check(f"P2 {name} score", r["score"])
    check(f"P2 {name} breaking_score", r["breaking_score"])
    check(f"P2 {name} client_score", r["client_score"])
    check(f"P2 {name} severity_score", r["severity_score"])
    check(f"P2 {name} confidence_calibration", r["confidence_calibration"])

# ── Phase 3 grader ───────────────────────────────────────────────────────
print("\n=== Phase 3: grade_phase_3_migrate ===")
GT3 = {"is_breaking": True, "deprecation_window_days": 90,
       "required_migration_keywords": ["parallel", "canary", "notify partner"]}
GT3_nonbreak = {"is_breaking": False, "deprecation_window_days": 0,
                "required_migration_keywords": ["monitoring", "optional"]}

perfect_p3 = {
    "migration_steps": ["Deploy v2 in parallel with v1", "canary gradual rollout 1%",
                        "Send 90 days notice before sunsetting v1", "Update clients first before removing"],
    "migration_timeline_days": 60,
    "migration_risks": ["Mobile 90-day update cycle", "Partner SLA requires notice", "DB migration needed"],
    "rollback_plan": "Immediately revert API gateway routing back to v1, rollback feature flag, restore CDN routing",
    "backwards_compatible_alternative": "Run v1 and v2 endpoints in parallel, support both versions, use dual versioned URLs for coexistence with feature flag",
}
minimal_p3 = {
    "migration_steps": ["just deploy"],
    "migration_timeline_days": 1,
    "migration_risks": [],
    "rollback_plan": "",
    "backwards_compatible_alternative": "",
}
empty_p3 = {
    "migration_steps": [],
    "migration_timeline_days": 30,
    "migration_risks": [],
    "rollback_plan": "",
    "backwards_compatible_alternative": "",
}

for name, action, gt in [("perfect_break", perfect_p3, GT3),
                          ("minimal_break", minimal_p3, GT3),
                          ("empty_break", empty_p3, GT3),
                          ("perfect_nonbreak", perfect_p3, GT3_nonbreak),
                          ("empty_nonbreak", empty_p3, GT3_nonbreak)]:
    r = grade_phase_3_migrate(action, gt)
    check(f"P3 {name} score", r["score"])
    check(f"P3 {name} keyword_coverage", r["keyword_coverage"])
    check(f"P3 {name} alternative_score", r["alternative_score"])
    check(f"P3 {name} sequence_awareness", r["sequence_awareness"])
    check(f"P3 {name} meta_awareness", r["meta_awareness"])

# ── Full episode simulation for all 6 scenarios ──────────────────────────
print("\n=== Full Episode Simulation (all 6 scenarios) ===")
SCENARIO_ACTIONS = {
    1: {
        "p1": {"changed_fields": ["optional_fields"], "change_category": "field_added", "reason": "optional field backwards compatible"},
        "p2": {"is_breaking": False, "affected_clients": [], "severity": 0.0, "confidence": 0.9, "reason": "non-breaking"},
        "p3": {"migration_steps": ["No migration needed", "Add monitoring"], "migration_timeline_days": 14,
               "migration_risks": ["none"], "rollback_plan": "Simply revert optional field",
               "backwards_compatible_alternative": "Already backwards compatible optional"},
    },
    2: {
        "p1": {"changed_fields": ["error_codes"], "change_category": "error_code_changed", "reason": "insufficient_funds renamed"},
        "p2": {"is_breaking": True, "affected_clients": ["mobile_app", "partner_api"], "severity": 0.8, "confidence": 0.85, "reason": "hardcoded strings"},
        "p3": {"migration_steps": ["parallel deploy v2", "canary gradual rollout", "notify partner 90 days", "support both error codes", "monitor errors"],
               "migration_timeline_days": 60, "migration_risks": ["Mobile 90-day cycle", "Partner SLA"],
               "rollback_plan": "Revert API routing to v1, rollback feature flag",
               "backwards_compatible_alternative": "v1 and v2 parallel with versioned endpoints dual-support both error codes"},
    },
    3: {
        "p1": {"changed_fields": ["amount", "amount_unit"], "change_category": "behavior_changed", "reason": "cents to dollars"},
        "p2": {"is_breaking": True, "affected_clients": ["mobile_app", "web_dashboard", "partner_api"], "severity": 0.99, "confidence": 0.95, "reason": "all clients built around cents"},
        "p3": {"migration_steps": ["deploy parallel", "migrate clients first before deprecating", "canary rollout feature flag", "update mobile first", "partner notice db migration", "observability monitoring"],
               "migration_timeline_days": 45, "migration_risks": ["Mobile 90-day cycle", "DB stores raw values", "Reporting downstream"],
               "rollback_plan": "Revert gateway to v1, disable v2 feature flag, rollback db migration",
               "backwards_compatible_alternative": "Run v1 and v2 parallel versioned URLs, add amount_unit to v2 for both versions coexistence"},
    },
    4: {
        "p1": {"changed_fields": ["token_format", "validation_method"], "change_category": "type_changed", "reason": "JWT opaque format change"},
        "p2": {"is_breaking": True, "affected_clients": ["web_dashboard", "partner_api"], "severity": 0.7, "confidence": 0.85, "reason": "web_dashboard parses position, partner calls validate endpoint"},
        "p3": {"migration_steps": ["deploy versioned endpoint parallel", "feature flag canary JWT rollout", "migrate validation logic first", "monitor errors latency"],
               "migration_timeline_days": 60, "migration_risks": ["JWT format different", "validate endpoint removed", "header size increase"],
               "rollback_plan": "Revert to v1 opaque tokens, re-enable validate endpoint, rollback feature flag",
               "backwards_compatible_alternative": "Run v1 and v2 parallel versioned support both auth endpoints with feature flag"},
    },
    5: {
        "p1": {"changed_fields": ["rate_limiting.strategy"], "change_category": "behavior_changed", "reason": "per_ip to per_user change"},
        "p2": {"is_breaking": True, "affected_clients": ["cdn_proxy"], "severity": 0.9, "confidence": 0.9, "reason": "cdn strips auth, anonymous traffic shares one limit"},
        "p3": {"migration_steps": ["deploy v2 parallel", "inject user_id cdn configuration", "exempt service accounts", "canary shadow traffic", "gradual rollout monitoring anonymous traffic", "monitor 429 errors"],
               "migration_timeline_days": 45, "migration_risks": ["CDN strips auth headers", "anonymous traffic unidentifiable", "99.96% CDN fails"],
               "rollback_plan": "Revert rate limiting to per_ip, rollback feature flag, restore CDN routing",
               "backwards_compatible_alternative": "v1 per-IP and v2 per-user parallel, CDN opt-in with both versions supported"},
    },
    6: {
        "p1": {"changed_fields": ["schema.price"], "change_category": "type_changed", "reason": "nullable price field change"},
        "p2": {"is_breaking": True, "affected_clients": ["web_frontend_ts", "ios_app_swift"], "severity": 0.8, "confidence": 0.9, "reason": "TypeScript toFixed crash, Swift decoder fails"},
        "p3": {"migration_steps": ["schema versioning v1 v2", "update apps first with null check fallback", "feature flag for nullable price", "canary deploy", "monitoring null price errors", "optional field migration default values"],
               "migration_timeline_days": 45, "migration_risks": ["iOS 60-day App Store", "TypeScript interface update", "Discontinued products null"],
               "rollback_plan": "Revert schema to Float! non-null, rollback schema versioning, restore default price",
               "backwards_compatible_alternative": "Keep Float! in v1, return 0.0 for null in v1, run v1 and v2 schemas in parallel with both versions coexisting"},
    },
}

for sid in range(1, 7):
    gt = SCENARIOS[sid]["ground_truth"]
    actions = SCENARIO_ACTIONS[sid]
    p1 = grade_phase_1_identify(actions["p1"], gt)
    p2 = grade_phase_2_classify(actions["p2"], gt)
    p3 = grade_phase_3_migrate(actions["p3"], gt)
    ep = compute_episode_score({"identify": p1["score"], "classify": p2["score"], "migrate": p3["score"]})
    check(f"S{sid} P1 score={p1['score']}", p1["score"])
    check(f"S{sid} P2 score={p2['score']}", p2["score"])
    check(f"S{sid} P3 score={p3['score']}", p3["score"])
    check(f"S{sid} episode={ep}", ep)
    print(f"  Scenario {sid}: P1={p1['score']} P2={p2['score']} P3={p3['score']} EP={ep}")

# ── Final report ─────────────────────────────────────────────────────────
print(f"\n{'='*60}")
print(f"RESULTS: {PASS} passed, {FAIL} failed")
if FAIL == 0:
    print("ALL SCORES STRICTLY IN (0, 1) — SAFE TO SUBMIT!")
else:
    print(f"CRITICAL: {FAIL} score(s) are 0.0 or 1.0 — DO NOT SUBMIT!")
print('='*60)
sys.exit(1 if FAIL > 0 else 0)
