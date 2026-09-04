"""
Multi-Agent Orchestration System using LangGraph
Agents: Orchestrator → Knowledge → Socrates → Evaluator → Hint
"""
from typing import TypedDict, Annotated, Sequence, Optional
from langgraph.graph import StateGraph, END
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.schema import HumanMessage, SystemMessage
from config import get_settings
from rag.pipeline import retrieve_context, retrieve_context_no_filter
import json
import re

settings = get_settings()


# LLMs are lazily initialized via get_llms() when an API key is available



# ─────────────────────────────────────────────
# STATE DEFINITION
# ─────────────────────────────────────────────
class AgentState(TypedDict):
    user_message: str
    conversation_history: list[dict]
    document_id: Optional[str]
    retrieved_context: list[dict]
    evaluation_score: float
    consecutive_low_scores: int
    hint_level: int
    current_concept: str
    final_response: str
    agent_used: str
    mastery_achieved: bool


# ─────────────────────────────────────────────
# AGENT 1: KNOWLEDGE AGENT
# Retrieves relevant content from RAG
# ─────────────────────────────────────────────
def knowledge_agent(state: AgentState) -> AgentState:
    """Fetches relevant context from vector store."""
    query = state["user_message"]

    if state.get("document_id"):
        chunks = retrieve_context(query, state["document_id"], k=4)
    else:
        chunks = retrieve_context_no_filter(query, k=4)

    state["retrieved_context"] = chunks
    return state


# ─────────────────────────────────────────────
# AGENT 2: EVALUATOR AGENT
# Scores the student's answer 0-100
# ─────────────────────────────────────────────
def evaluator_agent(state: AgentState) -> AgentState:
    """Evaluates the student's answer and assigns a score 0-100."""
    history = state["conversation_history"]

    # Only evaluate if there's a previous question from the assistant
    if len(history) < 2:
        state["evaluation_score"] = -1  # Not evaluated yet (first message)
        return state

    # Find the last assistant question
    last_question = ""
    for msg in reversed(history[:-1]):
        if msg["role"] == "assistant":
            last_question = msg["content"]
            break

    if not last_question:
        state["evaluation_score"] = -1
        return state

    user_msg_lower = state["user_message"].strip().lower()
    is_direct_question = (
        user_msg_lower.endswith("?") or
        any(user_msg_lower.startswith(q) for q in ["what", "how", "why", "when", "can you", "explain", "tell me", "define", "show me", "which", "where"])
    )
    if is_direct_question and len(state["user_message"].split()) < 30:
        state["evaluation_score"] = -1
        return state

    context_str = "\n".join([c["content"] for c in state["retrieved_context"]])

    eval_prompt = f"""You are an expert educational evaluator. Score the student's answer.

CONTEXT (from textbook):
{context_str[:1500]}

QUESTION ASKED:
{last_question}

STUDENT'S ANSWER:
{state["user_message"]}

Rate the student's understanding from 0 to 100:
- 0-30: Fundamentally wrong or completely off track
- 31-60: Partial understanding, key concepts missing
- 61-80: Good understanding, minor gaps
- 81-100: Excellent, near-complete mastery

Respond ONLY with a JSON object like:
{{"score": 75, "concept": "Newton's Second Law", "what_they_got_right": "...", "what_is_missing": "..."}}"""

    _, eval_llm = get_llms()
    evaluated = False

    if eval_llm:
        try:
            response = eval_llm.invoke([HumanMessage(content=eval_prompt)])
            json_match = re.search(r'\{.*?\}', response.content, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
                score = float(result.get("score", 50))
                state["evaluation_score"] = score
                state["current_concept"] = result.get("concept", state.get("current_concept", ""))
                evaluated = True
        except Exception:
            evaluated = False

    if not evaluated:
        words = len(state["user_message"].split())
        if words > 15:
            state["evaluation_score"] = 75.0
        elif words > 5:
            state["evaluation_score"] = 60.0
        else:
            state["evaluation_score"] = 40.0

    # Track consecutive low scores
    if state["evaluation_score"] < 50:
        state["consecutive_low_scores"] = state.get("consecutive_low_scores", 0) + 1
    else:
        state["consecutive_low_scores"] = 0

    # Check mastery
    state["mastery_achieved"] = state["evaluation_score"] >= 85

    return state


# ─────────────────────────────────────────────
# AGENT 3: SOCRATES AGENT
# Generates probing questions — never gives the answer
# ─────────────────────────────────────────────
import random
import re
import json

def get_llms():
    """Lazily get Gemini models if a valid key exists, otherwise return None."""
    current_settings = get_settings()
    key = (current_settings.gemini_api_key or "").strip()
    if not key or "your_gemini" in key or len(key) < 15:
        return None, None
    try:
        chat_llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            google_api_key=key,
            temperature=0.7,
        )
        eval_llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            google_api_key=key,
            temperature=0.1,
        )
        return chat_llm, eval_llm
    except Exception:
        return None, None


