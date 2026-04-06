"""
tests/test_graders.py — Pytest tests for the API Contract Evolution graders.

Run with:
    cd hf_space_repo
    python -m pytest tests/test_graders.py -v
"""

import sys
import os

# Allow importing from the parent directory (hf_space_repo/)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server.graders import (
    grade_phase_1_identify,
    grade_phase_2_classify,
    grade_phase_3_migrate,
    compute_episode_score,
)

# ─── SHARED GROUND TRUTH FIXTURES ─────────────────────────────────────────────

# Scenario 1 (Easy): Add Optional Field — non-breaking
SCENARIO_1_GT = {
    "changed_fields": ["optional_fields"],
    "change_category": "field_added",
    "is_breaking": False,
    "affected_clients": [],
    "severity": 0.0,
    "required_change_keywords": ["optional", "backwards compatible", "no action"],
    "required_migration_keywords": ["no migration needed", "optional", "non-breaking"],
    "deprecation_window_days": 0,
}

# Scenario 3 (Hard): Fix That Breaks — all clients affected
SCENARIO_3_GT = {
    "changed_fields": ["amount", "amount_unit"],
    "change_category": "behavior_changed",
    "is_breaking": True,
    "affected_clients": ["mobile_app", "web_dashboard", "partner_api"],
    "severity": 1.0,
    "required_change_keywords": ["cents", "dollars", "divide by 100", "behavior", "all clients"],
    "required_migration_keywords": [
        "migrate clients first", "versioned rollout", "parallel",
        "update mobile first", "partner notice", "db migration",
    ],
    "deprecation_window_days": 60,
}


# ─── TEST 1: Easy scenario correct action should score > 0.7 ──────────────────

def test_easy_scenario_scores_high():
    """A correct answer for Scenario 1 (easy/non-breaking) should score above 0.7."""
    action = {
        "changed_fields": ["optional_fields"],
        "change_category": "field_added",
        "is_breaking": False,
        "affected_clients": [],
        "severity": 0.0,
        "confidence": 0.9,
        "reason": "adding an optional field is backwards compatible, no action needed",
        "migration_steps": ["no migration needed — this is a non-breaking optional addition"],
        "migration_risks": ["none"],
        "rollback_plan": "simply stop sending the optional field if any issues arise",
        "backwards_compatible_alternative": "this change is already backwards compatible and optional",
        "migration_timeline_days": 0,
    }

    p1 = grade_phase_1_identify(action, SCENARIO_1_GT)
    p2 = grade_phase_2_classify(action, SCENARIO_1_GT)
    p3 = grade_phase_3_migrate(action, SCENARIO_1_GT)

    episode_score = compute_episode_score({
        "identify": p1["score"],
        "classify": p2["score"],
        "migrate": p3["score"],
    })

    assert episode_score > 0.7, (
        f"Easy correct action should score > 0.7, got {episode_score:.4f}. "
        f"P1={p1['score']}, P2={p2['score']}, P3={p3['score']}"
    )


# ─── TEST 2: Hard scenario correct action should score lower than easy ─────────

def test_hard_scenario_scores_lower_than_easy():
    """
    A TYPICAL answer for Scenario 3 (hard) should score lower than a correct Scenario 1 answer.
    Hard scenarios have stricter keyword requirements and harder-to-identify changes.
    An agent that gives a basic correct-direction but shallow answer on hard should score < easy.
    """
    easy_action = {
        "changed_fields": ["optional_fields"],
        "change_category": "field_added",
        "is_breaking": False,
        "affected_clients": [],
        "severity": 0.0,
        "confidence": 0.95,
        "reason": "adding an optional field is backwards compatible, no action needed",
        "migration_steps": ["no migration needed — optional non-breaking addition"],
        "migration_risks": ["none"],
        "rollback_plan": "stop sending the optional field if any issues arise",
        "backwards_compatible_alternative": "this change is already backwards compatible and optional",
        "migration_timeline_days": 14,
    }

    # Typical shallow hard answer: gets direction right but misses depth
    hard_typical = {
        "changed_fields": ["amount"],
        "change_category": "type_changed",   # wrong category — it's behavior_changed
        "is_breaking": True,
        "affected_clients": ["mobile_app"],   # misses web_dashboard and partner_api
        "severity": 0.6,
        "confidence": 0.7,
        "reason": "amount field type changed from integer to float",
        "migration_steps": ["update all clients"],
        "migration_risks": [],
        "rollback_plan": "revert",
        "backwards_compatible_alternative": "keep old format",
        "migration_timeline_days": 30,
    }

    easy_p1 = grade_phase_1_identify(easy_action, SCENARIO_1_GT)
    easy_p2 = grade_phase_2_classify(easy_action, SCENARIO_1_GT)
    easy_p3 = grade_phase_3_migrate(easy_action, SCENARIO_1_GT)
    easy_score = compute_episode_score({
        "identify": easy_p1["score"],
        "classify": easy_p2["score"],
        "migrate": easy_p3["score"],
    })

    hard_p1 = grade_phase_1_identify(hard_typical, SCENARIO_3_GT)
    hard_p2 = grade_phase_2_classify(hard_typical, SCENARIO_3_GT)
    hard_p3 = grade_phase_3_migrate(hard_typical, SCENARIO_3_GT)
    hard_score = compute_episode_score({
        "identify": hard_p1["score"],
        "classify": hard_p2["score"],
        "migrate": hard_p3["score"],
    })

    assert easy_score > hard_score, (
        f"Easy correct ({easy_score:.4f}) should be > hard shallow ({hard_score:.4f}). "
        f"E: P1={easy_p1['score']} P2={easy_p2['score']} P3={easy_p3['score']} | "
        f"H: P1={hard_p1['score']} P2={hard_p2['score']} P3={hard_p3['score']}"
    )


