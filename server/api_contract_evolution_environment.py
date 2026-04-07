# server/api_contract_evolution_environment.py
# Main environment logic — implements reset(), step(), state

from uuid import uuid4

from openenv.core.env_server.interfaces import Environment
from openenv.core.env_server.types import State

try:
    from ..models import ApiContractAction, ApiContractObservation, ApiContractState
except ImportError:
    from models import ApiContractAction, ApiContractObservation, ApiContractState

from .scenarios import SCENARIOS
from .graders import (
    grade_phase_1_identify,
    grade_phase_2_classify,
    grade_phase_3_migrate,
    compute_episode_score,
)
from typing import Dict, Any


PHASE_ORDER = ["identify", "classify", "migrate"]


class ApiContractEvolutionEnvironment(Environment):
    """
    API Contract Evolution Environment

    An RL training environment where agents learn to detect API breaking
    changes through a 3-phase episodic task:
      Phase 1: Identify what changed between API versions
      Phase 2: Classify whether the change is breaking and who is affected
      Phase 3: Propose a safe migration plan

    Supports 6 scenarios across 4 real-world domains:
      - Payment Service (scenarios 1-3)
      - Auth Service (scenario 4)
      - API Gateway (scenario 5)
      - E-Commerce (GraphQL) (scenario 6)
    """

    # Enable concurrent WebSocket sessions.
    SUPPORTS_CONCURRENT_SESSIONS: bool = False

    def __init__(self):
        self._scenario_id = 1
        self._current_phase_index = 0
        self._phase_scores = {}
        self._step_count = 0
        self._is_done = False
        self._action_history = []
        self._state = State(episode_id=str(uuid4()), step_count=0)

    def reset(self, scenario_id: int = 1, **kwargs) -> ApiContractObservation:
        """
        Start a new episode with the given scenario.
        Returns initial observation (the API specs for the agent to analyze).
        """
        # Support scenario_id passed via JSON body (unpacked into kwargs)
        if "scenario_id" in kwargs:
            try:
                scenario_id = int(kwargs["scenario_id"])
            except (ValueError, TypeError):
                pass

        # Validate scenario_id
        if scenario_id not in SCENARIOS:
            scenario_id = 1

        # Reset all state
        self._scenario_id = scenario_id
        self._current_phase_index = 0
        self._phase_scores = {}
        self._step_count = 0
        self._is_done = False
        self._action_history = []
        self._state = State(episode_id=str(uuid4()), step_count=0)

        scenario = SCENARIOS[self._scenario_id]
        current_phase = PHASE_ORDER[self._current_phase_index]
        remaining = PHASE_ORDER[self._current_phase_index :]

        return ApiContractObservation(
            done=False,
            reward=0.001,
            scenario_id=self._scenario_id,
            scenario_name=scenario["name"],
            difficulty=scenario["difficulty"],
            deprecation_window_days=scenario.get("deprecation_window_days", 0),
            current_phase=current_phase,
            phases_remaining=remaining,
            spec_v1=scenario["spec_v1"],
            spec_v2=scenario["spec_v2"],
            client_code=scenario["client_code"],
            client_personas=scenario["client_personas"],
            dependency_graph=scenario["dependency_graph"],
            previous_phase_feedback="",
            previous_phase_score=0.001,
            cumulative_score=0.001,
        )

    def step(self, action: ApiContractAction) -> ApiContractObservation:  # type: ignore[override]
        """
        Process the agent's action for the current phase.
        Returns observation with reward and feedback.
        """
        if self._is_done:
            scenario = SCENARIOS[self._scenario_id]
            return ApiContractObservation(
                done=True,
                reward=0.001,
                scenario_id=self._scenario_id,
                scenario_name=scenario["name"],
                difficulty=scenario["difficulty"],
                deprecation_window_days=scenario.get("deprecation_window_days", 0),
                current_phase="done",
                phases_remaining=[],
                spec_v1=scenario["spec_v1"],
                spec_v2=scenario["spec_v2"],
                client_code=scenario["client_code"],
                client_personas=scenario["client_personas"],
                dependency_graph=scenario["dependency_graph"],
                previous_phase_feedback="Episode already finished.",
                previous_phase_score=0.001,
                cumulative_score=compute_episode_score(self._phase_scores),
            )

        self._step_count += 1
        self._state.step_count = self._step_count
        scenario = SCENARIOS[self._scenario_id]
        ground_truth = scenario["ground_truth"]
        current_phase = PHASE_ORDER[self._current_phase_index]
        action_dict = action.model_dump()

        # Grade the current phase
        if current_phase == "identify":
            grade_result = grade_phase_1_identify(action_dict, ground_truth)
        elif current_phase == "classify":
            grade_result = grade_phase_2_classify(action_dict, ground_truth)
        else:
            grade_result = grade_phase_3_migrate(action_dict, ground_truth)

        phase_score = grade_result["score"]
        self._phase_scores[current_phase] = phase_score
        self._action_history.append(
            {
                "phase": current_phase,
                "action": action_dict,
                "score": phase_score,
                "feedback": grade_result,
            }
        )

        # Generate human-readable feedback
        feedback = self._make_feedback(current_phase, grade_result, ground_truth)

        # Move to next phase
        self._current_phase_index += 1
        is_done = self._current_phase_index >= len(PHASE_ORDER)
        self._is_done = is_done

        if is_done:
            next_phase = "done"
            remaining = []
            final_score = compute_episode_score(self._phase_scores)
        else:
            next_phase = PHASE_ORDER[self._current_phase_index]
            remaining = PHASE_ORDER[self._current_phase_index :]
            final_score = phase_score  # Partial reward for this phase

        cumulative = (
            compute_episode_score(self._phase_scores)
            if is_done
            else (sum(self._phase_scores.values()) / len(PHASE_ORDER))
        )

        return ApiContractObservation(
            done=is_done,
            reward=final_score if is_done else phase_score,
            scenario_id=self._scenario_id,
            scenario_name=scenario["name"],
            difficulty=scenario["difficulty"],
            deprecation_window_days=scenario.get("deprecation_window_days", 0),
            current_phase=next_phase,
            phases_remaining=remaining,
            spec_v1=scenario["spec_v1"],
            spec_v2=scenario["spec_v2"],
            client_code=scenario["client_code"],
            client_personas=scenario["client_personas"],
            dependency_graph=scenario["dependency_graph"],
            previous_phase_feedback=feedback,
            previous_phase_score=phase_score,
            cumulative_score=round(cumulative, 4),
            metadata={"phase_scores": self._phase_scores, "grade_detail": grade_result},
        )

    @property
    def state(self) -> ApiContractState:
        """Return current episode state."""
        current_phase = (
            PHASE_ORDER[self._current_phase_index]
            if self._current_phase_index < len(PHASE_ORDER)
            else "done"
        )
        return ApiContractState(
            episode_id=self._state.episode_id,
            step_count=self._state.step_count,
            scenario_id=self._scenario_id,
            scenario_name=SCENARIOS[self._scenario_id]["name"],
            difficulty=SCENARIOS[self._scenario_id]["difficulty"],
            current_phase=current_phase,
            total_score=compute_episode_score(self._phase_scores),
            phase_scores=self._phase_scores,
            is_done=self._is_done,
        )

    def _make_feedback(self, phase: str, grade: Dict, ground_truth: Dict) -> str:
        """Generate helpful feedback text for the agent after each phase."""
        score = grade["score"]
        lines = [f"Phase '{phase}' score: {score:.2f}/1.00"]

        if phase == "identify":
            if grade["field_score"] < 0.5:
                lines.append(f"  - You identified: {grade['agent_fields']}")
                lines.append(f"  - Actual changes: {grade['true_fields']}")
            if grade["category_score"] == 0.0:
                lines.append(f"  - You said category: '{grade['agent_category']}'")
                lines.append(f"  - Correct category: '{grade['true_category']}'")

        elif phase == "classify":
            if not grade["is_correct"]:
                lines.append(f"  - You said breaking: {grade['agent_said_breaking']}")
                lines.append(f"  - Actually breaking: {grade['truth_is_breaking']}")
            missing_clients = set(grade["true_affected"]) - set(grade["agent_affected"])
            false_clients = set(grade["agent_affected"]) - set(grade["true_affected"])
            if missing_clients:
                lines.append(f"  - Missed affected clients: {list(missing_clients)}")
            if false_clients:
                lines.append(f"  - Incorrectly flagged: {list(false_clients)}")

        elif phase == "migrate":
            if grade["keywords_missing"]:
                lines.append(
                    f"  - Missing migration concepts: {grade['keywords_missing'][:3]}"
                )
            if not grade["has_rollback"]:
                lines.append("  - No rollback plan provided")
            if not grade["has_risks"]:
                lines.append("  - No risks identified")

        return "\n".join(lines)
