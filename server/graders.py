# server/graders.py — Scoring logic for all 3 phases
# ALL scores are STRICTLY between 0.001 and 0.999 — NEVER 0.0 or 1.0
# The OpenEnv validator REJECTS scores of exactly 0.0 or 1.0.
# _clamp() is applied at EVERY score output point: intermediates AND totals.

from typing import Dict, List, Any


# ─── STRICT SCORE BOUNDS ──────────────────────────────────────────────────────

_SCORE_MIN = 0.01   # Hard floor — validator rejects 0.0
_SCORE_MAX = 0.99   # Hard ceiling — validator rejects 1.0


def _clamp(val: float) -> float:
    """
    Guarantee a score is STRICTLY within (0, 1) — never 0.0, never 1.0.
    This is applied at EVERY score boundary: intermediates and finals.
    The OpenEnv validator will reject any score == 0.0 or == 1.0 exactly.
    """
    try:
        v = float(val)
        if v != v:  # NaN check
            return _SCORE_MIN
        return max(_SCORE_MIN, min(_SCORE_MAX, v))
    except (TypeError, ValueError):
        return _SCORE_MIN


def _safe_round(val: float, ndigits: int = 4) -> float:
    """Round and clamp — ensures round(0.9995, 4) never becomes 1.0."""
    return _clamp(round(float(val), ndigits))


# ─── SYNONYM TABLES (so any capable LLM scores correctly regardless of vocabulary) ──

# Phase 1 category synonyms — grouped by canonical category
CATEGORY_SYNONYMS = {
    "field_added": [
        "field_added", "field added", "new field", "added field", "optional field added",
        "field introduced", "new parameter", "added parameter", "new property"
    ],
    "field_removed": [
        "field_removed", "field removed", "removed field", "deleted field",
        "field deleted", "parameter removed", "deprecated field"
    ],
    "type_changed": [
        "type_changed", "type changed", "type change", "format changed",
        "type_change", "schema change", "schema changed", "data type changed",
        "data format changed", "format change"
    ],
    "error_code_changed": [
        "error_code_changed", "error code changed", "error renamed",
        "error code renamed", "status code changed", "error string changed",
        "error_renamed", "error code change"
    ],
    "behavior_changed": [
        "behavior_changed", "behavior changed", "semantic change",
        "semantic changed", "semantics changed", "behavioral change",
        "implicit change", "logic changed", "calculation changed",
        "runtime behavior changed", "behavior change"
    ],
}


def normalize_category(category: str) -> str:
    """Map any synonym to the canonical category name."""
    cat_lower = category.lower().strip()
    for canonical, synonyms in CATEGORY_SYNONYMS.items():
        if cat_lower in synonyms or cat_lower == canonical:
            return canonical
    # Partial match fallback
    for canonical, synonyms in CATEGORY_SYNONYMS.items():
        for syn in synonyms:
            if cat_lower in syn or syn in cat_lower:
                return canonical
    return cat_lower


