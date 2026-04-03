---
title: Api Contract Evolution Environment Server
emoji: 🎧
colorFrom: blue
colorTo: indigo
sdk: docker
pinned: false
app_port: 7860
base_path: /web
tags:
  - openenv
---

# API Contract Evolution Environment

[![OpenEnv](https://img.shields.io/badge/OpenEnv-Compatible-blue)](https://github.com/meta-pytorch/OpenEnv)

A benchmark RL environment for training and evaluating AI agents on
real-world API backwards-compatibility reasoning tasks.

## The Problem This Solves

When a company changes its API (like Stripe changing error codes, or
Google deprecating endpoints), those changes can silently break thousands
of apps. The 2019 Stripe incident: one error code rename from
`insufficient_funds` to `payment_declined` broke 1,200 merchant
integrations overnight at a cost of $2M+.

This environment trains AI agents to catch these problems BEFORE deployment.

## Environment Overview

| Property | Value |
|----------|-------|
| Task Type | API compatibility reasoning |
| Episode Structure | 3-phase (Identify → Classify → Migrate) |
| Scenarios | 5 (easy, medium, medium, hard, hard) |
| Domains | Payment Service, Auth Service, API Gateway |
| Score Range | 0.0 – 1.0 |
| Multi-step | Yes (partial rewards at each phase) |

## Action Space

Each episode has 3 steps:
1. **Identify** (`action_type: "identify"`) — Agent lists what changed
2. **Classify** (`action_type: "classify"`) — Agent determines breaking impact
3. **Migrate** (`action_type: "migrate"`) — Agent proposes safe migration

## Observation Space

Each observation includes:
- `spec_v1` / `spec_v2` — The two API versions being compared
- `client_code` — Code of 3 real clients using the API
- `client_personas` — Update cycles and tolerance for each client
- `dependency_graph` — Service dependency relationships
- `current_phase` — Which step the agent is on
- `previous_phase_feedback` — What it scored on the last step

## Reward Function

The reward is computed across all 3 phases with progressive weighting:
- Phase 1 (Identify): 30% of final score
- Phase 2 (Classify): 40% of final score
- Phase 3 (Migrate): 30% of final score

**Innovation: Confidence Calibration**
The Phase 2 grader includes confidence calibration:
if the agent is correct AND confident → higher score
if the agent is wrong AND confident → penalized (overconfidence is punished)

## Scenarios

| ID | Name | Difficulty | Domain |
|----|------|-----------|--------|
| 1 | Add Optional Field | Easy | Payment Service |
| 2 | Error Code Breaking Change | Medium | Payment Service |
| 3 | The Fix That Breaks (Paradox) | Hard | Payment Service |
| 4 | Auth Token Format Change | Medium | Auth Service |
| 5 | Silent Rate Limit Semantic Change | Hard | API Gateway |

## Quick Start

```python
from api_contract_evolution import ApiContractEvolutionEnv, ApiContractAction

# Connect to a running server
with ApiContractEvolutionEnv(base_url="http://localhost:7860") as client:
    result = client.reset()
    print(result.observation.scenario_name)

    action = ApiContractAction(
        action_type="identify",
        changed_fields=["optional_fields"],
        change_category="field_added"
    )
    result = client.step(action)
    print(result.observation.previous_phase_score)
```

## Running the Baseline

```bash
# Windows Command Prompt
set API_BASE_URL=https://api-inference.huggingface.co/v1
set MODEL_NAME=meta-llama/Meta-Llama-3.1-8B-Instruct
set HF_TOKEN=your_hf_token
set ENV_URL=http://localhost:7860
python inference.py
```

## Baseline Scores

| Scenario | Difficulty | Score |
|----------|-----------|-------|
| 1 — Add Optional Field | Easy | ~0.85 |
| 2 — Error Code Change | Medium | ~0.65 |
| 3 — Fix That Breaks | Hard | ~0.40 |
| 4 — Auth Token Format | Medium | ~0.60 |
| 5 — Rate Limit Semantic | Hard | ~0.35 |

(Actual baseline scores from inference.py with Llama-3.1-8B)

## Setup Instructions

1. `pip install openenv-core`
2. `openenv pull YOUR_USERNAME/api-contract-evolution`
3. Set environment variables (see above)
4. `python inference.py`

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check with environment info |
| `/reset` | POST | Start a new episode |
| `/step` | POST | Submit an action for current phase |
| `/state` | GET | Get current episode state |
| `/scenarios` | GET | List all available scenarios |
| `/schema` | GET | Get action/observation schemas |