def extract_key_terms(text: str) -> list[str]:
    """Extract meaningful domain words from student message."""
    stop_words = {
        "the", "is", "at", "which", "on", "and", "a", "an", "i", "think", "what", "how",
        "why", "when", "it", "to", "of", "in", "for", "with", "that", "this", "can", "be",
        "do", "does", "by", "as", "or", "from", "are", "we", "you", "my", "about", "so"
    }
    words = [w.strip(".,!?;:()[]\"'") for w in text.lower().split()]
    meaningful = [w for w in words if len(w) > 3 and w not in stop_words]
    return meaningful


def generate_local_socratic_question(state: AgentState) -> str:
    """Generate diverse, non-repetitive Socratic questions when no API key is present."""
    msg = state["user_message"].strip()
    history = state.get("conversation_history", [])
    turn_count = len(history) // 2 + 1

    # Extract student's terms
    terms = extract_key_terms(msg)
    primary_term = terms[0] if terms else (state.get("current_concept") or "this concept")

    # Extract textbook knowledge snippets from retrieved chunks if available
    snippets = []
    if state.get("retrieved_context"):
        for c in state["retrieved_context"]:
            sentences = [s.strip() for s in re.split(r'[.!?]\s+', c.get("content", "")) if len(s.strip()) > 20]
            snippets.extend(sentences[:2])

    snippet_to_use = snippets[(turn_count - 1) % len(snippets)] if snippets else "the foundational theory"

    # Dialectical Socratic inquiry strategies based on turn count and context
    strategies = [
        # Strategy 1: First Principles & Mechanism
        (
            f"You brought up **{primary_term}**. Let's examine this from first principles: "
            f"what is the exact mathematical or logical mechanism that causes {primary_term} to behave this way? "
            f"How would you explain the step-by-step process?"
        ),
        # Strategy 2: Edge Case & Boundary Testing
        (
            f"That's a solid start on **{primary_term}**! Now let's test the boundaries: "
            f"what happens if the input data is extremely noisy or initialization is flawed? "
            f"Would your reasoning about {primary_term} still hold, or where would the breakdown occur?"
        ),
        # Strategy 3: Real-world / Everyday Analogy
        (
            f"Good intuition. If you had to explain **{primary_term}** to someone with zero technical background "
            f"using an everyday analogy (like sorting mail, water flow, or a balance scale), what real-world parallel would you choose and why?"
        ),
        # Strategy 4: Socratic Challenge / Counter-argument
        (
            f"Suppose a peer argued: *'We don't actually need {primary_term}, we could just skip it and use random guessing or a simpler heuristic.'* "
            f"What specific drawback or limitation would you cite to prove them wrong?"
        ),
        # Strategy 5: Grounded in Textbook context
        (
            f"Looking closely at what the material points out: *\"{snippet_to_use[:120]}...\"*\n\n"
            f"How does that observation connect to your thoughts on **{primary_term}**? What is the vital takeaway here?"
        ),
        # Strategy 6: Cause and Effect
        (
            f"Interesting observation! If you modify or increase **{primary_term}**, "
            f"what is the direct consequence on the final output or convergence speed? Which trade-off are you making?"
        )
    ]

    selected = strategies[(turn_count - 1) % len(strategies)]
    notice = "\n\n*(Notice: Running on Local Socratic Engine. Add your free Gemini API key in the navbar to unlock full Gemini 1.5 Flash AI reasoning!)*"
    return selected + notice