def grade_phase_1_identify(action_data: Dict, ground_truth: Dict) -> Dict:
    """
    Phase 1: Did the agent correctly identify what changed?

    Scores:
      - changed_fields accuracy (F1): 60%
      - change_category correctness (with synonyms): 40%

    Keyword bonus only applies when core score >= 0.5 to prevent rewarding hallucination.
    Max score: 0.999 (never 1.0)
    """
    # What the agent said changed
    agent_fields = set(f.lower().strip() for f in action_data.get("changed_fields", []))
    # What actually changed
    gt_fields = set(f.lower().strip() for f in ground_truth.get("changed_fields", []))

    # Field identification score (60%) using F1
    if len(gt_fields) == 0:
        raw_field_score = 0.85 if len(agent_fields) == 0 else 0.2
    else:
        # Fuzzy match: check if any agent field is a substring of a gt field or vice versa
        matched = set()
        for af in agent_fields:
            for gf in gt_fields:
                if af in gf or gf in af or af == gf:
                    matched.add(gf)
        correct = len(matched)
        if len(agent_fields) == 0:
            raw_field_score = 0.0
        else:
            precision = correct / len(agent_fields)
            recall = correct / len(gt_fields)
            if precision + recall > 0:
                raw_field_score = 2 * precision * recall / (precision + recall)
            else:
                raw_field_score = 0.0
    field_score = _clamp(raw_field_score)

    # Category score (40%) with full synonym matching
    agent_category_raw = action_data.get("change_category", "").lower().strip()
    gt_category_raw = ground_truth.get("change_category", "").lower().strip()

    agent_category = normalize_category(agent_category_raw)
    gt_category = normalize_category(gt_category_raw)
    # Use 0.9 instead of 1.0 to avoid ceiling — clamped anyway
    raw_category_score = 0.9 if agent_category == gt_category else 0.0
    category_score = _clamp(raw_category_score)

    core_score = _clamp((field_score * 0.60) + (category_score * 0.40))

    # Keyword bonus (max 0.15) — ONLY applied when core answer is already correct (>=0.5)
    # This prevents rewarding hallucination
    keyword_bonus = 0.0
    if core_score >= 0.5:
        agent_reason = action_data.get("reason", "").lower()
        keywords = ground_truth.get("required_change_keywords", [])
        if keywords:
            keyword_matches = sum(
                1 for kw in keywords if kw.lower() in agent_reason
            )
            keyword_bonus = (keyword_matches / len(keywords)) * 0.15

    # Cap at 0.99 — never allow 1.0
    total = _safe_round(min(_SCORE_MAX, core_score + keyword_bonus))

    return {
        "score": total,
        "field_score": _safe_round(field_score),
        "category_score": _safe_round(category_score),
        "agent_fields": list(agent_fields),
        "true_fields": list(gt_fields),
        "agent_category": agent_category_raw,
        "true_category": gt_category_raw,
        "keyword_bonus": _safe_round(keyword_bonus),
    }


def grade_phase_2_classify(action_data: Dict, ground_truth: Dict) -> Dict:
    """
    Phase 2: Did the agent correctly classify the impact?

    Scores:
      - Breaking/non-breaking detection: 35%
      - Affected client identification (F1, fuzzy): 35%
      - Severity accuracy: 15%
      - Confidence calibration: 15%

    Confidence calibration: rewards being right AND confident.
    Penalizes being wrong AND confident (overconfidence).
    Max score: 0.999 (never 1.0)
    """
    gt_breaking = ground_truth.get("is_breaking", False)
    gt_affected = [c.lower() for c in ground_truth.get("affected_clients", [])]
    gt_severity = float(ground_truth.get("severity", 0.5))

    agent_breaking = action_data.get("is_breaking", None)
    agent_affected_raw = action_data.get("affected_clients", [])
    agent_affected = [c.lower() for c in agent_affected_raw]
    # Clamp incoming agent values: never trust them to be in bounds
    agent_severity = _clamp(float(action_data.get("severity", 0.5)))
    agent_confidence = _clamp(float(action_data.get("confidence", 0.5)))

    # 1. Breaking detection (35%)
    # Use 0.9 for correct, 0.0 for wrong — never raw 1.0
    is_correct = (agent_breaking == gt_breaking)
    raw_breaking_score = 0.9 if is_correct else 0.0
    breaking_score = _clamp(raw_breaking_score)

    # 2. Client identification using fuzzy F1 score (35%)
    # Fuzzy match: "cdn_proxy" matches "cdn" or "proxy"
    def client_match(agent_name: str, gt_names: list) -> bool:
        for g in gt_names:
            if agent_name in g or g in agent_name or agent_name == g:
                return True
        return False

    if len(gt_affected) == 0:
        raw_client_score = 0.85 if len(agent_affected) == 0 else 0.2
    else:
        true_positives = sum(1 for a in agent_affected if client_match(a, gt_affected))
        precision = true_positives / len(agent_affected) if agent_affected else 0.0
        recall = true_positives / len(gt_affected)
        if precision + recall > 0:
            raw_client_score = 2 * precision * recall / (precision + recall)
        else:
            raw_client_score = 0.0
    client_score = _clamp(raw_client_score)

    # 3. Severity accuracy (15%)
    # gt_severity may be 0.0 or 1.0 from ground truth — clamp the result, not the input
    severity_diff = abs(agent_severity - gt_severity)
    raw_severity_score = max(0.0, 1.0 - severity_diff)
    severity_score = _clamp(raw_severity_score)

    # 4. Confidence calibration (15%)
    # If RIGHT: score = confidence (reward being appropriately confident when correct)
    # If WRONG: score = max(0, 0.5 - confidence) (reward uncertainty when wrong, but cap gain)
    # This prevents gaming by always setting confidence=0.01
    if is_correct:
        # agent_confidence already clamped to (0.001, 0.999)
        confidence_score = agent_confidence
    else:
        # Wrong answer: reward humility but cap the max gain
        raw_conf = max(0.0, 0.5 - agent_confidence)
        confidence_score = _clamp(raw_conf) if raw_conf > 0 else _SCORE_MIN

    total = _safe_round(
        breaking_score * 0.35
        + client_score * 0.35
        + severity_score * 0.15
        + confidence_score * 0.15
    )

    return {
        "score": total,
        "breaking_score": _safe_round(breaking_score),
        "client_score": _safe_round(client_score),
        "severity_score": _safe_round(severity_score),
        "confidence_calibration": _safe_round(confidence_score),
        "agent_said_breaking": agent_breaking,
        "truth_is_breaking": gt_breaking,
        "agent_affected": list(agent_affected),
        "true_affected": list(gt_affected),
        "is_correct": is_correct,
    }


