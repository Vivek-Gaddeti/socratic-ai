import asyncio

from agents.orchestrator import _offline_score, route_after_evaluation, run_socratic_session
from config import MASTERY_THRESHOLD


def run(**kwargs):
    defaults = dict(conversation_history=[], document_ids=[], current_topic="Gradient Descent", next_topic="Regularization")
    defaults.update(kwargs)
    return asyncio.run(run_socratic_session(**defaults))


def test_first_message_is_not_graded():
    out = run(user_message="I want to learn gradient descent")
    assert out["evaluation_score"] == -1
    assert [t["agent"] for t in out["agent_trace"]] == ["knowledge", "evaluator", "socrates"]


def test_answer_is_graded_after_a_tutor_question():
    history = [{"role": "assistant", "content": "What does the learning rate control?"}]
    out = run(user_message="It controls how big each update step is when we move against the gradient of the loss",
              conversation_history=history)
    assert 0 <= out["evaluation_score"] <= 100


def test_asking_for_help_routes_to_hint_agent():
    history = [{"role": "assistant", "content": "What does the learning rate control?"}]
    out = run(user_message="I'm stuck, can I get a hint", conversation_history=history)
    assert out["agent_used"].startswith("hint")
    assert out["hint_level"] == 1


def test_repeated_low_scores_route_to_hint():
    state = {"user_message": "no", "evaluation_score": 20, "consecutive_low_scores": 2}
    assert route_after_evaluation(state) == "hint"
    state["evaluation_score"] = 70
    assert route_after_evaluation(state) == "socrates"


def test_offline_score_rewards_textbook_vocabulary():
    context = [{"content": "The learning rate controls the step size of gradient descent updates."}]
    weak = _offline_score("not sure", context)
    strong = _offline_score("The learning rate controls the step size of each gradient descent update", context)
    assert strong > weak
    assert strong >= MASTERY_THRESHOLD  # a fully on-topic answer can reach the threshold offline


def test_gemini_errors_get_plain_reasons():
    from llm import describe_llm_error

    assert "quota" in describe_llm_error(Exception("429 RESOURCE_EXHAUSTED. You exceeded your current quota"))
    assert "overloaded" in describe_llm_error(Exception("503 UNAVAILABLE"))
    assert describe_llm_error(Exception("boom")) == "Gemini call failed"
