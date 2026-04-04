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
  set MODEL_NAME=meta-llama/Meta-Llama-3.1-8B-Instruct
  set HF_TOKEN=hf_your_huggingface_token_here
  python inference.py
"""

import os
import json
import time
import requests
from openai import OpenAI
from typing import Dict, Any, List

# ─── CONFIGURATION ────────────────────────────────────────────────────────
API_BASE_URL = os.getenv("API_BASE_URL", "https://api-inference.huggingface.co/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "meta-llama/Meta-Llama-3.1-8B-Instruct")
HF_TOKEN = os.getenv("HF_TOKEN", "")
ENV_URL = os.getenv("ENV_URL", "http://localhost:7860")

MAX_TOKENS = 800
TEMPERATURE = 0.2
FALLBACK_ACTION = {"action_type": "identify", "changed_fields": [], "change_category": "field_added"}

# ─── LLM CLIENT (uses OpenAI-compatible API) ──────────────────────────────
llm_client = OpenAI(base_url=API_BASE_URL, api_key=HF_TOKEN)

DEBUG = True

def log(msg: str):
    if DEBUG:
        print(f"[inference] {msg}")


# ─── ENVIRONMENT INTERACTION ───────────────────────────────────────────────

def reset_env(scenario_id: int) -> Dict:
    """Call /reset on the environment."""
    r = requests.post(f"{ENV_URL}/reset", params={"scenario_id": scenario_id}, timeout=30)
    r.raise_for_status()
    return r.json()


def step_env(action: Dict) -> Dict:
    """Call /step on the environment."""
    r = requests.post(f"{ENV_URL}/step", json={"action": action}, timeout=30)
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
    
    return f"""Analyze these two API versions and identify what changed.

API v1:
{spec_v1}

API v2:
{spec_v2}

Respond with ONLY this JSON (no other text):
{{
  "action_type": "identify",
  "changed_fields": ["list", "of", "field", "names", "that", "changed"],
  "change_category": "one of: field_added | field_removed | type_changed | error_code_changed | behavior_changed",
  "reason": "brief explanation of what changed and why"
}}"""


def build_phase2_prompt(observation: Dict) -> str:
    """Prompt for Phase 2: Classify the impact."""
    spec_v1 = json.dumps(observation.get("spec_v1", {}), indent=2)
    spec_v2 = json.dumps(observation.get("spec_v2", {}), indent=2)
    client_code = json.dumps(observation.get("client_code", {}), indent=2)
    client_personas = json.dumps(observation.get("client_personas", {}), indent=2)
    prev_feedback = observation.get("previous_phase_feedback", "")
    
    return f"""Analyze this API change and determine which clients will break.

API v1:
{spec_v1}

API v2:
{spec_v2}

Client Code:
{client_code}

Client Update Cycles:
{client_personas}

Previous Analysis:
{prev_feedback}

For each client, check if its code will stop working after the v2 change.

Respond with ONLY this JSON:
{{
  "action_type": "classify",
  "is_breaking": true or false,
  "affected_clients": ["list of client names that will break"],
  "severity": 0.0 to 1.0,
  "confidence": 0.0 to 1.0,
  "reason": "detailed explanation of which clients break and why"
}}"""


def build_phase3_prompt(observation: Dict) -> str:
    """Prompt for Phase 3: Propose migration plan."""
    spec_v1 = json.dumps(observation.get("spec_v1", {}), indent=2)
    spec_v2 = json.dumps(observation.get("spec_v2", {}), indent=2)
    prev_feedback = observation.get("previous_phase_feedback", "")
    
    return f"""Propose a safe migration plan for this API change.

API v1:
{spec_v1}

API v2:
{spec_v2}

Impact Analysis:
{prev_feedback}