# ─────────────────────────────────────────────
# AGENT 3: SOCRATES AGENT
# Generates probing questions — never gives the answer
# ─────────────────────────────────────────────
def socrates_agent(state: AgentState) -> AgentState:
    """Generates Socratic probing questions based on context and score."""
    chat_llm, _ = get_llms()

    # If no LLM available, use intelligent dynamic local generator
    if not chat_llm:
        state["final_response"] = generate_local_socratic_question(state)
        state["agent_used"] = "socrates_local"
        return state

    context_str = "\n\n".join([
        f"[Page {c['page']}]: {c['content']}" for c in state["retrieved_context"]
    ])

    history_str = ""
    for msg in state["conversation_history"][-6:]:
        role = "Student" if msg["role"] == "user" else "SocraticAI"
        history_str += f"{role}: {msg['content']}\n\n"

    score = state.get("evaluation_score", -1)
    mastery = state.get("mastery_achieved", False)

    if mastery:
        tone = "celebratory and advancing"
        instruction = "Congratulate the student warmly, confirm their understanding, and introduce the NEXT related concept with a new probing question."
    elif score >= 60:
        tone = "encouraging and deepening"
        instruction = "The student is on the right track! Acknowledge what they got right, then ask a deeper follow-up question to solidify their understanding. Do NOT reveal the full answer yet."
    elif score >= 30:
        tone = "gentle and guiding"
        instruction = "The student has partial understanding. Acknowledge what they got right, then guide them with a question that points toward the missing piece. Use an analogy or real-world example."
    elif score >= 0:
        tone = "supportive and redirecting"
        instruction = "The student seems confused. Gently redirect with a simpler, more foundational question. Break the concept down. Use a relatable everyday analogy."
    else:
        tone = "curious and welcoming"
        instruction = "This is the start of the conversation. Greet the student, identify what topic they want to explore based on their message, and ask the first Socratic opening question to gauge their current knowledge."

    system_prompt = f"""You are SocraticAI — an adaptive, patient, and intellectually stimulating AI tutor.
You are helping the student master complex concepts from their uploaded PDF textbook and notes.

HOW TO RESPOND:
1. IF THE STUDENT ASKS A DIRECT QUESTION (e.g. "What does the PDF say about X?", "What is X?", "Can you explain X from the document?", "Why does X happen?"):
   - DIRECTLY ANSWER their question by explaining the concept thoroughly using the TEXTBOOK CONTEXT provided below.
   - Quote or reference relevant details, formulas, or definitions from the textbook context to ground your answer.
   - THEN, conclude your response with ONE probing Socratic follow-up question to test if they understood the mechanism or can apply it.

2. IF THE STUDENT IS ATTEMPTING TO ANSWER A QUESTION OR TEST THEIR KNOWLEDGE:
   - Do NOT just hand them the answer immediately.
   - Evaluate their thought process. Praise what they got right, and gently point out any subtle misconceptions or missing links.
   - Guide them toward the complete insight using progressive Socratic questioning, hints, or relatable analogies.

3. GENERAL PRINCIPLES:
   - Always prioritize facts and methods found in the TEXTBOOK CONTEXT.
   - Be warm, encouraging, and clear.
   - End with ONE focused question to keep the dialectical dialogue engaging.
   - If the student achieves mastery (score >= 85), congratulate them and transition to the next related concept.

YOUR TONE: {tone}
YOUR SPECIFIC INSTRUCTION: {instruction}

TEXTBOOK CONTEXT:
{context_str[:2500]}

STUDENT SCORE ON PREVIOUS ANSWER: {score if score >= 0 else "N/A (inquiry / first question)"}
"""

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"Conversation so far:\n{history_str}\n\nLatest student message: {state['user_message']}\n\nRespond as SocraticAI:"),
    ]

    try:
        response = chat_llm.invoke(messages)
        state["final_response"] = response.content
        state["agent_used"] = "socrates_gemini"
    except Exception as e:
        state["final_response"] = generate_local_socratic_question(state)
        state["agent_used"] = "socrates_local"

    return state


