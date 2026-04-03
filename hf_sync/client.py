# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

"""Api Contract Evolution Environment Client."""

from typing import Dict

from openenv.core import EnvClient
from openenv.core.client_types import StepResult
from openenv.core.env_server.types import State

from .models import ApiContractAction, ApiContractObservation


class ApiContractEvolutionEnv(
    EnvClient[ApiContractAction, ApiContractObservation, State]
):
    """
    Client for the Api Contract Evolution Environment.

    This client maintains a persistent WebSocket connection to the environment server,
    enabling efficient multi-step interactions with lower latency.
    Each client instance has its own dedicated environment session on the server.

    Example:
        >>> # Connect to a running server
        >>> with ApiContractEvolutionEnv(base_url="http://localhost:7860") as client:
        ...     result = client.reset()
        ...     print(result.observation.scenario_name)
        ...
        ...     result = client.step(ApiContractAction(action_type="identify",
        ...         changed_fields=["optional_fields"], change_category="field_added"))
        ...     print(result.observation.previous_phase_score)

    Example with Docker:
        >>> # Automatically start container and connect
        >>> client = ApiContractEvolutionEnv.from_docker_image("api_contract_evolution-env:latest")
        >>> try:
        ...     result = client.reset()
        ...     result = client.step(ApiContractAction(action_type="identify"))
        ... finally:
        ...     client.close()
    """

    def _step_payload(self, action: ApiContractAction) -> Dict:
        """
        Convert ApiContractAction to JSON payload for step message.

        Args:
            action: ApiContractAction instance

        Returns:
            Dictionary representation suitable for JSON encoding
        """
        return action.model_dump()

    def _parse_result(self, payload: Dict) -> StepResult[ApiContractObservation]:
        """
        Parse server response into StepResult[ApiContractObservation].

        Args:
            payload: JSON response data from server

        Returns:
            StepResult with ApiContractObservation
        """
        obs_data = payload.get("observation", {})
        observation = ApiContractObservation(
            scenario_id=obs_data.get("scenario_id", 1),
            scenario_name=obs_data.get("scenario_name", ""),
            difficulty=obs_data.get("difficulty", "easy"),
            current_phase=obs_data.get("current_phase", "identify"),
            phases_remaining=obs_data.get("phases_remaining", []),
            spec_v1=obs_data.get("spec_v1", {}),
            spec_v2=obs_data.get("spec_v2", {}),
            client_code=obs_data.get("client_code", {}),
            client_personas=obs_data.get("client_personas", {}),
            dependency_graph=obs_data.get("dependency_graph", {}),
            previous_phase_feedback=obs_data.get("previous_phase_feedback", ""),
            previous_phase_score=obs_data.get("previous_phase_score", 0.0),
            cumulative_score=obs_data.get("cumulative_score", 0.0),
            done=payload.get("done", False),
            reward=payload.get("reward"),
            metadata=obs_data.get("metadata", {}),
        )

        return StepResult(
            observation=observation,
            reward=payload.get("reward"),
            done=payload.get("done", False),
        )

    def _parse_state(self, payload: Dict) -> State:
        """
        Parse server response into State object.

        Args:
            payload: JSON response from state request

        Returns:
            State object with episode_id and step_count
        """
        return State(
            episode_id=payload.get("episode_id"),
            step_count=payload.get("step_count", 0),
        )
