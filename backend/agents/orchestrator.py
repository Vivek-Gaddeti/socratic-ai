"""
Multi-agent Socratic tutor built as a LangGraph state machine.

    knowledge -> evaluator -> (route) -> socrates -> END
                                     `-> hint -----> END

knowledge  retrieves textbook passages for the current topic from FAISS (RAG)
evaluator  scores the student's last answer 0-100 with Gemini 2.5 Flash
socrates   the teaching agent: asks the next guiding question; when the score
           reaches MASTERY_THRESHOLD it introduces the next curriculum topic
hint       gives graduated hints (level 1-3) when the student is stuck
"""
import json
import logging
import re
from typing import Optional, TypedDict

from langchain.schema import HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph

from config import MASTERY_THRESHOLD
from llm import describe_llm_error, get_llms
from rag.pipeline import retrieve_context

log = logging.getLogger("socratic.agents")


class AgentState(TypedDict):
    user_message: str
    conversation_history: list[dict]
    document_ids: list[str]
    current_topic: str
    next_topic: Optional[str]
    retrieved_context: list[dict]
    evaluation_score: float
    evaluation_feedback: dict
    consecutive_low_scores: int
    hint_level: int
    final_response: str
    agent_used: str
    mastery_achieved: bool
    agent_trace: list[dict]
    llm_error: Optional[str]


STOP_WORDS = {
    "the", "is", "at", "which", "on", "and", "a", "an", "i", "think", "what", "how", "why", "when",
    "it", "to", "of", "in", "for", "with", "that", "this", "can", "be", "do", "does", "by", "as", "or",
    "from", "are", "we", "you", "my", "about", "so", "they", "their", "there", "then", "than", "into",
    "will", "would", "should", "could", "also", "just", "like", "because", "each", "some", "more",
}
HELP_PHRASES = ("hint", "i don't know", "i dont know", "no idea", "i'm stuck", "im stuck", "help me", "not sure")
DIRECT_QUESTION_STARTS = ("what", "how", "why", "when", "can you", "explain", "tell me", "define", "show me", "which", "where", "teach me")


def key_terms(text: str) -> list[str]:
    words = [w.strip(".,!?;:()[]\"'*") for w in text.lower().split()]
    return [w for w in words if len(w) > 3 and w not in STOP_WORDS]


def _trace(state: AgentState, agent: str, detail: str) -> None:
    state["agent_trace"] = state.get("agent_trace", []) + [{"agent": agent, "detail": detail}]


def _asks_for_help(message: str) -> bool:
    lower = message.lower()
    return any(p in lower for p in HELP_PHRASES)


def _is_direct_question(message: str) -> bool:
    lower = message.strip().lower()
    return (lower.endswith("?") or lower.startswith(DIRECT_QUESTION_STARTS)) and len(message.split()) < 30


# ─────────────────────────────────────────────
# AGENT 1: KNOWLEDGE — retrieve textbook passages (RAG)
# ─────────────────────────────────────────────
def knowledge_agent(state: AgentState) -> AgentState:
    if not state.get("document_ids"):
        state["retrieved_context"] = []
        _trace(state, "knowledge", "No document selected, so nothing to retrieve")
        return state

    topic = state.get("current_topic") or ""
    query = f"{topic}: {state['user_message']}" if topic else state["user_message"]
    chunks = retrieve_context(query, state["document_ids"], k=4)
    state["retrieved_context"] = chunks
    pages = sorted({c["page"] for c in chunks})
    detail = f"Retrieved {len(chunks)} passages (pages {', '.join(map(str, pages))})" if chunks else "No matching passages found"
    _trace(state, "knowledge", detail)
    return state


# ─────────────────────────────────────────────
# AGENT 2: EVALUATOR — score the student's answer 0-100
# ─────────────────────────────────────────────
def _offline_score(answer: str, context: list[dict]) -> float:
    """Rough score without an LLM: answer length plus overlap with textbook vocabulary."""
    words = len(answer.split())
    base = 30 if words < 5 else 45 if words < 10 else 55
    student = set(key_terms(answer))
    textbook = set(key_terms(" ".join(c["content"] for c in context)))
    if not student or not textbook:
        return float(base)
    overlap = len(student & textbook) / min(len(student), 12)
    return float(min(95, round(base + 40 * min(overlap, 1.0))))