# ─── PHASE 3 SYNONYM BANKS ────────────────────────────────────────────────────

# All phrases that mean "run both versions simultaneously"
PARALLEL_SYNONYMS = [
    "parallel", "side by side", "alongside", "dual support", "run both",
    "support both", "simultaneous", "coexist", "run concurrently",
    "maintain both", "keep old endpoint", "keep v1 alive", "dual-run",
    "run in parallel", "both versions", "version coexistence", "backward shim"
]

# All phrases that mean "gradual / canary rollout"
CANARY_SYNONYMS = [
    "canary", "gradual", "phased rollout", "phased deployment", "staged rollout",
    "progressive rollout", "incremental rollout", "traffic splitting",
    "traffic shifting", "weighted routing", "percentage rollout",
    "blue-green", "blue green", "shadow traffic", "shadow mode",
    "feature flag", "feature toggle", "dark launch", "ring deployment",
    "rolling deployment", "rolling update", "percentage-based"
]

# All phrases that mean "monitor during rollout"
MONITORING_SYNONYMS = [
    "monitoring", "monitor", "observability", "observable", "alert", "alerting",
    "dashboard", "metric", "metrics", "logging", "log errors",
    "track", "watch", "telemetry", "trace", "sentry", "datadog",
    "error rate", "success rate", "latency", "p99", "p95"
]

# All phrases that mean "update clients before deprecating"
SEQUENCE_SYNONYMS = [
    "before deprecating", "before sunsetting", "before removing",
    "migrate clients first", "update clients first", "client migration first",
    "all clients updated", "until all traffic", "after clients have migrated",
    "clients must update first", "notify clients before", "partner notice",
    "90 days notice", "deprecation notice", "communicate first",
    "update before removing", "migration complete before"
]

# All phrases that mean "rollback if something breaks"
ROLLBACK_SYNONYMS = [
    "rollback", "roll back", "revert", "undo", "restore",
    "switch back", "flip back", "traffic back to", "route back",
    "disable feature flag", "turn off", "fall back", "fallback"
]


def _text_contains_any(text: str, phrases: list) -> bool:
    """Check if text contains any of the given phrases."""
    return any(p.lower() in text for p in phrases)


