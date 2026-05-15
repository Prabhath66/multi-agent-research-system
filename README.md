# 🔬 Multi-Agent AI Research System

> An autonomous research pipeline that turns any topic into a fully written, source-cited report in under 2 minutes — powered by 4 specialised AI agents working in sequence.

---

## What It Does

The Multi-Agent AI Research System is an end-to-end research pipeline that transforms any topic into a fully written, source-cited research report in under 2 minutes. Instead of relying on a single AI prompt to do everything, the system uses four specialised agents — each with one clearly defined job — orchestrated by a LangGraph state machine.

The **Planner** breaks the topic into focused sub-questions. The **Researcher** searches the live web for each question simultaneously using parallel threads. The **Analyst** organises findings into themes and rates confidence. The **Writer** produces a polished markdown report with executive summary, key findings, detailed analysis, conclusion, and cited sources. Users watch each agent work in real time through a live-updating Streamlit UI.

---

## Demo

```
Topic: "Impact of artificial intelligence on healthcare in 2024"

🧠 Planner    → Done (4.2s)    — Generated 5 sub-questions
🔍 Researcher → Done (28.7s)   — Found 18 sources across 5 searches
📊 Analyst    → Done (11.3s)   — Identified 5 themes with confidence ratings
✍️  Writer     → Done (19.1s)  — Wrote full report with sources

✅ Research complete in 63.3 seconds
```

---

## Architecture

```
User Input (topic)
        │
        ▼
┌───────────────┐
│  🧠 Planner   │  Gemini API call #1
│               │  Breaks topic into 3–5 focused sub-questions
└──────┬────────┘
       │
       ▼
┌───────────────┐
│ 🔍 Researcher │  Tavily API calls #1–5  (parallel, ThreadPoolExecutor)
│               │  Gemini API call #2     (extracts findings from results)
└──────┬────────┘
       │
       ▼
┌───────────────┐
│  📊 Analyst   │  Gemini API call #3
│               │  Groups findings into themes, rates confidence
└──────┬────────┘
       │
       ▼
┌───────────────┐
│  ✍️  Writer    │  Gemini API call #4
│               │  Writes final markdown report with sources
└───────────────┘
        │
        ▼
  reports/{id}_topic.md  (saved to disk)
```

**Total per research job:** 4 Gemini API calls + 3–5 Tavily API calls

---

## Tech Stack

| Category | Technology |
|---|---|
| Language | Python 3.11 |
| AI Orchestration | LangGraph, LangChain |
| LLM | Google Gemini 2.5 Flash |
| Web Search | Tavily Search API |
| Backend | FastAPI, Uvicorn |
| Frontend | Streamlit |
| Concurrency | ThreadPoolExecutor, asyncio, queue.Queue, threading |
| Config | python-dotenv, Pydantic v2 |

---

## Key Features

- **Real-time streaming** — FastAPI SSE streams each agent's progress to the UI the moment it finishes, not after all agents complete
- **Parallel web search** — All sub-questions searched simultaneously using `ThreadPoolExecutor`, cutting search time 5× (30s → 8s)
- **Retry with backoff** — All Gemini and Tavily calls retry up to 3 times with exponential delays (2s, 4s, 8s) on transient errors
- **Prompt injection protection** — User input is sanitised against 8 regex patterns before touching any LLM prompt
- **Memory management** — Job store auto-evicts entries after 1 hour (TTL) and caps at 200 jobs to prevent RAM exhaustion
- **Disk persistence** — Every completed report is saved as a `.md` file in the `reports/` folder automatically
- **Configurable CORS** — Allowed origins set via environment variable, not hardcoded

---

## Report Structure

Every generated report follows this structure:

```
# Research Report: [Topic]

## Executive Summary
## Key Findings
## Detailed Analysis
   ### Theme 1
   ### Theme 2
   ...
## Conclusion
## Sources
```

---

## Project Structure

```
project-root/
├── backend/
│   ├── agents.py        # The 4 AI agents (Planner, Researcher, Analyst, Writer)
│   ├── config.py        # All settings, API keys, and constants
│   ├── graph.py         # LangGraph pipeline — wires agents together
│   ├── main.py          # FastAPI server — HTTP endpoints + SSE streaming
│   ├── tools.py         # Tavily search — parallel web search logic
│   ├── requirements.txt # Backend dependencies
│   └── Procfile         # Render deployment start command
├── frontend/
│   ├── app.py           # Streamlit UI
│   ├── requirements.txt # Frontend dependencies
│   └── Procfile         # Render deployment start command
├── reports/             # Generated research reports saved here
├── .env                 # API keys (not committed to git)
├── requirements.txt     # Full dependencies for local development
└── README.md
```

---

## Getting Started

### Prerequisites

- Python 3.11+
- Google Gemini API key — [aistudio.google.com](https://aistudio.google.com) (free)
- Tavily API key — [tavily.com](https://tavily.com) (free tier: 1000 searches/month)

### 1. Clone the repository

```bash
git clone https://github.com/YOUR_USERNAME/multi-agent-research-system.git
cd multi-agent-research-system
```

### 2. Create and activate a virtual environment

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Mac/Linux
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Set up your API keys

Create a `.env` file in the project root:

```
GOOGLE_API_KEY=your_gemini_api_key_here
TAVILY_API_KEY=your_tavily_api_key_here
```

### 5. Run the backend

```bash
cd backend
uvicorn main:app --reload
```

Backend runs at `http://localhost:8000`

### 6. Run the frontend (new terminal)

```bash
streamlit run frontend/app.py
```

Frontend opens at `http://localhost:8501`

### 7. Use the app

1. Open `http://localhost:8501` in your browser
2. Type a research topic
3. Click **🚀 Research**
4. Watch the 4 agents work in real time
5. Download the finished report as a `.md` file

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/research` | Create a research job, returns `job_id` |
| `GET` | `/research/{job_id}` | SSE stream of live agent progress |
| `GET` | `/research/{job_id}/report` | Poll for the completed report |
| `GET` | `/health` | Server health check |

Auto-generated API docs available at `http://localhost:8000/docs`

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `GOOGLE_API_KEY` | ✅ Yes | — | Gemini API key |
| `TAVILY_API_KEY` | ✅ Yes | — | Tavily Search API key |
| `ALLOWED_ORIGINS` | No | `http://localhost:8501` | Comma-separated allowed CORS origins |
| `BACKEND_URL` | No | `http://localhost:8000` | Backend URL used by the frontend |

---

## Deployment

Both services deploy to [Render](https://render.com) (free tier, no credit card required).

| Service | Root Directory | Start Command |
|---|---|---|
| Backend | `backend` | `uvicorn main:app --host 0.0.0.0 --port $PORT` |
| Frontend | `frontend` | `streamlit run app.py --server.port $PORT --server.address 0.0.0.0 --server.headless true` |

Set these environment variables on Render:
- Backend: `GOOGLE_API_KEY`, `TAVILY_API_KEY`, `ALLOWED_ORIGINS` (your frontend URL)
- Frontend: `BACKEND_URL` (your backend URL)

See `DEPLOYMENT.md` for the complete step-by-step guide.

---

## Built By

**Prabhath Nalla** — AI/ML Engineer · Python Developer · Data Scientist
