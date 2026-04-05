# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

"""
FastAPI application for the Api Contract Evolution Environment.

This module creates an HTTP server that exposes the ApiContractEvolutionEnvironment
over HTTP and WebSocket endpoints, compatible with EnvClient.

Endpoints:
    - POST /reset: Reset the environment
    - POST /step: Execute an action
    - GET /state: Get current environment state
    - GET /schema: Get action/observation schemas
    - WS /ws: WebSocket endpoint for persistent sessions

Usage:
    # Development (with auto-reload):
    uvicorn server.app:app --reload --host 0.0.0.0 --port 7860

    # Production:
    uvicorn server.app:app --host 0.0.0.0 --port 7860 --workers 4

    # Or run directly:
    python -m server.app
"""

try:
    from openenv.core.env_server.http_server import create_app
except Exception as e:  # pragma: no cover
    raise ImportError(
        "openenv is required for the web interface. Install dependencies with '\n    uv sync\n'"
    ) from e

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

try:
    from models import ApiContractAction, ApiContractObservation
    from server.api_contract_evolution_environment import ApiContractEvolutionEnvironment
except ImportError:
    # Fallback if somehow installed as a package
    from ..models import ApiContractAction, ApiContractObservation
    from .api_contract_evolution_environment import ApiContractEvolutionEnvironment


# Create a single global instance for the environment
global_env = ApiContractEvolutionEnvironment()

# Create the app with web interface and README integration
app = create_app(
    lambda: global_env,
    ApiContractAction,
    ApiContractObservation,
    env_name="api_contract_evolution",
    max_concurrent_envs=1,
)

# ─── OVERRIDE DEFAULT ROUTES TO MATCH TESTING CRITERIA ────────────────

# Define custom routes on a router to ensure they taking precedence
from fastapi import APIRouter
custom_router = APIRouter()

@custom_router.post("/reset")
def reset_env(scenario_id: int = 1):
    """Reset the environment with a specific scenario_id and return a flat JSON."""
    obs = global_env.reset(scenario_id=scenario_id)
    return obs.model_dump()

@custom_router.post("/step")
def step_env(action: ApiContractAction):
    """Execute a step and return a flat JSON (unwrapped from 'observation')."""
    obs = global_env.step(action)
    return obs.model_dump()


# ─── BONUS ENDPOINTS (Section 6) ───────────────────────────────────────

from .scenarios import SCENARIOS
from .graders import compute_episode_score

@custom_router.get("/replay")
def replay_episode():
    """Return the full action-reward history of the current episode.
    Standard RL debugging tool for evaluators."""
    return {
        "episode_id": global_env._state.episode_id,
        "scenario_id": global_env._scenario_id,
        "step_count": global_env._step_count,
        "is_done": global_env._is_done,
        "phase_scores": global_env._phase_scores,
        "action_history": global_env._action_history,
        "total_score": compute_episode_score(global_env._phase_scores)
    }


@custom_router.get("/scenarios")
def list_scenarios():
    """List all available scenarios with metadata."""
    return {
        "total": len(SCENARIOS),
        "scenarios": [
            {
                "id": s["id"],
                "name": s["name"],
                "difficulty": s["difficulty"],
                "domain": s["domain"],
                "description": s["description"][:100] + "..."
            }
            for s in SCENARIOS.values()
        ]
    }


@custom_router.get("/health")
def health_check():
    """Verbose health check matching Phase 1: Step 1.2 criteria."""
    return {
        "status": "ok",
        "environment": "api-contract-evolution",
        "version": "1.0.0",
        "scenarios_available": len(SCENARIOS),
        "phases_per_episode": 3,
        "domains": ["Payment Service", "Auth Service", "API Gateway", "E-Commerce (GraphQL)"]
    }

# Include the custom router
app.include_router(custom_router)

# Forced override: Purge OpenEnv's default routes that collide with ours
custom_paths = {r.path for r in custom_router.routes if hasattr(r, "path")}
new_routes = []
seen_custom = set()

# We want our custom routes to be at the very front
for route in app.router.routes:
    path = getattr(route, "path", None)
    if path in custom_paths:
        # If this is one of our custom routes and we haven't added it yet, put it at the front
        if hasattr(route, "name") and route.name in ["reset_env", "step_env", "health_check", "replay_episode", "list_scenarios"]:
            if path not in seen_custom:
                new_routes.insert(0, route)
                seen_custom.add(path)
        # Else it's a default route for a path we've overridden, so skip it
        continue
    new_routes.append(route)

app.router.routes = new_routes


def main(host: str = "0.0.0.0", port: int = 7860):
    """
    Entry point for direct execution via uv run or python -m.

    This function enables running the server without Docker:
        uv run --project . server
        uv run --project . server --port 7860
        python -m api_contract_evolution.server.app

    Args:
        host: Host address to bind to (default: "0.0.0.0")
        port: Port number to listen on (default: 7860)

    For production deployments, consider using uvicorn directly with
    multiple workers:
        uvicorn api_contract_evolution.server.app:app --workers 4
    """
    import uvicorn

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
