# server/graders.py — Scoring logic for all 3 phases
# All scores are between 0.0 and 1.0
# All graders are DETERMINISTIC (same input = same output every time)

from typing import Dict, List, Any


def grade_phase_1_identify(action_data: Dict, ground_truth: Dict) -> Dict:
    """
    Phase 1: Did the agent correctly identify what changed?
    
    Scores:
      - changed_fields accuracy: 50%
      - change_category correctness: 50%
    
    Max score: 1.0
    """
    # What the agent said changed
    agent_fields = set(f.lower() for f in action_data.get("changed_fields", []))
    # What actually changed
    gt_fields = set(f.lower() for f in ground_truth.get("changed_fields", []))

    # Field identification score (50%)
    if len(gt_fields) == 0:
        field_score = 1.0 if len(agent_fields) == 0 else 0.2
    else:
        correct = agent_fields & gt_fields
        if len(agent_fields) == 0:
            field_score = 0.0
        else:
            precision = len(correct) / len(agent_fields)
            recall = len(correct) / len(gt_fields)
            if precision + recall > 0:
                field_score = 2 * precision * recall / (precision + recall)
            else:
                field_score = 0.0

    # Category score (50%)
    agent_category = action_data.get("change_category", "").lower().strip()
    gt_category = ground_truth.get("change_category", "").lower().strip()
    category_score = 1.0 if agent_category == gt_category else 0.0

    # Bonus: check if reason mentions key change words
    agent_reason = action_data.get("reason", "").lower()
    keyword_matches = sum(
        1 for kw in ground_truth.get("required_change_keywords", [])
        if kw.lower() in agent_reason
    )
    keywords = ground_truth.get("required_change_keywords", [])
    keyword_bonus = (keyword_matches / len(keywords)) * 0.2 if keywords else 0.0

    total = (field_score * 0.5) + (category_score * 0.5)
    total = min(1.0, total + keyword_bonus)

    return {
        "score": round(total, 4),
        "field_score": round(field_score, 4),
        "category_score": round(category_score, 4),
        "agent_fields": list(agent_fields),
        "true_fields": list(gt_fields),
        "agent_category": agent_category,
        "true_category": gt_category,
        "keyword_bonus": round(keyword_bonus, 4)
    }


def grade_phase_2_classify(action_data: Dict, ground_truth: Dict) -> Dict:
    """
    Phase 2: Did the agent correctly classify the impact?
    
    Scores:
      - Breaking/non-breaking detection: 30%
      - Affected client identification (F1): 30%
      - Severity accuracy: 20%
      - Confidence calibration: 20%
    
    Max score: 1.0
    """
    gt_breaking = ground_truth.get("is_breaking", False)
    gt_affected = set(ground_truth.get("affected_clients", []))
    gt_severity = ground_truth.get("severity", 0.0)

    agent_breaking = action_data.get("is_breaking", None)
    agent_affected = set(action_data.get("affected_clients", []))
    agent_severity = action_data.get("severity", 0.5)
    agent_confidence = action_data.get("confidence", 0.5)

    # 1. Breaking detection (30%)
    breaking_score = 1.0 if agent_breaking == gt_breaking else 0.0

    # 2. Client identification using F1 score (30%)
    if len(gt_affected) == 0:
        client_score = 1.0 if len(agent_affected) == 0 else 0.0
    else:
        intersection = agent_affected & gt_affected
        precision = len(intersection) / len(agent_affected) if agent_affected else 0.0
        recall = len(intersection) / len(gt_affected)
        if precision + recall > 0:
            client_score = 2 * precision * recall / (precision + recall)
        else:
            client_score = 0.0

    # 3. Severity accuracy (20%)
    severity_diff = abs(agent_severity - gt_severity)
    severity_score = max(0.0, 1.0 - severity_diff)

    # 4. INNOVATION: Confidence calibration (20%)
    # If agent is RIGHT, higher confidence = higher score
    # If agent is WRONG, higher confidence = LOWER score (penalize overconfidence)
    is_correct = (agent_breaking == gt_breaking)
    if is_correct:
        confidence_score = agent_confidence
    else:
        confidence_score = 1.0 - agent_confidence

    total = (
        breaking_score * 0.30 +
        client_score * 0.30 +
        severity_score * 0.20 +
        confidence_score * 0.20
    )

    return {
        "score": round(total, 4),
        "breaking_score": round(breaking_score, 4),
        "client_score": round(client_score, 4),
        "severity_score": round(severity_score, 4),
        "confidence_calibration": round(confidence_score, 4),
        "agent_said_breaking": agent_breaking,
        "truth_is_breaking": gt_breaking,
        "agent_affected": list(agent_affected),
        "true_affected": list(gt_affected),
        "is_correct": is_correct
    }