def evaluator_agent(state: AgentState) -> AgentState:
    state["evaluation_score"] = -1
    state["mastery_achieved"] = False
    history = state["conversation_history"]
    message = state["user_message"]

    last_question = next((m["content"] for m in reversed(history[:-1]) if m["role"] == "assistant"), "")
    if not last_question:
        _trace(state, "evaluator", "First message: nothing to grade yet")
        return state
    if _is_direct_question(message) or _asks_for_help(message):
        _trace(state, "evaluator", "Student asked a question, so no answer to grade")
        return state

    topic = state.get("current_topic") or "the topic under discussion"
    context_str = "\n".join(c["content"] for c in state["retrieved_context"])
    eval_prompt = f"""You are an expert educational evaluator. Score how well the student's answer shows understanding of: {topic}

TEXTBOOK CONTEXT:
{context_str[:2000]}

TUTOR'S QUESTION:
{last_question}

STUDENT'S ANSWER:
{message}

Scale:
- 0-30: wrong or off track
- 31-60: partial understanding, key ideas missing
- 61-84: good understanding, some gaps
- 85-100: accurate and complete; ready to move to the next topic

Respond ONLY with JSON. Keep each text field to one short sentence, addressed to the student ("You ...").
{{"score": <0-100>, "what_they_got_right": "...", "what_is_missing": "..."}}"""

    _, eval_llm = get_llms()
    feedback, source = {}, "offline estimate"
    if eval_llm:
        try:
            response = eval_llm.invoke([HumanMessage(content=eval_prompt)])
            match = re.search(r"\{.*\}", response.content, re.DOTALL)
            if match:
                feedback = json.loads(match.group())
                state["evaluation_score"] = max(0.0, min(100.0, float(feedback.get("score", 50))))
                source = "Gemini 2.5 Flash"
        except Exception as e:
            log.warning("Evaluator: Gemini call failed: %s", e)
            feedback = {}
            source = f"offline estimate; {describe_llm_error(e)}"
    if state["evaluation_score"] < 0:
        state["evaluation_score"] = _offline_score(message, state["retrieved_context"])

    score = state["evaluation_score"]
    state["evaluation_feedback"] = {
        "got_right": feedback.get("what_they_got_right", ""),
        "missing": feedback.get("what_is_missing", ""),
    }
    state["consecutive_low_scores"] = state.get("consecutive_low_scores", 0) + 1 if score < 50 else 0
    state["mastery_achieved"] = score >= MASTERY_THRESHOLD
    verdict = "mastered" if state["mastery_achieved"] else f"needs {MASTERY_THRESHOLD}% to advance"
    _trace(state, "evaluator", f"Scored {score:.0f}/100 ({source}): {verdict}")
    return state


# ─────────────────────────────────────────────
# AGENT 3: SOCRATES — the teaching agent
# ─────────────────────────────────────────────
def _offline_socratic_reply(state: AgentState) -> str:
    topic = state.get("current_topic") or "this concept"
    terms = key_terms(state["user_message"])
    term = terms[0] if terms else topic
    turn = len(state.get("conversation_history", [])) // 2
    snippet = ""
    for c in state.get("retrieved_context", []):
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", c["content"]) if len(s.strip()) > 40]
        if sentences:
            snippet = sentences[0][:160]
            break

    if state.get("mastery_achieved"):
        nxt = state.get("next_topic")
        if nxt:
            return f"Excellent, that shows real understanding of **{topic}**. Let's move on to **{nxt}**. Before I explain anything: what do you already know or guess about {nxt}?"
        return f"Excellent work. You've now mastered every topic in this document, including **{topic}**. Which idea would you like to revisit or connect together?"

    prompts = [
        f"Let's look at **{topic}** from first principles. What is the step-by-step mechanism behind it, in your own words?",
        f"You mentioned **{term}**. What would change if that assumption didn't hold? Where would the reasoning break?",
        f"Try explaining **{topic}** to a friend with no technical background, using an everyday analogy. What would you compare it to, and why?",
        f"Suppose someone said we could skip **{term}** entirely. What specific problem would that cause?",
    ]
    reply = prompts[turn % len(prompts)]
    if snippet:
        reply = f"The textbook says: *\"{snippet}\"*\n\n{reply}"
    return reply + "\n\n_(Offline mode: add a Gemini API key for full AI tutoring.)_"


