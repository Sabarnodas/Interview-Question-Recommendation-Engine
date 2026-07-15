# Intelligent Interview Question Recommendation Engine

Analyzes a candidate's **resume** against a **job description** and uses Claude to
generate a structured, editable interview plan:

- **Candidate strengths** relevant to the role
- **Skills to validate** — required skills that are missing, unclear, or weak
- **Recommended questions**, each with:
  - a **category** (required technical skill / project experience / missing skill / practical problem-solving)
  - a **difficulty** (Easy / Medium / Hard)
  - **expected answer points** (a grading rubric)
  - a **reason** explaining why the question was selected

The interviewer can **edit, approve, or reject** each question and export the
approved set as Markdown.

---

## How it works

```
Browser (single-page UI)  ──►  FastAPI backend  ──►  LLM provider
        ▲                                              │  JSON output
        └──────────  validated InterviewPlan JSON  ◄───┘  (Pydantic schema)
```

The backend is **provider-agnostic**. It talks to any OpenAI-compatible endpoint and
validates the model's JSON against the `InterviewPlan` Pydantic schema (with a
self-correction retry if the first response is malformed).

| Provider  | Cost            | Env var             | Get a key |
| --------- | --------------- | ------------------- | --------- |
| **gemini** (default) | **Free tier** | `GEMINI_API_KEY` | https://aistudio.google.com/app/apikey |
| **groq**  | **Free tier**   | `GROQ_API_KEY`      | https://console.groq.com/keys |
| **ollama**| **Free, local** | *(none)*            | https://ollama.com/download |
| openai    | Paid            | `OPENAI_API_KEY`    | https://platform.openai.com/api-keys |
| anthropic | Paid            | `ANTHROPIC_API_KEY` | https://console.anthropic.com |

## Setup

Requires **Python 3.10+**.

```bash
# 1. Install dependencies
pip install -r requirements.txt
```

**2. Pick a provider and set its key.** The easiest free option is Google Gemini —
create a free key (no credit card) at https://aistudio.google.com/app/apikey, then:

```powershell
# PowerShell (Windows)
$env:LLM_PROVIDER = "gemini"
$env:GEMINI_API_KEY = "your-gemini-key"
```
```bash
# macOS/Linux
export LLM_PROVIDER=gemini
export GEMINI_API_KEY="your-gemini-key"
```

To use Groq instead: `LLM_PROVIDER=groq` + `GROQ_API_KEY`.
To run fully offline: install [Ollama](https://ollama.com), run `ollama pull llama3.1`,
then `LLM_PROVIDER=ollama` (`LLM_MODEL` picks the model).

```bash
# 3. Run
python run.py
```

Then open **http://127.0.0.1:8000**. The status pill (top-right) shows the active
provider, model, and whether a key was detected.

## Using it

1. Paste the candidate's resume (or click **Upload PDF** to extract text from a resume PDF).
2. Paste the job description.
3. Choose how many questions to generate and click **Generate Plan**.
4. Review the questions — **Edit** to reword, **Approve** / **Reject** to curate.
5. **Copy Approved** or **Export .md** to save the finalized interview plan.

Click **Load example** to try it with the sample resume/JD from the brief.

## Project structure

```
app/
  main.py            FastAPI app: /api/generate, /api/extract-pdf, /api/health
  llm.py             Provider-agnostic LLM layer (Gemini/Groq/Ollama/OpenAI/Anthropic)
  static/
    index.html       UI
    styles.css       Styling (light + dark)
    app.js           Frontend logic (generate, edit/approve/reject, export)
requirements.txt
run.py               Launcher (uvicorn)
```

## API

| Endpoint            | Method | Purpose                                             |
| ------------------- | ------ | --------------------------------------------------- |
| `/api/generate`     | POST   | `{resume, job_description, num_questions}` → plan    |
| `/api/extract-pdf`  | POST   | Upload a resume PDF → extracted text                |
| `/api/health`       | GET    | Reports whether `ANTHROPIC_API_KEY` is configured   |

## Notes

- Switch providers/models any time with the `LLM_PROVIDER` and `LLM_MODEL` env vars — no code change.
- PDF text extraction works on text-based PDFs; scanned/image PDFs won't yield text (no OCR).
