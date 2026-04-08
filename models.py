# models.py — Defines what the agent sends and receives
# Adapted to use the actual openenv package imports

from openenv.core.env_server.types import Action, Observation, State
from pydantic import Field
from typing import List, Dict, Optional, Any


# ─── WHAT THE AGENT SENDS TO /step ──────────────────────────────────────





class ApiContractAction(Action):
    """
    The action an AI agent takes when analyzing an API change.

    PHASE 1 (identify):   Agent lists what changed between v1 and v2
    PHASE 2 (classify):   Agent says if it is breaking + which clients break
    PHASE 3 (migrate):    Agent proposes how to safely migrate
    """

    # Which phase of analysis is this?
    action_type: str = Field(
        default="identify", description="One of: identify | classify | migrate"
    )

    # Phase 1: Identify
    changed_fields: List[str] = Field(
        default_factory=list, description="List of fields/endpoints that changed"
    )
    change_category: str = Field(
        default="",
        description="Type of change: field_added | field_removed | type_changed | error_code_changed | behavior_changed",
    )

    # Phase 2: Classify
    is_breaking: Optional[bool] = Field(
        default=None, description="True if this change breaks existing clients"
    )
    affected_clients: List[str] = Field(
        default_factory=list, description="Names of clients that will break"
    )
    severity: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Severity of break: 0.0 (none) to 1.0 (catastrophic)",
    )
    confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="How confident the agent is in its analysis",
    )
    reason: str = Field(
        default="", description="Explanation of why this is or is not breaking"
    )

    # Phase 3: Migrate
    migration_steps: List[str] = Field(
        default_factory=list, description="Ordered list of migration steps"
    )
    migration_timeline_days: int = Field(
        default=30, description="How many days migration will take"
    )
    migration_risks: List[str] = Field(
        default_factory=list, description="Risks if migration goes wrong"
    )
    rollback_plan: str = Field(
        default="", description="How to undo the change if something breaks"
    )
    backwards_compatible_alternative: str = Field(
        default="", description="A way to make the change without breaking clients"
    )


# ─── WHAT THE AGENT RECEIVES FROM /reset AND /step ───────────────────────


class ApiContractObservation(Observation):
    """
    What the agent sees at each step.
    Contains the API specs, client code, and current phase info.
    """

    # Scenario metadata
    scenario_id: int = Field(default=1)
    scenario_name: str = Field(default="")
    difficulty: str = Field(default="easy")
    deprecation_window_days: int = Field(default=0, description="Real-world deadline before clients must migrate")
    current_phase: str = Field(default="identify")
    phases_remaining: List[str] = Field(default_factory=list)

    # The core data the agent analyzes
    spec_v1: Dict[str, Any] = Field(default_factory=dict)
    spec_v2: Dict[str, Any] = Field(default_factory=dict)
    client_code: Dict[str, str] = Field(default_factory=dict)
    client_personas: Dict[str, Any] = Field(default_factory=dict)
    dependency_graph: Dict[str, Any] = Field(default_factory=dict)

    # Feedback from previous step (empty on first step)
    previous_phase_feedback: str = Field(default="")
    previous_phase_score: float = Field(default=0.01)

    # Running total
    cumulative_score: float = Field(default=0.01)

    # done and reward come from the base Observation class


# ─── ENVIRONMENT STATE (what /state returns) ─────────────────────────────


class ApiContractState(State):
    """
    Current state of the environment episode.
    """

    scenario_id: int = Field(default=1)
    scenario_name: str = Field(default="")
    difficulty: str = Field(default="easy")
    current_phase: str = Field(default="identify")
    step_count: int = Field(default=0)
    total_score: float = Field(default=0.01)  # Never 0.0 — validator rejects exact 0.0
    phase_scores: Dict[str, float] = Field(default_factory=dict)
    is_done: bool = Field(default=False)
