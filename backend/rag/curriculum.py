"""
Build an ordered list of topics (a curriculum) for a document.

A session walks through these topics in order and moves to the next one only
after the student scores at least MASTERY_THRESHOLD on the current one.

With a Gemini key, Gemini reads the start of the document and proposes the
topics in teaching order. Without one, headings are picked from the PDF text
in the order they appear.
"""
import json
import re

from langchain.schema import HumanMessage

from llm import get_llms

MAX_TOPICS = 8


def _clean_heading(line: str) -> str:
    line = re.sub(r"^\s*(chapter\s+)?\d+(\.\d+)*[.)]?\s+", "", line, flags=re.I)
    return line.strip(" -:•\t")


def _is_topic_like(title: str, min_words: int) -> bool:
    words = title.split()
    if not (min_words <= len(words) <= 8 and 4 <= len(title) <= 70):
        return False
    if not title[0].isupper() or title.endswith((".", ",", ";", "?")):
        return False
    if re.match(r"^(figure|fig\.|table|example|equation|listing)\b", title, re.I):
        return False
    return sum(c.isalpha() for c in title) >= len(title) * 0.7


def heuristic_topics(pages: list[dict], limit: int = MAX_TOPICS) -> list[str]:
    """Pick section headings in reading order.

    Prefers lines in a larger/bold font (found by extract_pages). If the PDF
    has no font differences, falls back to short title-like lines.
    """
    topics, seen = [], set()
    for p in pages:
        for line in p.get("headings", []):
            title = _clean_heading(line)
            if _is_topic_like(title, min_words=1) and title.lower() not in seen:
                seen.add(title.lower())
                topics.append(title)
    if len(topics) >= 2:
        return topics[:limit]
    return _text_only_topics(pages, limit)


def _text_only_topics(pages: list[dict], limit: int) -> list[str]:
    # Lines that repeat on many pages are running headers/footers, not topics.
    line_pages: dict[str, set[int]] = {}
    for p in pages:
        for line in p["text"].split("\n"):
            key = line.strip().lower()
            if key:
                line_pages.setdefault(key, set()).add(p["page"])
    repeated = {k for k, v in line_pages.items() if len(v) > max(2, len(pages) * 0.3)}

    topics, seen = [], set()
    for p in pages:
        for raw in p["text"].split("\n"):
            line = raw.strip()
            if line.lower() in repeated:
                continue
            title = _clean_heading(line)
            if not _is_topic_like(title, min_words=2):
                continue
            key = title.lower()
            if key not in seen:
                seen.add(key)
                topics.append(title)
            if len(topics) >= limit:
                return topics
    return topics


def llm_topics(full_text: str, limit: int = MAX_TOPICS) -> list[str]:
    """Ask Gemini for the document's key concepts in teaching order."""
    _, eval_llm = get_llms()
    if eval_llm is None:
        return []
    prompt = f"""Below is the text of a study document. List the {limit} most important concepts it teaches,
in the order a student should learn them (foundations first). Use short names (2-6 words) taken from the document.
Respond ONLY with a JSON array of strings.

DOCUMENT:
{full_text[:15000]}"""
    try:
        response = eval_llm.invoke([HumanMessage(content=prompt)])
        match = re.search(r"\[.*\]", response.content, re.DOTALL)
        topics = json.loads(match.group()) if match else []
        return [str(t).strip() for t in topics if str(t).strip()][:limit]
    except Exception:
        return []


def build_curriculum(pages: list[dict]) -> list[str]:
    full_text = "\n".join(p["text"] for p in pages)
    return llm_topics(full_text) or heuristic_topics(pages)
