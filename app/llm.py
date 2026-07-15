"""
Provider-agnostic LLM layer.

The app can talk to any of several backends via one OpenAI-compatible client.
Pick one with the LLM_PROVIDER environment variable:

  gemini   Google Gemini      — FREE tier, no credit card. Recommended.
           Key: GEMINI_API_KEY   (get one at https://aistudio.google.com/app/apikey)
  groq     Groq (Llama etc.)  — FREE tier, very fast.
           Key: GROQ_API_KEY     (get one at https://console.groq.com/keys)
  openai   OpenAI             — paid.  Key: OPENAI_API_KEY
  ollama   Local models       — FREE/offline, needs Ollama running locally.
  anthropic Claude            — paid.  Key: ANTHROPIC_API_KEY

Optionally override the model with LLM_MODEL.
"""

from __future__ import annotations

import json
import os
from typing import List, Literal, Tuple

from pydantic import BaseModel, Field, ValidationError

DEFAULT_PROVIDER = "gemini"

# base_url / default model / which env var holds the API key.
PROVIDERS = {
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "model": "gemini-2.0-flash",
        "key_env": "GEMINI_API_KEY",
        "signup": "https://aistudio.google.com/app/apikey",
        "label": "Google Gemini (free tier)",
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "model": "llama-3.3-70b-versatile",
        "key_env": "GROQ_API_KEY",
        "signup": "https://console.groq.com/keys",
        "label": "Groq (free tier)",
    },
    "openai": {
        "base_url": None,
        "model": "gpt-4o-mini",
        "key_env": "OPENAI_API_KEY",
        "signup": "https://platform.openai.com/api-keys",
        "label": "OpenAI",
    },
    "ollama": {
        "base_url": "http://localhost:11434/v1",
        "model": "llama3.1",
        "key_env": None,  # local server needs no real key
        "signup": "https://ollama.com/download",
        "label": "Ollama (local)",
    },
    "anthropic": {
        "base_url": "https://api.anthropic.com/v1/",  # OpenAI-compatible shim
        "model": "claude-opus-4-8",
        "key_env": "ANTHROPIC_API_KEY",
        "signup": "https://console.anthropic.com/settings/keys",
        "label": "Anthropic Claude",
    },
}


# --------------------------------------------------------------------------- #
# Schema — the shape the model must return.
# --------------------------------------------------------------------------- #

Category = Literal[
    "required_technical_skill",
    "project_experience",
    "missing_or_weak_skill",
    "practical_problem_solving",
]
Difficulty = Literal["Easy", "Medium", "Hard"]


class Question(BaseModel):
    category: Category
    difficulty: Difficulty
    question: str
    expected_answer_points: List[str]
    reason: str


class InterviewPlan(BaseModel):
    candidate_strengths: List[str]
    skills_to_validate: List[str]
    questions: List[Question]


class LLMError(Exception):
    """Wraps provider errors with an HTTP status hint and a user-facing message."""

    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


# --------------------------------------------------------------------------- #
# Config helpers.
# --------------------------------------------------------------------------- #


def current_provider() -> str:
    name = os.environ.get("LLM_PROVIDER", DEFAULT_PROVIDER).strip().lower()
    return name if name in PROVIDERS else DEFAULT_PROVIDER


def _config(provider: str) -> dict:
    cfg = dict(PROVIDERS[provider])
    if os.environ.get("LLM_MODEL"):
        cfg["model"] = os.environ["LLM_MODEL"].strip()
    return cfg


def _api_key(cfg: dict) -> str | None:
    key_env = cfg["key_env"]
    if key_env is None:  # ollama
        return "ollama"
    return os.environ.get(key_env)


def provider_status() -> dict:
    provider = current_provider()
    cfg = _config(provider)
    key = _api_key(cfg)
    return {
        "provider": provider,
        "label": cfg["label"],
        "model": cfg["model"],
        "key_configured": bool(key),
        "key_env": cfg["key_env"] or "(none needed)",
        "signup": cfg["signup"],
    }


# --------------------------------------------------------------------------- #
# Prompting.
# --------------------------------------------------------------------------- #

SYSTEM_PROMPT = """You are a senior technical interviewer and hiring panel lead. \
Given a candidate's resume and a job description, you design a focused, high-signal \
interview plan.

Rules:
- Identify genuine strengths where the resume aligns with the job's requirements.
- Identify skills to validate: required skills from the job description that are \
missing, only implied, or look weak/unclear in the resume.
- Generate interview questions specific to THIS candidate and THIS role — never \
generic filler. Draw on the candidate's actual projects and experience where possible.
- Cover a balanced mix across these categories: required_technical_skill, \
project_experience, missing_or_weak_skill, practical_problem_solving.
- Assign each question a difficulty (Easy, Medium, or Hard) with a sensible spread.
- For each question, give concrete expected_answer_points that act as a grading rubric.
- For each question, give a short reason explaining why it was selected, referencing \
the resume/JD gap or strength it targets.
- No duplicate or near-duplicate questions; no questions about skills irrelevant to \
the job description.
- You MUST respond with a single valid JSON object and nothing else."""

JSON_SHAPE = """Return ONLY a JSON object with exactly this structure (no markdown, no prose):
{
  "candidate_strengths": ["string", ...],
  "skills_to_validate": ["string", ...],
  "questions": [
    {
      "category": "required_technical_skill" | "project_experience" | "missing_or_weak_skill" | "practical_problem_solving",
      "difficulty": "Easy" | "Medium" | "Hard",
      "question": "string",
      "expected_answer_points": ["string", ...],
      "reason": "string"
    }
  ]
}"""


