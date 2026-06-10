"""Diagnose whether a tau2 telecom pass is genuine: run ONE episode, dump the
full transcript + which goal-actions actually fired + the reward.

    set -a && source .env && set +a
    PYTHONPATH=src .venv-tau2-eval/bin/python scripts/tau2_diag_episode.py
"""

from __future__ import annotations

import json

from loguru import logger

logger.remove()

from tau2.agent.llm_agent import LLMAgent
from tau2.orchestrator.orchestrator import Orchestrator
from tau2.registry import registry
from tau2.runner.simulation import run_simulation
from tau2.user.user_simulator import UserSimulator

LLM = "deepseek/deepseek-chat"
ARGS = {"temperature": 0.0, "num_retries": 2, "timeout": 120}


def main() -> None:
    tasks = list(registry.get_tasks_loader("telecom")())
    task = next(t for t in tasks if "mms_issue" in t.id and "PERSONA:Hard" in t.id)
    print("TASK:", task.id)
    required = {
        f"{a.name}({json.dumps(a.arguments, sort_keys=True)})"
        for a in (task.evaluation_criteria.actions or [])
    }
    print("REQUIRED goal-actions:", required)
    print("ENV_ASSERTIONS:", task.evaluation_criteria.env_assertions)
    print("=" * 70)

    env = registry.get_env_constructor("telecom")(solo_mode=False)
    user_tools = env.get_user_tools(include=task.user_tools) or None
    agent = LLMAgent(tools=env.get_tools(), domain_policy=env.get_policy(), llm=LLM, llm_args=dict(ARGS))
    user = UserSimulator(tools=user_tools, instructions=task.user_scenario, llm=LLM, llm_args=dict(ARGS))
    orch = Orchestrator(domain="telecom", agent=agent, user=user, environment=env, task=task, max_steps=200)
    sim = run_simulation(orch)

    fired: list[str] = []
    for m in sim.messages:
        role = getattr(m, "role", "?")
        content = (getattr(m, "content", "") or "")[:140].replace("\n", " ")
        tcs = getattr(m, "tool_calls", None) or []
        calls = []
        for tc in tcs:
            fn = getattr(tc, "name", None) or getattr(getattr(tc, "function", None), "name", "?")
            args = getattr(tc, "arguments", None) or getattr(getattr(tc, "function", None), "arguments", "")
            calls.append(f"{fn}({args})")
            fired.append(f"{fn}({args})")
        line = f"[{role}] {content}"
        if calls:
            line += "  >> " + " | ".join(calls)
        print(line)

    print("=" * 70)
    ri = getattr(sim, "reward_info", None)
    print("REWARD:", getattr(ri, "reward", None), "breakdown:", getattr(ri, "reward_breakdown", None))
    print("num_messages:", len(sim.messages))
    # did the 3 required corrective actions actually fire?
    for need in ("toggle_airplane_mode", "grant_app_permission"):
        hits = [c for c in fired if need in c]
        print(f"  fired {need}: {hits}")


if __name__ == "__main__":
    main()
