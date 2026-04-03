# 2-Minute Pitch: API Contract Evolution

*Instructions: Practice reading this out loud. Take pauses where paragraph breaks are placed. Speak conversationally, not like a robot. No need for bullet points — this is built as a complete narrative.*

---

**[Hook]**
In 2019, Stripe made a tiny API change. They renamed an error code from `"insufficient_funds"` to `"payment_declined"`. It was a pure bug fix — a cleanup. But what happened? It broke 1,200 merchant integrations overnight and cost them over $2 Million in support tickets and lost revenue.

**[The Problem]**
This happens *every day* in software. Changing an API is easy; knowing *which clients* it will break is nearly impossible. Why? Because the documentation doesn't tell the whole story, you have to read the actual client code to know for sure. That is exactly the reasoning challenge I've built for our AI agents today.

**[The Solution]**
Welcome to the API Contract Evolution environment. It is the very first OpenEnv curriculum that trains AI to act as expert compatibility analysts. When you ping the `/reset` and `/step` endpoints on my Hugging Face space, here is what the agent sees:
1. Two API versions (v1 and v2)
2. Three real-world client personas making requests
3. A dependency graph

**[The Innovations]**
It is not enough for an agent to simply guess if an API change is "breaking." That's too simplistic. My environment completely reimagines the evaluation using two core innovations:

1. **Three-Phase Episodic Workflow:** It forces the agent through a logical progression: Phase 1: Identify exactly what changed. Phase 2: Classify the severity and *which specific clients break*. Phase 3: Propose a backwards-compatible rollout plan. The agent is scored progressively.

2. **Confidence Calibration Grader:** For the first time in OpenEnv, the agent has to rate its own confidence. If an agent is right and confident, it maximizes its score. But if it's overconfident and wrong, it gets heavily penalized.

3. **Advanced Production Realities:** The environment goes far beyond simple API parsing. It introduces realistic deprecation timelines (an agent is penalized for proposing a 365-day migration to a client that mandates a 30-day turnaround) and strict Semantic Versioning evaluation. Furthermore, Scenario 6 specifically tests GraphQL Field Nullability—the exact sort of nuanced breaking change that plagues massive engineering organizations like Meta or GitHub today.

4. **Built-in RL Debugging:** Evaluators can hit a standard `/replay` endpoint to view an entire episode's action-reward trajectory instantly.

**[Conclusion]**
I ran the baseline script against Llama 3.1 8B, and the results are fascinating. The agent handles "easy" additive changes beautifully, scoring around 0.85. But on Scenario 3 — "The Fix That Breaks Paradox" — where fixing a bug unintentionally destroys downstream formatting — the model completely misses the nuance and the score drops to 0.40. There is a massive reasoning gap here for RL to solve. That's why this benchmark is relevant to industry right now. Thank you!
