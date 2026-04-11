"""
inference.py — Baseline Agent Script for API Contract Evolution Environment

MANDATORY REQUIREMENTS:
- Must be named 'inference.py' at project root
- Must use OpenAI Client (not Anthropic, not requests)
- Must read credentials from environment variables
- Must complete in under 20 minutes
- Must produce scores between 0.0 and 1.0 for all scenarios

ENVIRONMENT VARIABLES REQUIRED:
  API_BASE_URL   The LLM API endpoint (HuggingFace, OpenAI compatible)
  MODEL_NAME     The model identifier
  HF_TOKEN       Your HuggingFace API key

HOW TO RUN (Windows Command Prompt):
  set API_BASE_URL=https://api-inference.huggingface.co/v1
#   set MODEL_NAME=meta-llama/Llama-3.3-70B-Instruct
  set HF_TOKEN=hf_your_huggingface_token_here
  python inference.py
"""

import os
import sys
import json
import time
import requests
from openai import OpenAI
from typing import Dict, Any, List

# Guarantee stdout is never buffered — critical for the Meta validator
# which reads structured blocks directly from the process's stdout pipe.
try:
    sys.stdout.reconfigure(line_buffering=True)  # type: ignore[attr-defined]
except AttributeError:
    pass  # Python < 3.7 fallback (line_buffering not available)