def socrates_agent(state: AgentState) -> AgentState:
    chat_llm, _ = get_llms()
    if not chat_llm:
        state["final_response"] = _offline_socratic_reply(state)
        state["agent_used"] = "socrates_local"
        _trace(state, "socrates", "Offline question template")
        return state

    topic = state.get("current_topic") or "the student's chosen topic"
    next_topic = state.get("next_topic")
    score = state.get("evaluation_score", -1)
    feedback = state.get("evaluation_feedback") or {}
    context_str = "\n\n".join(f"[Page {c['page']}]: {c['content']}" for c in state["retrieved_context"])
    history_str = "".join(
        f"{'Student' if m['role'] == 'user' else 'SocraticAI'}: {m['content']}\n\n"
        for m in state["conversation_history"][-6:]
    )

    if state.get("mastery_achieved"):
        if next_topic:
            instruction = (f"The student has mastered '{topic}' (score {score:.0f}). Congratulate them briefly, "
                           f"confirm the key insight in one or two sentences, then introduce the NEXT topic, '{next_topic}', "
                           f"with one opening question that checks what they already know about it.")
        else:
            instruction = (f"The student has mastered '{topic}', the last topic in this document. Congratulate them, "
                           f"summarise what they have learned, and ask one question that connects the topics together.")
    elif score >= 60:
        instruction = "The student is on the right track. Acknowledge what they got right, then ask a deeper follow-up question. Don't reveal the full answer."
    elif score >= 30:
        instruction = "The student has partial understanding. Acknowledge what's right, then ask a question that points toward the missing piece. Use an analogy."
    elif score >= 0:
        instruction = "The student seems confused. Go back to a simpler, more foundational question and break the idea down with an everyday analogy."
    else:
        instruction = "The student asked a question or just started. Answer briefly from the textbook context, then ask one Socratic question to check understanding."

    system_prompt = f"""You are SocraticAI, a patient tutor that teaches through questions.

CURRENT TOPIC: {topic}

RULES:
1. If the student asks a direct question, answer it clearly using the TEXTBOOK CONTEXT (cite page numbers like "(p. 4)"), then end with ONE question that checks understanding.
2. If the student is answering, don't hand them the answer. Praise what's right, point out what's missing, and guide them with ONE question.
3. Stay on the current topic unless told to move on. Prefer facts from the textbook context.
4. Be warm and concise (under 180 words). Use Markdown for emphasis and lists.

THIS TURN: {instruction}
EVALUATOR NOTES: got right: {feedback.get('got_right') or 'n/a'}; missing: {feedback.get('missing') or 'n/a'}
SCORE ON LAST ANSWER: {f'{score:.0f}/100' if score >= 0 else 'n/a'}

TEXTBOOK CONTEXT:
{context_str[:3000] or '(no document selected)'}"""

    try:
        response = chat_llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"Conversation so far:\n{history_str}\nLatest student message: {state['user_message']}\n\nRespond as SocraticAI:"),
        ])
        state["final_response"] = response.content
        state["agent_used"] = "socrates_gemini"
        _trace(state, "socrates", "Introduced the next topic" if state.get("mastery_achieved") and next_topic else "Asked a guiding question (Gemini 2.5 Flash)")
    except Exception as e:
        log.warning("Tutor: Gemini call failed: %s", e)
        state["final_response"] = _offline_socratic_reply(state)
        state["agent_used"] = "socrates_local"
        _trace(state, "socrates", f"{describe_llm_error(e)}, so used offline template")
    return state


# ─────────────────────────────────────────────
# AGENT 4: HINT — graduated hints when the student is stuck
# ─────────────────────────────────────────────
HINT_LEVELS = {
    1: "Give a broad, gentle hint: just a direction to think in. Don't reveal key terms. End with an encouraging question.",
    2: "Give a medium hint: name the key principle (not the answer) and use an analogy. End with a guiding question.",
    3: "Give a strong hint: nearly reveal the answer but phrase it as a question, e.g. 'What if I told you that ...?'",
}


