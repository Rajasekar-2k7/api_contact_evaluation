import time
import concurrent.futures
from server.api_contract_evolution_environment import ApiContractEvolutionEnvironment
from models import ApiContractAction

def run_simulated_episode(scenario_id: int):
    """Simulate a lightning-fast model querying the environment directly without LLM overhead."""
    env = ApiContractEvolutionEnvironment()
    env.reset(scenario_id=scenario_id)
    
    # Phase 1: Identify
    env.step(ApiContractAction(action_type="identify", changed_fields=["test"]))
    
    # Phase 2: Classify
    env.step(ApiContractAction(action_type="classify", is_breaking=True))
    
    # Phase 3: Migrate
    res = env.step(ApiContractAction(action_type="migrate", migration_steps=["do nothing"]))
    return res.cumulative_score

def main():
    print("Beginning Environment Stress Test (Simulating 50 concurrent episodes)")
    start_time = time.time()
    
    # Simulate a barrage of 50 episodes to prove the environment compute overhead is negligible
    scenarios = [1, 2, 3, 4, 5, 6] * 9  # 54 episodes
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(run_simulated_episode, s): s for s in scenarios}
        for future in concurrent.futures.as_completed(futures):
            future.result() # ensure no exceptions
            
    wall_time = time.time() - start_time
    print(f"[OK] Stress test completed successfully.")
    print(f"Total Environments Evaluated: {len(scenarios)}")
    print(f"Total Wall Clock Time: {wall_time:.4f} seconds")
    print(f"Average Episode Latency: {(wall_time / len(scenarios)):.4f} seconds")
    
    if wall_time < 5.0:
        print("[SUCCESS] Environment processing logic is highly optimized and will not breach the 20-minute execution limit.")
    else:
        print("[WARNING] Environment logic overhead is too high.")

if __name__ == "__main__":
    main()