def _count_matches(text: str, phrases: list) -> int:
    """Count how many phrases appear in text."""
    return sum(1 for p in phrases if p.lower() in text)


def grade_phase_3_migrate(action_data: Dict, ground_truth: Dict) -> Dict:
    """
    Phase 3: Did the agent propose a good migration plan?

    Scores:
      - Required concept coverage (scenario-specific keywords + synonyms): 30%
      - Has substantive rollback plan: 10%
      - Has risk identification: 10%
      - Backwards compatible alternative quality: 20%
      - Sequencing & traffic shifting awareness: 20%
      - Timeline & SemVer awareness: 10%

    Max score: 0.999 (never 1.0)
    """
    migration_steps = action_data.get("migration_steps", [])
    risks = action_data.get("migration_risks", [])
    rollback = action_data.get("rollback_plan", "")
    alternative = action_data.get("backwards_compatible_alternative", "")
    required_keywords = ground_truth.get("required_migration_keywords", [])

    # Combine all text for global search
    all_text = " ".join(migration_steps + risks + [rollback, alternative]).lower()

    # 1. Concept coverage (30%)
    # Match scenario-specific keywords + universal synonyms
    universal_concepts = PARALLEL_SYNONYMS + CANARY_SYNONYMS + MONITORING_SYNONYMS
    universal_matches = min(0.95, _count_matches(all_text, universal_concepts) * 0.08)

    if required_keywords:
        # Each keyword also accepts synonyms
        scenario_matches = 0
        for kw in required_keywords:
            kw_lower = kw.lower()
            # Direct match
            if kw_lower in all_text:
                scenario_matches += 1
            # Synonym expansion for common patterns
            elif any(syn in all_text for syn in PARALLEL_SYNONYMS) and "parallel" in kw_lower:
                scenario_matches += 1
            elif any(syn in all_text for syn in CANARY_SYNONYMS) and (
                "canary" in kw_lower or "gradual" in kw_lower
            ):
                scenario_matches += 1
            elif any(syn in all_text for syn in MONITORING_SYNONYMS) and "monitor" in kw_lower:
                scenario_matches += 1
        raw_keyword_score = min(0.95, (scenario_matches / len(required_keywords)) + universal_matches)
    else:
        raw_keyword_score = min(0.95, 0.7 + universal_matches)
    keyword_score = _clamp(raw_keyword_score)

    # 2. Rollback plan quality (10%)
    has_rollback_concept = _text_contains_any(rollback.lower(), ROLLBACK_SYNONYMS)
    if len(rollback.strip()) > 20 and has_rollback_concept:
        raw_rollback_score = 0.9   # was 1.0
    elif len(rollback.strip()) > 20:
        raw_rollback_score = 0.5
    else:
        raw_rollback_score = 0.05  # was 0.0 — floor to avoid exact 0
    rollback_score = _clamp(raw_rollback_score)

    # 3. Risk identification quality (10%)
    raw_risk_score = min(0.9, len([r for r in risks if len(r.strip()) > 5]) * 0.4)
    risk_score = _clamp(raw_risk_score)

    # 4. Backwards compatible alternative quality (20%)
    if not alternative or len(alternative.strip()) < 20:
        raw_alt_score = 0.05  # was 0.0 — floor to avoid exact 0
    else:
        alt_lower = alternative.lower()
        good_words = [
            "parallel", "support both", "alias", "deprecat",
            "transition", "versioned", "gradual", "compatible",
            "header", "routing", "both versions", "coexist",
            "feature flag", "v1 and v2", "dual", "shim", "adapter"
        ]
        bad_words = ["immediately remove", "force update", "hard cutover", "just delete", "mandatory upgrade"]
        good_count = sum(1 for w in good_words if w in alt_lower)
        has_bad = any(w in alt_lower for w in bad_words)

        if has_bad:
            raw_alt_score = 0.1
        elif good_count >= 3:
            raw_alt_score = 0.9   # was 1.0
        elif good_count == 2:
            raw_alt_score = 0.8
        elif good_count == 1:
            raw_alt_score = 0.5
        else:
            raw_alt_score = 0.3
    alt_score = _clamp(raw_alt_score)

    # 5. Sequencing & Traffic Shifting (20%) — Using full synonym banks
    is_breaking = ground_truth.get("is_breaking", False)

    has_sequence = _text_contains_any(all_text, SEQUENCE_SYNONYMS)
    has_traffic_shift = _text_contains_any(all_text, CANARY_SYNONYMS)
    has_parallel = _text_contains_any(all_text, PARALLEL_SYNONYMS)

    if is_breaking:
        points = 0.0
        if has_sequence:
            points += 0.4
        if has_traffic_shift:
            points += 0.4
        if has_parallel:
            points += 0.2
        raw_sequence_score = min(0.9, points)
    else:
        # Non-breaking: just mentioning monitoring/parallel is enough
        raw_sequence_score = 0.85 if (has_parallel or has_traffic_shift) else 0.65
    sequence_score = _clamp(raw_sequence_score)

    # 6. Timeline & SemVer Awareness (10%)
    timeline = action_data.get("migration_timeline_days", 30)
    deprecation_window = ground_truth.get("deprecation_window_days", 0)

    if deprecation_window > 0:
        if 30 <= timeline <= deprecation_window:
            raw_timeline_math = 0.9   # was 1.0
        elif timeline < 30:
            raw_timeline_math = 0.3   # too fast — unrealistic
        else:
            raw_timeline_math = 0.5   # over budget
    else:
        raw_timeline_math = 0.9 if timeline >= 14 else 0.5
    timeline_math_score = _clamp(raw_timeline_math)

    # SemVer — broader synonym matching
    raw_semver = 0.0
    if is_breaking:
        breaking_semver = [
            "major version", "v2", "v 2", "2.0", "major bump",
            "semver major", "breaking change version", "major release",
            "increment major", "new major"
        ]
        raw_semver = 0.9 if _text_contains_any(all_text, breaking_semver) else 0.05
    else:
        nonbreaking_semver = [
            "minor version", "patch", "v1.1", "v1.2", "backwards compatible",
            "minor bump", "minor release", "semver minor"
        ]
        raw_semver = 0.9 if _text_contains_any(all_text, nonbreaking_semver) else 0.3
    semver_score = _clamp(raw_semver)

    combined_meta_score = _clamp((timeline_math_score * 0.5) + (semver_score * 0.5))

    total = _safe_round(
        keyword_score * 0.30
        + rollback_score * 0.10
        + risk_score * 0.10
        + alt_score * 0.20
        + sequence_score * 0.20
        + combined_meta_score * 0.10
    )

    return {
        "score": total,
        "keyword_coverage": _safe_round(keyword_score),
        "has_rollback": rollback_score > 0.5,
        "has_risks": risk_score > _SCORE_MIN,
        "alternative_score": _safe_round(alt_score),
        "sequence_awareness": _safe_round(sequence_score),
        "meta_awareness": _safe_round(combined_meta_score),
        "keywords_matched": [kw for kw in required_keywords if kw.lower() in all_text],
        "keywords_missing": [kw for kw in required_keywords if kw.lower() not in all_text],
    }


def compute_episode_score(phase_scores: Dict[str, float]) -> float:
    """
    Compute the final weighted episode score from all 3 phases.

    Phase 1 (identify):  30% weight
    Phase 2 (classify):  40% weight
    Phase 3 (migrate):   30% weight

    Returns a score strictly in (0.001, 0.999) — NEVER 0.0 or 1.0.
    """
    # Clamp each individual phase score before weighting (defensive)
    p1 = _clamp(phase_scores.get("identify", _SCORE_MIN))
    p2 = _clamp(phase_scores.get("classify", _SCORE_MIN))
    p3 = _clamp(phase_scores.get("migrate", _SCORE_MIN))

    total = (p1 * 0.30) + (p2 * 0.40) + (p3 * 0.30)
    # Final clamp — absolute guarantee
    return _safe_round(total)
