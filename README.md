# Intelligent Interview Question Recommendation Engine

Analyzes a candidate's **resume** against a **job description** and uses an LLM to
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

**Live demo:** https://interview-question-recommendation-e.vercel.app/

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
  __init__.py
  main.py            FastAPI app: /api/generate, /api/extract-pdf, /api/health
  llm.py             Provider-agnostic LLM layer + schema + dedup (Gemini/Groq/Ollama/OpenAI/Anthropic)
  static/
    index.html       UI
    styles.css       Styling (light + dark)
    app.js           Frontend logic (generate, edit/approve/reject, export)
api/
  index.py           Vercel serverless entrypoint (exposes the FastAPI app)
tests/
  test_app.py        Automated tests (pytest)
vercel.json          Vercel deployment config
requirements.txt     Runtime dependencies
requirements-dev.txt Test dependencies
run.py               Local launcher (uvicorn)
```

## API

| Endpoint            | Method | Purpose                                             |
| ------------------- | ------ | --------------------------------------------------- |
| `/api/generate`     | POST   | `{resume, job_description, num_questions}` → plan    |
| `/api/extract-pdf`  | POST   | Upload a resume PDF → extracted text                |
| `/api/health`       | GET    | Reports the active provider, model, and whether its key is set |

## Testing

Automated tests cover the deterministic logic (JSON extraction, normalization,
duplicate detection) and the API endpoints (validation, error mapping, and a
success path with the LLM call mocked). **No API key or network is needed** to run them.

```bash
pip install -r requirements-dev.txt
pytest
```

## Deployment (Vercel)

The app is configured to deploy as a single Python serverless function on Vercel
(`vercel.json` routes all requests to `api/index.py`, which serves both the API
and the static UI).

1. Push the repo to GitHub.
2. On [vercel.com](https://vercel.com): **Add New → Project → import the repo**
   (auto-detected as FastAPI).
3. Add environment variables (**Settings → Environment Variables**), e.g.
   `LLM_PROVIDER=groq` and `GROQ_API_KEY=...`.
4. **Deploy.** Every push to `main` re-deploys automatically.

> Free-tier notes: serverless functions cold-start after idle (a few extra seconds
> on the first request) and have a ~10s execution limit — comfortably enough for a
> fast provider like Groq.

## Assumptions & Trade-offs

**Assumptions**
- Resume and job description are provided as **text** (or a text-based PDF). Scanned
  image PDFs aren't OCR'd — the app tells the user when a PDF has no selectable text.
- The interviewer is the user; there's no authentication or multi-user persistence —
  a generated plan lives in the browser session until exported.
- An LLM provider key is supplied via environment variables (never committed).

**Trade-offs**
- **Provider-agnostic over single-vendor.** The LLM layer targets any OpenAI-compatible
  endpoint so you can use a free tier (Gemini/Groq) or run offline (Ollama). The cost is
  that we validate JSON ourselves rather than relying on one vendor's native structured
  output; a self-correction retry handles the rare malformed response.
- **Prompt + code for the "no duplicates/irrelevant" rule.** Relevance is enforced via
  the prompt (semantic judgment isn't reliable in plain code). Duplicates additionally
  get a deterministic backstop: a conservative content-word similarity check
  (`dedupe_questions`, Jaccard ≥ 0.7) drops near-identical questions. It runs *after*
  generation, so the guarantee is "no duplicates," not "always exactly N questions."
- **No database.** Plans aren't persisted server-side — simpler to run and deploy, at the
  cost of no history. Export-to-Markdown covers the "save the result" need.
- **Single serverless function on Vercel.** The whole app (API + static) ships as one
  function for deployment simplicity, rather than splitting static hosting from the API.
- **Stateless generation.** Each request is independent (no fine-tuning/embeddings),
  keeping the system easy to reason about and cheap to run.

## AI Tools Used

- **LLM at runtime** — the core feature. The app sends the resume + job description to an
  LLM (default Google Gemini; also Groq, Ollama, OpenAI, or Anthropic) and asks for a
  structured interview plan. Prompt engineering (`SYSTEM_PROMPT` in `app/llm.py`) steers
  the model to identify strengths/gaps, balance question categories and difficulty, write
  rubric-style answer points, and avoid duplicate/irrelevant questions. The response is
  validated against a Pydantic schema.
- **Claude (Anthropic) as a coding assistant** — this project was built with AI pair
  programming. It was used to scaffold the FastAPI backend and UI, design the
  provider-agnostic LLM layer, write the automated tests, and produce the Vercel
  deployment config, with iterative review and manual verification of each step.

## Notes

- Switch providers/models any time with the `LLM_PROVIDER` and `LLM_MODEL` env vars — no code change.
- PDF text extraction works on text-based PDFs; scanned/image PDFs won't yield text (no OCR).