def _user_prompt(resume: str, jd: str, num: int) -> str:
    return f"""Analyze the following candidate resume against the job description and \
produce a structured interview plan with approximately {num} questions.

=== RESUME ===
{resume.strip()}

=== JOB DESCRIPTION ===
{jd.strip()}

{JSON_SHAPE}"""


# --------------------------------------------------------------------------- #
# JSON extraction + normalization (models occasionally wrap or mis-case output).
# --------------------------------------------------------------------------- #

_CATEGORY_ALIASES = {
    "required_technical_skill": "required_technical_skill",
    "technical": "required_technical_skill",
    "technical_skill": "required_technical_skill",
    "project_experience": "project_experience",
    "project": "project_experience",
    "experience": "project_experience",
    "missing_or_weak_skill": "missing_or_weak_skill",
    "missing_skill": "missing_or_weak_skill",
    "weak_skill": "missing_or_weak_skill",
    "missing": "missing_or_weak_skill",
    "practical_problem_solving": "practical_problem_solving",
    "problem_solving": "practical_problem_solving",
    "practical": "practical_problem_solving",
}


def _extract_json(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        # strip ```json ... ``` fences
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip().rstrip("`").strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text


import re

# Small stopword set so similarity compares meaningful content words, not filler.
_STOPWORDS = frozenset(
    "a an and are as at be by can could do does for from how in is it of on or "
    "should the this that to use using what when which who why will with would you "
    "your describe explain walk me through about would design build".split()
)


def _content_tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {w for w in words if len(w) > 1 and w not in _STOPWORDS}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    union = len(a | b)
    return len(a & b) / union if union else 0.0


def dedupe_questions(questions: List[Question], threshold: float = 0.7) -> List[Question]:
    """Drop near-duplicate questions as a code-level backstop to the prompt rule.

    Compares content-word overlap (Jaccard) between question texts. The threshold
    is deliberately conservative (0.7) so it only removes genuinely near-identical
    questions and never trims a legitimately distinct one. Order is preserved.
    """
    kept: List[Question] = []
    kept_tokens: List[set[str]] = []
    for q in questions:
        toks = _content_tokens(q.question)
        if any(_jaccard(toks, prev) >= threshold for prev in kept_tokens):
            continue
        kept.append(q)
        kept_tokens.append(toks)
    return kept


def _normalize(data: dict) -> dict:
    data.setdefault("candidate_strengths", [])
    data.setdefault("skills_to_validate", [])
    for q in data.get("questions", []):
        if isinstance(q.get("difficulty"), str):
            q["difficulty"] = q["difficulty"].strip().capitalize()
        if isinstance(q.get("category"), str):
            key = q["category"].strip().lower().replace(" ", "_").replace("-", "_")
            q["category"] = _CATEGORY_ALIASES.get(key, q["category"])
    return data


# --------------------------------------------------------------------------- #
# The call.
# --------------------------------------------------------------------------- #


def generate_interview_plan(resume: str, jd: str, num: int) -> InterviewPlan:
    provider = current_provider()
    cfg = _config(provider)
    key = _api_key(cfg)

    if not key:
        raise LLMError(
            401,
            f"No API key found for provider '{provider}'. Set {cfg['key_env']} "
            f"(free key: {cfg['signup']}), then restart. Or choose another provider "
            f"with LLM_PROVIDER.",
        )

    try:
        from openai import OpenAI
        import openai as openai_mod
    except ImportError:
        raise LLMError(500, "The 'openai' package is not installed. Run: pip install openai")

    client = OpenAI(api_key=key, base_url=cfg["base_url"])

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _user_prompt(resume, jd, num)},
    ]

    last_err = ""
    for attempt in range(2):
        try:
            kwargs: dict = {
                "model": cfg["model"],
                "messages": messages,
                "temperature": 0.4,
            }
            # JSON mode where supported (harmless prompt already forces JSON).
            if provider in ("gemini", "groq", "openai"):
                kwargs["response_format"] = {"type": "json_object"}
            resp = client.chat.completions.create(**kwargs)
        except openai_mod.AuthenticationError:
            raise LLMError(401, f"Authentication failed for '{provider}'. Check {cfg['key_env']}.")
        except openai_mod.RateLimitError:
            raise LLMError(429, f"'{provider}' rate limit / quota reached. Wait a bit or switch providers.")
        except openai_mod.APIConnectionError:
            msg = "Could not reach the provider."
            if provider == "ollama":
                msg = "Could not reach Ollama at localhost:11434. Is `ollama serve` running?"
            raise LLMError(503, msg)
        except openai_mod.APIStatusError as exc:
            detail = getattr(exc, "message", str(exc))
            raise LLMError(502, f"'{provider}' API error: {detail}")
        except Exception as exc:  # noqa: BLE001
            raise LLMError(502, f"'{provider}' request failed: {exc}")

        text = resp.choices[0].message.content or ""
        try:
            data = _normalize(json.loads(_extract_json(text)))
            plan = InterviewPlan.model_validate(data)
            plan.questions = dedupe_questions(plan.questions)
            return plan
        except (json.JSONDecodeError, ValidationError) as exc:
            last_err = str(exc)
            # Ask the model to correct itself once.
            messages.append({"role": "assistant", "content": text})
            messages.append(
                {
                    "role": "user",
                    "content": f"That was not valid. Error: {last_err}. "
                    f"Respond again with ONLY the corrected JSON object.",
                }
            )

    raise LLMError(502, f"The model did not return a valid interview plan. ({last_err})")