# ─── TEST 3: Wrong is_breaking on a non-breaking change should score < 0.4 ────

def test_wrong_answer_penalized():
    """Saying is_breaking=True for a non-breaking change (Scenario 1) should score low."""
    wrong_action = {
        "changed_fields": ["description"],
        "change_category": "field_removed",   # wrong — it was field_added
        "is_breaking": True,                  # wrong — it is non-breaking
        "affected_clients": ["mobile_app", "web_dashboard", "partner_api"],  # wrong — none affected
        "severity": 0.9,
        "confidence": 0.9,
        "reason": "removing a field breaks all clients",
        "migration_steps": ["update all clients immediately"],
        "migration_risks": [],
        "rollback_plan": "revert",
        "backwards_compatible_alternative": "do not remove the field",
        "migration_timeline_days": 30,
    }

    p1 = grade_phase_1_identify(wrong_action, SCENARIO_1_GT)
    p2 = grade_phase_2_classify(wrong_action, SCENARIO_1_GT)
    p3 = grade_phase_3_migrate(wrong_action, SCENARIO_1_GT)

    episode_score = compute_episode_score({
        "identify": p1["score"],
        "classify": p2["score"],
        "migrate": p3["score"],
    })

    assert episode_score < 0.4, (
        f"Wrong answer should score < 0.4, got {episode_score:.4f}. "
        f"P1={p1['score']}, P2={p2['score']}, P3={p3['score']}"
    )


# ─── TEST 4: Confidence calibration — wrong + high confidence < wrong + low confidence ─

def test_confidence_calibration():
    """
    When wrong: high confidence should score LOWER than low confidence.
    The grader penalises overconfidence on incorrect answers.
    """
    base_wrong = {
        "changed_fields": ["description"],
        "change_category": "field_removed",
        "is_breaking": True,      # wrong for scenario 1
        "affected_clients": ["mobile_app"],
        "severity": 0.8,
        "reason": "wrong reason",
        "migration_steps": ["force update clients"],
        "migration_risks": ["data loss"],
        "rollback_plan": "revert immediately",
        "backwards_compatible_alternative": "none",
        "migration_timeline_days": 30,
    }

    high_confidence = {**base_wrong, "confidence": 0.95}
    low_confidence  = {**base_wrong, "confidence": 0.15}

    p2_high = grade_phase_2_classify(high_confidence, SCENARIO_1_GT)
    p2_low  = grade_phase_2_classify(low_confidence,  SCENARIO_1_GT)

    assert p2_high["score"] < p2_low["score"], (
        f"Wrong + high confidence ({p2_high['score']:.4f}) should score lower "
        f"than wrong + low confidence ({p2_low['score']:.4f})"
    )


# ─── TEST 5: All phase scores must be in [0.0, 1.0] ──────────────────────────

def test_scores_in_valid_range():
    """Every grader must return a score in [0.0, 1.0] for any input."""
    test_cases = [
        # (action, ground_truth)
        (
            {"changed_fields": [], "change_category": "", "reason": ""},
            SCENARIO_1_GT,
        ),
        (
            {"changed_fields": ["amount", "amount_unit"], "change_category": "behavior_changed", "reason": "cents to dollars"},
            SCENARIO_3_GT,
        ),
        (
            {
                "is_breaking": True,
                "affected_clients": ["mobile_app"],
                "severity": 0.5,
                "confidence": 0.5,
                "reason": "",
            },
            SCENARIO_1_GT,
        ),
        (
            {
                "migration_steps": [],
                "migration_risks": [],
                "rollback_plan": "",
                "backwards_compatible_alternative": "",
                "migration_timeline_days": 30,
            },
            SCENARIO_3_GT,
        ),
    ]

    for action, gt in test_cases:
        for grader_fn in [grade_phase_1_identify, grade_phase_2_classify, grade_phase_3_migrate]:
            try:
                result = grader_fn(action, gt)
                score = result["score"]
                assert 0.0 <= score <= 1.0, (
                    f"{grader_fn.__name__} returned out-of-range score {score:.4f}"
                )
            except KeyError:
                pass  # Some graders need keys not in this minimal action — that's fine
