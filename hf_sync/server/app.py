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


# Create the app with web interface and README integration
app = create_app(
    ApiContractEvolutionEnvironment,
    ApiContractAction,
    ApiContractObservation,
    env_name="api_contract_evolution",
    max_concurrent_envs=1,  # increase this number to allow more concurrent WebSocket sessions
)


# ─── BONUS ENDPOINTS (Section 6) ───────────────────────────────────────

from .scenarios import SCENARIOS


@app.get("/scenarios")
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


@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "environment": "api-contract-evolution",
        "version": "1.0.0",
        "scenarios_available": len(SCENARIOS),
        "phases_per_episode": 3,
        "domains": ["Payment Service", "Auth Service", "API Gateway"]
    }


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