# ─── CONFIGURATION ────────────────────────────────────────────────────────
API_BASE_URL = os.getenv("API_BASE_URL", "https://api-inference.huggingface.co/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "meta-llama/Meta-Llama-3.1-8B-Instruct")
HF_TOKEN = os.getenv("HF_TOKEN", "")
ENV_URL = os.getenv("ENV_URL", "http://localhost:7860")

MAX_TOKENS = 512
TEMPERATURE = 0.2
FALLBACK_ACTION = {"action_type": "identify", "changed_fields": [], "change_category": "field_added"}

# Minimum non-zero score — OpenEnv validator requires strictly (0, 1), never 0.0 or 1.0
_SCORE_MIN = 0.01
_SCORE_MAX = 0.99


def _safe_score(val) -> float:
    """Clamp any score to strictly (0, 1) — validator rejects 0.0 and 1.0 exactly."""
    try:
        v = float(val)
    except (TypeError, ValueError):
        v = _SCORE_MIN
    return max(_SCORE_MIN, min(_SCORE_MAX, v))

# ─── LLM CLIENT (uses OpenAI-compatible API) ──────────────────────────────
llm_client = OpenAI(base_url=API_BASE_URL, api_key=HF_TOKEN)

DEBUG = True

def log(msg: str):
    if DEBUG:
        print(f"[inference] {msg}")


# ─── ENVIRONMENT INTERACTION ───────────────────────────────────────────────

def get_obs(response: Dict) -> Dict:
    """Handle both flat and OpenEnv-wrapped observation formats."""
    if "observation" in response:
        return response["observation"]
    return response


def reset_env(scenario_id: int) -> Dict:
    """Call /reset on the environment, sending scenario_id via params and JSON body for robustness."""
    r = requests.post(
        f"{ENV_URL}/reset", 
        params={"scenario_id": scenario_id}, 
        json={"scenario_id": scenario_id},
        timeout=30
    )
    r.raise_for_status()
    return get_obs(r.json())


def step_env(action: Dict) -> Dict:
    r = requests.post(f"{ENV_URL}/step", json=action, timeout=30)
    r.raise_for_status()
    return r.json()


def get_state() -> Dict:
    """Call /state on the environment."""
    r = requests.get(f"{ENV_URL}/state", timeout=30)
    r.raise_for_status()
    return r.json()


# ─── LLM AGENT LOGIC ──────────────────────────────────────────────────────

def build_system_prompt() -> str:
    return """You are an expert API compatibility analyst.
You analyze API version changes and determine:
1. What specifically changed between versions
2. Whether the change is backwards-compatible or breaking
3. Which client integrations will break and why
4. How to safely migrate without breaking production

Always respond with valid JSON only. No explanations outside the JSON."""


def build_phase1_prompt(observation: Dict) -> str:
    """Prompt for Phase 1: Identify what changed."""
    spec_v1 = json.dumps(observation.get("spec_v1", {}), indent=2)
    spec_v2 = json.dumps(observation.get("spec_v2", {}), indent=2)

    return f"""You are an expert API compatibility analyst. Your job is to find EVERY difference
between two API versions, including semantic changes that are invisible to schema diffing tools.

API v1:
{spec_v1}

API v2:
{spec_v2}

Analysis approach:
1. Compare every field, type, endpoint, error code, example value, and behavioral note
2. Look for SEMANTIC changes: unit changes (cents vs dollars), strategy changes
   (per_ip vs per_user), format changes (opaque token vs JWT)
3. Example values often reveal unit changes that the schema hides — compare them carefully
4. Identify the SINGLE most important change_category

Categories:
  field_added       — a new optional field was introduced
  field_removed     — an existing field was removed
  type_changed      — a field's type or format changed (number, string, JWT, etc.)
  error_code_changed — an error code string was renamed or changed value
  behavior_changed  — same API surface, different runtime behavior or semantics

Respond with ONLY valid JSON:
{{
  "action_type": "identify",
  "changed_fields": ["dot.notation.field.names"],
  "change_category": "one of the 5 categories above",
  "reason": "precise technical explanation of what changed and why it matters"
}}"""


def build_phase2_prompt(observation: Dict) -> str:
    """Prompt for Phase 2: Classify the impact."""
    spec_v1 = json.dumps(observation.get("spec_v1", {}), indent=2)
    spec_v2 = json.dumps(observation.get("spec_v2", {}), indent=2)
    client_code = observation.get("client_code", {})
    client_personas = json.dumps(observation.get("client_personas", {}), indent=2)
    prev = observation.get("previous_phase_feedback", "")

    # Format client code with explicit labels
    client_analysis = ""
    for name, code in client_code.items():
        client_analysis += f"\n=== Client: {name} ===\n{code}\n"

    return f"""You are an expert API compatibility analyst.

API v1:
{spec_v1}

API v2:
{spec_v2}

Client code (currently running against v1):
{client_analysis}

Client update constraints:
{client_personas}

Previous change analysis: {prev}

For EACH client, read their code line by line and answer:
1. Does this client's code reference the SPECIFIC value/behavior that changed?
2. If yes — will it break loudly (exception) or silently (wrong output)?
3. Which exact line of code causes the break?

IMPORTANT: Your confidence value MUST reflect your actual certainty.
- If you are very sure of your analysis, set confidence=0.8–1.0
- If there is ambiguity, set confidence=0.4–0.6
- Do NOT default to 0.5 — use your real assessment

Respond with ONLY valid JSON:
{{
  "action_type": "classify",
  "is_breaking": true or false,
  "affected_clients": ["exact client names from above that WILL break"],
  "severity": 0.0 to 1.0,
  "confidence": 0.0 to 1.0,
  "reason": "for each affected client: quote the exact line that breaks and explain why"
}}"""


def build_phase3_prompt(observation: Dict) -> str:
    """Prompt for Phase 3: Propose migration plan."""
    spec_v1 = json.dumps(observation.get("spec_v1", {}), indent=2)
    spec_v2 = json.dumps(observation.get("spec_v2", {}), indent=2)
    prev = observation.get("previous_phase_feedback", "")
    deprecation_window = observation.get("deprecation_window_days", 0)
    deadline_note = f"\nIMPORTANT: The deprecation window for this scenario is {deprecation_window} days. Your migration_timeline_days MUST be between 30 and {deprecation_window}." if deprecation_window > 0 else ""

    return f"""You are an expert API migration planner at a major tech company.

API v1:
{spec_v1}

API v2:
{spec_v2}

Impact analysis from the previous phase:
{prev}{deadline_note}

Here is an example of an EXCELLENT migration plan response. Use this as a model:

```json
{{
  "action_type": "migrate",
  "migration_steps": [
    "Deploy v2 endpoint in parallel with v1 — both versions run simultaneously with no traffic cutover",
    "Enable feature flag for 1% canary traffic to v2, monitor error rates and latency on dashboard",
    "Send 90-day deprecation notice to all affected partners before sunsetting v1",
    "Gradually shift traffic: 1% → 10% → 50% → 100% using weighted routing over 30 days",
    "Migrate clients completely to v2 before removing v1 endpoint",
    "Run DB migration scripts in shadow mode, validate against production data",
    "Flip feature flag off and revert to v1 routing if error rate exceeds 0.1%"
  ],
  "migration_timeline_days": 60,
  "migration_risks": [
    "Mobile app has 90-day update cycle — clients cannot update immediately",
    "Database schema migration required before v2 go-live",
    "Partner SLA requires 90 days advance notice"
  ],
  "rollback_plan": "Immediately revert API Gateway routing back to v1 handler. Disable v2 feature flag. Roll back DB migration scripts. Notify affected clients of emergency revert.",
  "backwards_compatible_alternative": "Run v1 and v2 endpoints in parallel permanently. Use versioned URL paths (/v1/, /v2/) so clients can migrate at their own pace. Add deprecation headers to v1 responses with sunset date."
}}
```

Now create your migration plan for the API change above. Requirements:
- Use parallel deployment (never hard cutover — that is an antipattern)
- Use gradual/canary rollout with feature flags
- Update clients first BEFORE deprecating v1
- Use major versioning (v2) for breaking changes
- Include monitoring and alerting during rollout
- Give a realistic rollback plan with specific steps
- Reference both v1 and v2 coexisting in your alternative approach

Respond with ONLY valid JSON (no markdown, no explanation outside JSON):
{{
  "action_type": "migrate",
  "migration_steps": ["ordered, specific steps"],
  "migration_timeline_days": number,
  "migration_risks": ["specific production risks"],
  "rollback_plan": "specific revert steps",
  "backwards_compatible_alternative": "concrete dual-version support strategy"
}}"""


def call_llm(prompt: str) -> Dict:
    """Call the LLM with exponential backoff and absolute timeout bounds."""
    # Cap maximum retries to aggressively protect against 20-minute constraint limit
    for attempt in range(3):
        try:
            # 45s timeout ensures fast failure and prevents episode blockages
            response = llm_client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": build_system_prompt()},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=MAX_TOKENS,
                temperature=TEMPERATURE,
                timeout=45.0
            )
            content = response.choices[0].message.content.strip()
            
            # Remove deepseek/reasoning tags if present
            import re
            content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
            
            # Clean up JSON (remove markdown code blocks if present)
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            
            return json.loads(content)
            
        except json.JSONDecodeError as e:
            log(f"JSON parse error: {e}. Using fallback action.")
            return FALLBACK_ACTION
        except Exception as e:
            log(f"LLM error on attempt {attempt+1}: {e}")
            if attempt == 2:
                log("Max retries exceeded. Using fallback action.")
                return FALLBACK_ACTION
            time.sleep(2 ** attempt)  # exponential backoff
    return FALLBACK_ACTION


