"""
Intelligent Interview Question Recommendation Engine — FastAPI backend.

Analyzes a candidate resume against a job description and asks an LLM to produce a
structured interview plan: candidate strengths, skills to validate, and tailored
interview questions (difficulty, expected answer points, and a rationale each).

The LLM backend is provider-agnostic (see app/llm.py) — choose a free provider
(Google Gemini, Groq, or local Ollama) via the LLM_PROVIDER environment variable.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .llm import InterviewPlan, LLMError, generate_interview_plan, provider_status

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Intelligent Interview Question Recommendation Engine")


class GenerateRequest(BaseModel):
    resume: str
    job_description: str
    num_questions: int = 8


# --------------------------------------------------------------------------- #
# API endpoints.
# --------------------------------------------------------------------------- #


@app.get("/api/health")
def health() -> dict:
    status = provider_status()
    return {"ok": True, **status}


@app.post("/api/generate", response_model=InterviewPlan)
def generate(req: GenerateRequest) -> InterviewPlan:
    if not req.resume.strip():
        raise HTTPException(status_code=400, detail="Resume is empty.")
    if not req.job_description.strip():
        raise HTTPException(status_code=400, detail="Job description is empty.")

    num = max(3, min(req.num_questions, 15))
    try:
        return generate_interview_plan(req.resume, req.job_description, num)
    except LLMError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)


@app.post("/api/extract-pdf")
async def extract_pdf(file: UploadFile = File(...)) -> dict:
    """Extract plain text from an uploaded resume PDF so it can populate the form."""
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Please upload a .pdf file.")

    data = await file.read()
    try:
        from pypdf import PdfReader

        reader = PdfReader(BytesIO(data))
        text = "\n".join((page.extract_text() or "") for page in reader.pages).strip()
    except Exception as exc:  # noqa: BLE001 - surface a friendly message
        raise HTTPException(status_code=400, detail=f"Could not read PDF: {exc}")

    if not text:
        raise HTTPException(
            status_code=422,
            detail="No selectable text found in this PDF (it may be a scanned image).",
        )
    return {"text": text}


# --------------------------------------------------------------------------- #
# Serve the frontend. Mounted last so /api routes take precedence.
# --------------------------------------------------------------------------- #


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/", StaticFiles(directory=STATIC_DIR), name="static")