# ─────────────────────────────────────────────
# AGENT 4: HINT AGENT
# Gives graduated hints when student is stuck
# ─────────────────────────────────────────────
def hint_agent(state: AgentState) -> AgentState:
    """Provides graduated hints when student is stuck."""
    hint_level = min(state.get("hint_level", 0) + 1, 3)
    state["hint_level"] = hint_level

    context_str = "\n".join([c["content"] for c in state["retrieved_context"]])

    hint_prompts = {
        1: "Give a very broad, gentle hint — just a conceptual direction. Don't reveal any key terms. End with an encouraging question.",
        2: "Give a medium hint — mention a key principle or idea (but not the answer). Use an analogy. End with a guiding question.",
        3: "Give a strong hint — almost reveal the answer but frame it as a question. For example: 'What if I told you that [key insight]... does that change your thinking?'",
    }

    prompt = f"""You are SocraticAI. The student has been struggling and needs a Level {hint_level} hint.

TEXTBOOK CONTEXT:
{context_str[:1500]}

STUDENT'S MESSAGE: {state["user_message"]}

HINT INSTRUCTION: {hint_prompts[hint_level]}

Start with empathy ("That's a tricky one!", "You're closer than you think!", "Let's approach this differently!"), then give the hint, then ask your guiding question."""

    chat_llm, _ = get_llms()
    hint_sent = False

    if chat_llm:
        try:
            response = chat_llm.invoke([HumanMessage(content=prompt)])
            state["final_response"] = f"💡 **Hint Level {hint_level}:** {response.content}"
            state["agent_used"] = f"hint_gemini_l{hint_level}"
            hint_sent = True
        except Exception:
            hint_sent = False

    if not hint_sent:
        fallback_hints = {
            1: "💡 **Hint Level 1:** You're closer than you think! Consider the general rule: how does this behave under normal conditions?",
            2: "💡 **Hint Level 2:** Let's look at an analogy: think of how water flows downhill. How does that energy balance apply to what we're studying?",
            3: "💡 **Hint Level 3:** What if you look directly at the conservation principle? If input must balance output, what must the missing piece be?",
        }
        state["final_response"] = fallback_hints.get(hint_level, fallback_hints[1])
        state["agent_used"] = f"hint_local_l{hint_level}"
    return state


# ─────────────────────────────────────────────
# ROUTING LOGIC
# ─────────────────────────────────────────────
def route_after_evaluation(state: AgentState) -> str:
    """Decide which agent responds based on evaluation score."""
    score = state.get("evaluation_score", -1)
    consecutive_low = state.get("consecutive_low_scores", 0)

    # Student is stuck — give hints
    if consecutive_low >= 2 and score < 40:
        return "hint"

    # Otherwise, Socrates responds
    return "socrates"


# ─────────────────────────────────────────────
# BUILD THE LANGGRAPH STATE MACHINE
# ─────────────────────────────────────────────
def build_socratic_graph():
    graph = StateGraph(AgentState)

    # Add nodes
    graph.add_node("knowledge", knowledge_agent)
    graph.add_node("evaluator", evaluator_agent)
    graph.add_node("socrates", socrates_agent)
    graph.add_node("hint", hint_agent)

    # Entry point
    graph.set_entry_point("knowledge")

    # Flow: knowledge → evaluator → route → (socrates or hint) → END
    graph.add_edge("knowledge", "evaluator")
    graph.add_conditional_edges(
        "evaluator",
        route_after_evaluation,
        {
            "socrates": "socrates",
            "hint": "hint",
        }
    )
    graph.add_edge("socrates", END)
    graph.add_edge("hint", END)

    return graph.compile()


# Singleton compiled graph
socratic_graph = build_socratic_graph()


# ─────────────────────────────────────────────
# PUBLIC INTERFACE
# ─────────────────────────────────────────────
async def run_socratic_session(
    user_message: str,
    conversation_history: list[dict],
    document_id: Optional[str] = None,
    consecutive_low_scores: int = 0,
    hint_level: int = 0,
    current_concept: str = "",
) -> dict:
    """
    Main entry point for the multi-agent Socratic conversation.
    Returns the agent response and metadata.
    """
    initial_state: AgentState = {
        "user_message": user_message,
        "conversation_history": conversation_history + [{"role": "user", "content": user_message}],
        "document_id": document_id,
        "retrieved_context": [],
        "evaluation_score": -1,
        "consecutive_low_scores": consecutive_low_scores,
        "hint_level": hint_level,
        "current_concept": current_concept,
        "final_response": "",
        "agent_used": "socrates",
        "mastery_achieved": False,
    }

    result = await socratic_graph.ainvoke(initial_state)

    return {
        "response": result["final_response"],
        "agent_used": result["agent_used"],
        "evaluation_score": result["evaluation_score"],
        "mastery_achieved": result["mastery_achieved"],
        "consecutive_low_scores": result["consecutive_low_scores"],
        "hint_level": result["hint_level"],
        "current_concept": result["current_concept"],
        "sources": [
            {
                "page": c.get("page", 1),
                "text": c.get("content", "")[:350],
                "score": round(float(c.get("score", 0)), 3)
            }
            for c in result["retrieved_context"]
        ],
    }