def hint_agent(state: AgentState) -> AgentState:
    level = min(state.get("hint_level", 0) + 1, 3)
    state["hint_level"] = level
    topic = state.get("current_topic") or "the current topic"
    context_str = "\n".join(c["content"] for c in state["retrieved_context"])

    chat_llm, _ = get_llms()
    if chat_llm:
        prompt = f"""You are SocraticAI. The student is stuck on "{topic}" and needs a level {level} hint (of 3).

TEXTBOOK CONTEXT:
{context_str[:2000]}

STUDENT'S MESSAGE: {state['user_message']}

HINT INSTRUCTION: {HINT_LEVELS[level]}
Start with one line of encouragement, give the hint, then ask your guiding question. Keep it under 120 words."""
        try:
            response = chat_llm.invoke([HumanMessage(content=prompt)])
            state["final_response"] = response.content
            state["agent_used"] = f"hint_gemini_l{level}"
            _trace(state, "hint", f"Level {level} hint (Gemini 2.5 Flash)")
            return state
        except Exception as e:
            log.warning("Hint: Gemini call failed: %s", e)
            state["llm_error"] = describe_llm_error(e)

    snippet = ""
    if state["retrieved_context"]:
        snippet = state["retrieved_context"][0]["content"].split(".")[0][:160]
    fallback = {
        1: f"You're closer than you think! Think about what problem **{topic}** is trying to solve in the first place.",
        2: f"Here's a bigger clue. The textbook puts it like this: *\"{snippet}...\"* How does that connect to your answer?" if snippet
           else f"Here's a bigger clue: break **{topic}** into its inputs, the steps applied, and the output. Which step is unclear?",
        3: f"Almost there. What if the key idea of **{topic}** is the one in that passage? Try restating it in one sentence.",
    }
    state["final_response"] = fallback[level]
    state["agent_used"] = f"hint_local_l{level}"
    _trace(state, "hint", f"Level {level} hint (offline{'; ' + state['llm_error'] if state.get('llm_error') else ''})")
    return state


# ─────────────────────────────────────────────
# ROUTING
# ─────────────────────────────────────────────
def route_after_evaluation(state: AgentState) -> str:
    if _asks_for_help(state["user_message"]):
        return "hint"
    if state.get("consecutive_low_scores", 0) >= 2 and 0 <= state.get("evaluation_score", -1) < 40:
        return "hint"
    return "socrates"


def build_socratic_graph():
    graph = StateGraph(AgentState)
    graph.add_node("knowledge", knowledge_agent)
    graph.add_node("evaluator", evaluator_agent)
    graph.add_node("socrates", socrates_agent)
    graph.add_node("hint", hint_agent)
    graph.set_entry_point("knowledge")
    graph.add_edge("knowledge", "evaluator")
    graph.add_conditional_edges("evaluator", route_after_evaluation, {"socrates": "socrates", "hint": "hint"})
    graph.add_edge("socrates", END)
    graph.add_edge("hint", END)
    return graph.compile()


socratic_graph = build_socratic_graph()


async def run_socratic_session(
    user_message: str,
    conversation_history: list[dict],
    document_ids: list[str],
    current_topic: str = "",
    next_topic: Optional[str] = None,
    consecutive_low_scores: int = 0,
    hint_level: int = 0,
) -> dict:
    """Run one tutoring turn through the agent graph."""
    initial_state: AgentState = {
        "user_message": user_message,
        "conversation_history": conversation_history + [{"role": "user", "content": user_message}],
        "document_ids": document_ids,
        "current_topic": current_topic,
        "next_topic": next_topic,
        "retrieved_context": [],
        "evaluation_score": -1,
        "evaluation_feedback": {},
        "consecutive_low_scores": consecutive_low_scores,
        "hint_level": hint_level,
        "final_response": "",
        "agent_used": "socrates",
        "mastery_achieved": False,
        "agent_trace": [],
        "llm_error": None,
    }
    result = await socratic_graph.ainvoke(initial_state)
    return {
        "response": result["final_response"],
        "agent_used": result["agent_used"],
        "evaluation_score": result["evaluation_score"],
        "evaluation_feedback": result.get("evaluation_feedback", {}),
        "mastery_achieved": result["mastery_achieved"],
        "consecutive_low_scores": result["consecutive_low_scores"],
        "hint_level": result["hint_level"],
        "agent_trace": result["agent_trace"],
        "sources": [
            {"page": c["page"], "text": c["content"][:400], "score": c["score"], "filename": c.get("filename", "")}
            for c in result["retrieved_context"]
        ],
    }