def emit_start(task_name: str):
    """Emit the mandatory [START] block required by the Meta validator."""
    print(f"[START] task={task_name}", flush=True)


def emit_step(step_num: int, reward: float):
    """Emit a mandatory [STEP] block required by the Meta validator."""
    safe = _safe_score(reward)
    print(f"[STEP] step={step_num} reward={safe:.4f}", flush=True)


def emit_end(task_name: str, score: float, steps: int):
    """Emit the mandatory [END] block required by the Meta validator."""
    safe = _safe_score(score)
    print(f"[END] task={task_name} score={safe:.4f} steps={steps}", flush=True)


def run_scenario(scenario_id: int) -> Dict:
    """Run one complete episode (all 3 phases) for a scenario."""
    log(f"\n{'='*60}")
    log(f"Running Scenario {scenario_id}")
    log(f"{'='*60}")

    task_name = f"scenario_{scenario_id}"
    emit_start(task_name)
    step_count = 0

    # Phase 1: Identify
    log("Phase 1: Resetting environment...")
    result0 = reset_env(scenario_id)
    obs0 = result0
    log(f"Scenario: {obs0.get('scenario_name', '')} | Difficulty: {obs0.get('difficulty', '')}")

    prompt1 = build_phase1_prompt(obs0)
    log("Phase 1: Calling LLM to identify changes...")
    action1 = call_llm(prompt1)
    log(f"Phase 1 action: {json.dumps(action1, indent=2)}")

    result1 = step_env(action1)
    result1 = get_obs(result1)
    obs1 = result1
    phase1_score = _safe_score(obs1.get("previous_phase_score", _SCORE_MIN))
    step_count += 1
    emit_step(step_count, phase1_score)
    log(f"Phase 1 score: {phase1_score:.4f}")
    log(f"Feedback: {obs1.get('previous_phase_feedback', '')}")

    if result1.get("done", False):
        log("Episode ended early.")
        final = _safe_score(result1.get("reward", _SCORE_MIN))
        emit_end(task_name, final, step_count)
        return {"scenario_id": scenario_id, "final_score": final}

    # Phase 2: Classify
    log("\nPhase 2: Calling LLM to classify impact...")
    prompt2 = build_phase2_prompt(obs1)
    action2 = call_llm(prompt2)
    log(f"Phase 2 action: {json.dumps(action2, indent=2)}")

    result2 = step_env(action2)
    result2 = get_obs(result2)
    obs2 = result2
    phase2_score = _safe_score(obs2.get("previous_phase_score", _SCORE_MIN))
    step_count += 1
    emit_step(step_count, phase2_score)
    log(f"Phase 2 score: {phase2_score:.4f}")
    log(f"Feedback: {obs2.get('previous_phase_feedback', '')}")

    if result2.get("done", False):
        log("Episode ended after phase 2.")
        final = _safe_score(result2.get("reward", _SCORE_MIN))
        emit_end(task_name, final, step_count)
        return {"scenario_id": scenario_id, "final_score": final}

    # Phase 3: Migrate
    log("\nPhase 3: Calling LLM to propose migration plan...")
    prompt3 = build_phase3_prompt(obs2)
    action3 = call_llm(prompt3)
    log(f"Phase 3 action: {json.dumps(action3, indent=2)}")

    result3 = step_env(action3)
    result3 = get_obs(result3)
    obs3 = result3
    final_score = _safe_score(result3.get("reward", _SCORE_MIN))
    phase3_score = _safe_score(obs3.get("previous_phase_score", _SCORE_MIN))
    step_count += 1
    emit_step(step_count, phase3_score)
    log(f"Phase 3 score: {phase3_score:.4f}")
    log(f"FINAL EPISODE SCORE: {final_score:.4f}")

    emit_end(task_name, final_score, step_count)

    return {
        "scenario_id": scenario_id,
        "scenario_name": obs0.get("scenario_name", ""),
        "difficulty": obs0.get("difficulty", ""),
        "phase_scores": {
            "identify": phase1_score,
            "classify": phase2_score,
            "migrate": phase3_score
        },
        "final_score": final_score
    }


