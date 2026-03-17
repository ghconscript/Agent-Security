from datetime import datetime

import pytest
from langchain.agents import AgentType

from agent.agent import run_agent
from baserun import Baserun


@pytest.fixture
def user_input():
    return (
        f"Who won the 2022 Nobel Prize in Physics? It is the year {datetime.utcnow().year} and the award has "
        f"already been handed out."
    )


def test_openai_non_streaming(user_input):
    Baserun.init()
    result = run_agent(user_input=user_input, provider="openai", use_streaming=False)
    Baserun.evals.includes("2022 Nobel Prize winner", result, ["Zeilinger"])
    assert "Zeilinger" in result


def test_openai_tools(user_input):
    Baserun.init()
    result = run_agent(
        user_input=user_input, provider="openai", use_streaming=False, agent_type=AgentType.OPENAI_MULTI_FUNCTIONS
    )
    Baserun.evals.includes("2022 Nobel Prize winner", result, ["Zeilinger"])
    assert "Zeilinger" in result


def test_openai_streaming(user_input):
    Baserun.init()
    result = run_agent(user_input=user_input, provider="openai", use_streaming=True)
    Baserun.evals.includes("2022 Nobel Prize winner", result, ["Zeilinger"])
    assert "Zeilinger" in result


def test_anthropic(user_input):
    Baserun.init()
    result = run_agent(user_input=user_input, provider="anthropic")
    Baserun.evals.includes("2022 Nobel Prize winner", result, ["Zeilinger"])
    assert "Zeilinger" in result