Respond with ONLY this JSON:
{{
  "action_type": "migrate",
  "migration_steps": ["step 1", "step 2", "step 3"],
  "migration_timeline_days": 30,
  "migration_risks": ["risk 1", "risk 2"],
  "rollback_plan": "how to undo this change if something breaks",
  "backwards_compatible_alternative": "a way to make this change without breaking clients"
}}"""


def call_llm(prompt: str) -> Dict:
    """Call the LLM with exponential backoff and absolute timeout bounds."""
    for attempt in range(4):
        try:
            # 120s timeout ensures we don't blow past the 20 minute limit
            response = llm_client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": build_system_prompt()},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=MAX_TOKENS,
                temperature=TEMPERATURE,
                timeout=120.0  
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
            if attempt == 3:
                log("Max retries exceeded. Using fallback action.")
                return FALLBACK_ACTION
            time.sleep(2 ** attempt)  # exponential backoff
    return FALLBACK_ACTION


def run_scenario(scenario_id: int) -> Dict:
    """Run one complete episode (all 3 phases) for a scenario."""
    log(f"\n{'='*60}")
    log(f"Running Scenario {scenario_id}")
    log(f"{'='*60}")
    
    # Phase 1: Identify
    log("Phase 1: Resetting environment...")
    result0 = reset_env(scenario_id)
    obs0 = result0.get("observation", {})
    log(f"Scenario: {obs0.get('scenario_name', '')} | Difficulty: {obs0.get('difficulty', '')}")
    
    prompt1 = build_phase1_prompt(obs0)
    log("Phase 1: Calling LLM to identify changes...")
    action1 = call_llm(prompt1)
    log(f"Phase 1 action: {json.dumps(action1, indent=2)}")
    
    result1 = step_env(action1)
    obs1 = result1.get("observation", {})
    phase1_score = obs1.get("previous_phase_score", 0.0)
    log(f"Phase 1 score: {phase1_score:.4f}")
    log(f"Feedback: {obs1.get('previous_phase_feedback', '')}")
    
    if result1.get("done", False):
        log("Episode ended early.")
        return {"scenario_id": scenario_id, "final_score": result1.get("reward", 0.0)}
    
    # Phase 2: Classify
    log("\nPhase 2: Calling LLM to classify impact...")
    prompt2 = build_phase2_prompt(obs1)
    action2 = call_llm(prompt2)
    log(f"Phase 2 action: {json.dumps(action2, indent=2)}")
    
    result2 = step_env(action2)
    obs2 = result2.get("observation", {})
    phase2_score = obs2.get("previous_phase_score", 0.0)
    log(f"Phase 2 score: {phase2_score:.4f}")
    log(f"Feedback: {obs2.get('previous_phase_feedback', '')}")
    
    if result2.get("done", False):
        log("Episode ended after phase 2.")
        return {"scenario_id": scenario_id, "final_score": result2.get("reward", 0.0)}
    
    # Phase 3: Migrate
    log("\nPhase 3: Calling LLM to propose migration plan...")
    prompt3 = build_phase3_prompt(obs2)
    action3 = call_llm(prompt3)
    log(f"Phase 3 action: {json.dumps(action3, indent=2)}")
    
    result3 = step_env(action3)
    obs3 = result3.get("observation", {})
    final_score = result3.get("reward", 0.0)
    phase3_score = obs3.get("previous_phase_score", 0.0)
    log(f"Phase 3 score: {phase3_score:.4f}")
    log(f"FINAL EPISODE SCORE: {final_score:.4f}")
    
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
    print("\n" + "="*70)
    print("API CONTRACT EVOLUTION — BASELINE INFERENCE")
    print(f"Model: {MODEL_NAME}")
    print(f"Environment: {ENV_URL}")
    print("="*70)

    all_results = []
    
    for scenario_id in [1, 2, 3, 4, 5, 6]:
        try:
            result = run_scenario(scenario_id)
            all_results.append(result)
            time.sleep(1)  # Brief pause between scenarios
        except Exception as e:
            log(f"ERROR in scenario {scenario_id}: {e}")
            all_results.append({
                "scenario_id": scenario_id,
                "final_score": 0.0,
                "error": str(e)
            })

    # Print summary
    elapsed = time.time() - start_time
    print("\n" + "="*70)
    print("RESULTS SUMMARY")
    print("="*70)
    
    total = 0.0
    for r in all_results:
        score = r.get("final_score", 0.0)
        total += score
        name = r.get("scenario_name", f"Scenario {r['scenario_id']}")
        difficulty = r.get("difficulty", "")
        print(f"  Scenario {r['scenario_id']} ({difficulty:6s}): {score:.4f}  — {name}")
    
    avg = total / len(all_results)
    print(f"\n  AVERAGE SCORE: {avg:.4f}")
    print(f"  RUNTIME: {elapsed:.1f}s ({elapsed/60:.1f} minutes)")
    print("="*70)
    
    # Save results to JSON
    with open("baseline_scores.json", "w") as f:
        json.dump({
            "model": MODEL_NAME,
            "average_score": avg,
            "runtime_seconds": elapsed,
            "results": all_results
        }, f, indent=2)
    print("Results saved to: baseline_scores.json")


if __name__ == "__main__":
    main()
