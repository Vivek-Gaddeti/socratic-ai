"""End-to-end API flow: register -> upload -> session -> answers -> topic advances -> progress saved."""
import time

import pytest
from fastapi.testclient import TestClient

from config import MASTERY_THRESHOLD
from main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def auth_headers(client, email="ada@example.com"):
    r = client.post("/auth/register", json={"name": "Ada", "email": email, "password": "pass1234"})
    if r.status_code == 400:
        r = client.post("/auth/login", json={"email": email, "password": "pass1234"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def upload_and_wait(client, headers, pdf_path):
    with open(pdf_path, "rb") as f:
        doc = client.post("/documents/upload", files={"file": ("ml_notes.pdf", f, "application/pdf")}, headers=headers).json()
    for _ in range(50):
        doc = client.get(f"/documents/{doc['id']}", headers=headers).json()
        if doc["status"] != "processing":
            break
        time.sleep(0.1)
    return doc


def test_requires_login(client):
    assert client.get("/chat/sessions").status_code == 401
    assert client.post("/api/settings/api-key", json={"api_key": "x" * 20}).status_code == 401


def test_upload_rejects_non_pdf(client):
    headers = auth_headers(client)
    r = client.post("/documents/upload", files={"file": ("a.pdf", b"hello", "application/pdf")}, headers=headers)
    assert r.status_code == 400


def test_full_learning_flow(client, sample_pdf):
    headers = auth_headers(client)
    doc = upload_and_wait(client, headers, sample_pdf)
    assert doc["status"] == "ready", doc
    assert doc["topics"][:3] == ["Gradient Descent", "Stochastic Gradient Descent", "Regularization"]

    session = client.post("/chat/session", json={"document_id": doc["id"]}, headers=headers).json()
    assert session["current_topic"] == "Gradient Descent"
    assert session["messages"][0]["role"] == "assistant"  # the tutor's saved opening question

    # Turn 1 is a vague reply (graded low); turn 2 is a strong on-topic answer.
    first = client.post("/chat/message", json={"session_id": session["id"], "message": "Let's start"}, headers=headers).json()
    assert 0 <= first["evaluation_score"] < MASTERY_THRESHOLD
    assert first["sources"] and first["sources"][0]["page"] == 1
    answer = ("Gradient descent is an optimization algorithm that updates model parameters in the direction of "
              "the negative gradient of the loss function, and the learning rate controls the step size")
    second = client.post("/chat/message", json={"session_id": session["id"], "message": answer}, headers=headers).json()
    assert second["evaluation_score"] >= MASTERY_THRESHOLD
    assert second["advanced"] is True
    assert second["session"]["current_topic"] == "Stochastic Gradient Descent"

    # Progress is saved per user: a brand-new session skips the mastered topic.
    again = client.post("/chat/session", json={"document_id": doc["id"]}, headers=headers).json()
    assert again["current_topic"] == "Stochastic Gradient Descent"

    prof = client.get("/chat/proficiency", headers=headers).json()
    topics = {t["concept"]: t for t in prof["documents"][0]["topics"]}
    assert topics["Gradient Descent"]["mastered"] is True
    assert topics["Regularization"]["attempts"] == 0

    detail = client.get(f"/chat/sessions/{session['id']}", headers=headers).json()
    assert len(detail["messages"]) == 5  # opening question + 2 turns
    assert detail["messages"][2]["agent_trace"][0]["agent"] == "knowledge"


def test_weak_answer_does_not_advance(client, sample_pdf):
    headers = auth_headers(client, "bob@example.com")
    doc = upload_and_wait(client, headers, sample_pdf)
    session = client.post("/chat/session", json={"document_id": doc["id"]}, headers=headers).json()
    client.post("/chat/message", json={"session_id": session["id"], "message": "Hi"}, headers=headers)
    out = client.post("/chat/message", json={"session_id": session["id"], "message": "it goes down"}, headers=headers).json()
    assert out["evaluation_score"] < MASTERY_THRESHOLD
    assert out["advanced"] is False
    assert out["session"]["current_topic"] == "Gradient Descent"
