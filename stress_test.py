import json
import time
import requests
import sys

# Connect to the local server
ENV_URL = "http://localhost:7860"

def run_stress_episode(scenario_id: int):
    """Run an episode as fast as the server allows to simulate 0ms LLM latency."""
    # Reset
    res = requests.post(f"{ENV_URL}/reset", params={"scenario_id": scenario_id})
    res.raise_for_status()

    # Identify
    requests.post(f"{ENV_URL}/step", json={"action": {
        "action_type": "identify",
        "changed_fields": ["auth_token"],
        "change_category": "field_added"
    }})

    # Classify
    requests.post(f"{ENV_URL}/step", json={"action": {
        "action_type": "classify",
        "is_breaking": True,
        "affected_clients": ["client_a"],
        "severity": 0.8,
        "confidence": 0.9,
        "reason": "stress test"
    }})

    # Migrate
    res = requests.post(f"{ENV_URL}/step", json={"action": {
        "action_type": "migrate",
        "migration_steps": ["step 1", "first update clients before deprecating v1"],
        "migration_timeline_days": 30,
        "migration_risks": ["risk 1"],
        "rollback_plan": "rollback immediately if test fails",
        "backwards_compatible_alternative": "parallel support using routing headers"
    }})
    return res.json().get("reward", 0.0)

def main():
    print("="*60)
    print("STARTING STRESS TEST: Validating 20-Minute Constraint Budget")
    print("="*60)
    
    start_time = time.time()
    
    # We run 30 episodes directly against the local server (5 repeats of all 6 scenarios)
    # This proves the absolute maximum throughput of the server logic.
    EPISODES = 30
    try:
        for i in range(EPISODES):
            run_stress_episode((i % 6) + 1)
            if (i+1) % 10 == 0:
                print(f"Completed {i+1}/{EPISODES} fast episodes...")
                
    except requests.exceptions.ConnectionError:
        print("ERROR: Could not connect to environment server. Is it running on port 7860?")
        sys.exit(1)
        
    elapsed = time.time() - start_time
    avg_sec = elapsed / EPISODES
    
    print("\nRESULTS:")
    print(f"Executed {EPISODES} full 3-phase episodes in {elapsed:.2f} seconds.")
    print(f"Average Server Latency per full episode: {avg_sec * 1000:.2f} ms")
    print("\nCONCLUSION:")
    
    # If 30 episodes take less than 10 seconds, then 6 episodes (one full inference run) 
    # takes less than 2 seconds of server time.
    if elapsed < 20.0:
        print("[OK] Server overhead is entirely negligible.")
        print("[OK] A full 6-scenario LLM evaluation run will effortlessly fit under the 20-minute limit.")
        sys.exit(0)
    else:
        print("[WARNING] Server might be sluggish. Execution times may be risking limits if LLMs are slow.")
        sys.exit(1)

if __name__ == "__main__":
    main()