# ─── MAIN ─────────────────────────────────────────────────────────────────

def main():
    start_time = time.time()
    print("\n" + "="*70, flush=True)
    print("API CONTRACT EVOLUTION — BASELINE INFERENCE", flush=True)
    print(f"Model: {MODEL_NAME}", flush=True)
    print(f"Environment: {ENV_URL}", flush=True)
    print("="*70, flush=True)

    all_results = []

    for scenario_id in [1, 2, 3, 4, 5, 6]:
        try:
            result = run_scenario(scenario_id)
            all_results.append(result)
            time.sleep(0.2)  # Optimized pause between scenarios
        except Exception as e:
            log(f"ERROR in scenario {scenario_id}: {e}")
            # Emit a minimal-score END block — validator rejects 0.0 scores
            task_name = f"scenario_{scenario_id}"
            emit_start(task_name)
            emit_step(1, _SCORE_MIN)
            emit_end(task_name, _SCORE_MIN, 1)
            all_results.append({
                "scenario_id": scenario_id,
                "final_score": _SCORE_MIN,
                "error": str(e)
            })

    # Print summary
    elapsed = time.time() - start_time
    print("\n" + "="*70, flush=True)
    print("RESULTS SUMMARY", flush=True)
    print("="*70, flush=True)

    total = 0.0
    for r in all_results:
        score = r.get("final_score", 0.0)
        total += score
        name = r.get("scenario_name", f"Scenario {r['scenario_id']}")
        difficulty = r.get("difficulty", "")
        print(f"  Scenario {r['scenario_id']} ({difficulty:6s}): {score:.4f}  — {name}", flush=True)

    avg = total / len(all_results)
    print(f"\n  AVERAGE SCORE: {avg:.4f}", flush=True)
    print(f"  RUNTIME: {elapsed:.1f}s ({elapsed/60:.1f} minutes)", flush=True)
    print("="*70, flush=True)

    # Save results to JSON
    with open("baseline_scores.json", "w") as f:
        json.dump({
            "model": MODEL_NAME,
            "average_score": avg,
            "runtime_seconds": elapsed,
            "results": all_results
        }, f, indent=2)
    print("Results saved to: baseline_scores.json", flush=True)


if __name__ == "__main__":
    main()
