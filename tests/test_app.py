"""
Automated tests for the Interview Question Recommendation Engine.

Covers the deterministic logic (JSON extraction, normalization, dedup) and the
FastAPI endpoints (validation, error mapping, and a success path). The LLM call
is monkeypatched, so these tests need no API key and no network access.

Run with:  pytest
"""

from fastapi.testclient import TestClient

from app import main
from app.llm import (
    InterviewPlan,
    Question,
    _content_tokens,
    _extract_json,
    _jaccard,
    _normalize,
    dedupe_questions,
)

client = TestClient(main.app)


def _q(text: str, category="required_technical_skill", difficulty="Medium") -> Question:
    return Question(
        category=category,
        difficulty=difficulty,
        question=text,
        expected_answer_points=["point"],
        reason="reason",
    )


# --------------------------------------------------------------------------- #
# JSON extraction / normalization
# --------------------------------------------------------------------------- #


def test_extract_json_strips_code_fences():
    import json

    fenced = '```json\n{"a": 1, "b": [2, 3]}\n```'
    assert json.loads(_extract_json(fenced)) == {"a": 1, "b": [2, 3]}


def test_extract_json_pulls_object_from_surrounding_prose():
    import json

    noisy = 'Sure, here you go: {"x": true} — hope that helps!'
    assert json.loads(_extract_json(noisy)) == {"x": True}


def test_normalize_fixes_difficulty_casing_and_category_alias():
    data = {
        "questions": [
            {
                "difficulty": "hard",
                "category": "Missing Skill",
                "question": "q",
                "expected_answer_points": [],
                "reason": "",
            }
        ]
    }
    out = _normalize(data)
    assert out["questions"][0]["difficulty"] == "Hard"
    assert out["questions"][0]["category"] == "missing_or_weak_skill"
    # missing top-level keys are backfilled so validation can't crash
    assert out["candidate_strengths"] == []
    assert out["skills_to_validate"] == []


def test_normalize_output_validates_against_schema():
    data = {
        "candidate_strengths": ["Python"],
        "skills_to_validate": ["Celery"],
        "questions": [
            {
                "difficulty": "easy",
                "category": "practical",
                "question": "q",
                "expected_answer_points": ["a"],
                "reason": "r",
            }
        ],
    }
    plan = InterviewPlan.model_validate(_normalize(data))
    assert plan.questions[0].difficulty == "Easy"
    assert plan.questions[0].category == "practical_problem_solving"


# --------------------------------------------------------------------------- #
# Duplicate detection (requirement #9 — code-level backstop)
# --------------------------------------------------------------------------- #


def test_dedupe_removes_near_identical_questions():
    qs = [
        _q("Explain how you would design a background email processing system using Django and Celery."),
        _q("Explain how you would build a background email processing system with Django and Celery."),
    ]
    assert len(dedupe_questions(qs)) == 1


def test_dedupe_keeps_distinct_questions():
    qs = [
        _q("Explain how you would design a background email system using Django and Celery."),
        _q("A Django API becomes slow retrieving thousands of records. How would you fix it?"),
        _q("Walk me through how the Django ORM translates a queryset into SQL."),
    ]
    assert len(dedupe_questions(qs)) == 3


def test_dedupe_handles_empty_list():
    assert dedupe_questions([]) == []


def test_jaccard_bounds():
    a = _content_tokens("docker redis celery")
    assert _jaccard(a, a) == 1.0
    assert _jaccard(a, set()) == 0.0


# --------------------------------------------------------------------------- #
# API: /api/health
# --------------------------------------------------------------------------- #


def test_health_reports_provider():
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert "provider" in body
    assert "model" in body
    assert "key_configured" in body


# --------------------------------------------------------------------------- #
# API: /api/generate
# --------------------------------------------------------------------------- #


def test_generate_rejects_empty_resume():
    resp = client.post("/api/generate", json={"resume": "  ", "job_description": "Python"})
    assert resp.status_code == 400


def test_generate_rejects_empty_job_description():
    resp = client.post("/api/generate", json={"resume": "Python", "job_description": ""})
    assert resp.status_code == 400


def test_generate_success_path(monkeypatch):
    fake = InterviewPlan(
        candidate_strengths=["Strong Python"],
        skills_to_validate=["Celery"],
        questions=[_q("Design a Celery pipeline.", category="missing_or_weak_skill")],
    )
    monkeypatch.setattr(main, "generate_interview_plan", lambda r, j, n: fake)

    resp = client.post(
        "/api/generate",
        json={"resume": "Python Django", "job_description": "Python Celery", "num_questions": 5},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["candidate_strengths"] == ["Strong Python"]
    assert len(data["questions"]) == 1
    assert data["questions"][0]["category"] == "missing_or_weak_skill"


def test_generate_maps_llm_error_to_http_status(monkeypatch):
    from app.llm import LLMError

    def boom(resume, jd, num):
        raise LLMError(401, "No API key found for provider 'groq'.")

    monkeypatch.setattr(main, "generate_interview_plan", boom)
    resp = client.post("/api/generate", json={"resume": "x", "job_description": "y"})
    assert resp.status_code == 401
    assert "No API key" in resp.json()["detail"]


# --------------------------------------------------------------------------- #
# API: /api/extract-pdf
# --------------------------------------------------------------------------- #


def test_extract_pdf_rejects_non_pdf():
    resp = client.post(
        "/api/extract-pdf",
        files={"file": ("resume.txt", b"hello world", "text/plain")},
    )
    assert resp.status_code == 400


# --------------------------------------------------------------------------- #
# Static UI is served
# --------------------------------------------------------------------------- #


def test_index_is_served():
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Interview Question Recommendation Engine" in resp.text