def grade_phase_3_migrate(action_data: Dict, ground_truth: Dict) -> Dict:
    """
    Phase 3: Did the agent propose a good migration plan?
    
    Scores:
      - Migration keyword coverage: 40%
      - Has rollback plan: 20%
      - Has risk identification: 20%
      - Backwards compatible alternative quality: 20%
    
    Max score: 1.0
    """
    migration_steps = action_data.get("migration_steps", [])
    risks = action_data.get("migration_risks", [])
    rollback = action_data.get("rollback_plan", "")
    alternative = action_data.get("backwards_compatible_alternative", "")
    required_keywords = ground_truth.get("required_migration_keywords", [])

    # 1. Keyword coverage in migration steps (40%)
    all_migration_text = " ".join(migration_steps + risks + [rollback] + [alternative]).lower()
    if required_keywords:
        matched = sum(1 for kw in required_keywords if kw.lower() in all_migration_text)
        keyword_score = matched / len(required_keywords)
    else:
        keyword_score = 0.7

    # 2. Rollback plan quality (20%)
    rollback_score = 1.0 if len(rollback.strip()) > 20 else 0.0

    # 3. Risk identification quality (20%)
    risk_score = 1.0 if len(risks) > 0 else 0.0

    # 4. Backwards compatible alternative quality (20%)
    if not alternative or len(alternative) < 20:
        alt_score = 0.0
    else:
        alt_lower = alternative.lower()
        good_words = ["parallel", "support both", "alias", "deprecat",
                      "transition", "versioned", "gradual", "compatible"]
        bad_words = ["immediately remove", "force update", "hard cutover"]
        good_count = sum(1 for w in good_words if w in alt_lower)
        has_bad = any(w in alt_lower for w in bad_words)
        if has_bad:
            alt_score = 0.1
        elif good_count >= 2:
            alt_score = 1.0
        elif good_count == 1:
            alt_score = 0.6
        else:
            alt_score = 0.3

    total = (
        keyword_score * 0.40 +
        rollback_score * 0.20 +
        risk_score * 0.20 +
        alt_score * 0.20
    )

    return {
        "score": round(total, 4),
        "keyword_coverage": round(keyword_score, 4),
        "has_rollback": rollback_score == 1.0,
        "has_risks": risk_score == 1.0,
        "alternative_score": round(alt_score, 4),
        "keywords_matched": [kw for kw in required_keywords if kw.lower() in all_migration_text],
        "keywords_missing": [kw for kw in required_keywords if kw.lower() not in all_migration_text]
    }


def compute_episode_score(phase_scores: Dict[str, float]) -> float:
    """
    Compute the final weighted episode score from all 3 phases.
    
    Phase 1 (identify):  30% weight
    Phase 2 (classify):  40% weight
    Phase 3 (migrate):   30% weight
    """
    p1 = phase_scores.get("identify", 0.0)
    p2 = phase_scores.get("classify", 0.0)
    p3 = phase_scores.get("migrate", 0.0)

    total = (p1 * 0.30) + (p2 * 0.40) + (p3 * 0.30)
    return round(total, 4)
