# 🔬 Multi-Agent AI Research System

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![LangGraph](https://img.shields.io/badge/LangGraph-Orchestration-1C3C3C?style=flat-square&logo=langchain&logoColor=white)](https://langchain-ai.github.io/langgraph/)
[![Gemini](https://img.shields.io/badge/Gemini%202.5%20Flash-LLM-4285F4?style=flat-square&logo=google&logoColor=white)](https://aistudio.google.com/)
[![FastAPI](https://img.shields.io/badge/FastAPI-Backend-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Streamlit](https://img.shields.io/badge/Streamlit-Frontend-FF4B4B?style=flat-square&logo=streamlit&logoColor=white)](https://streamlit.io/)
[![Tavily](https://img.shields.io/badge/Tavily-Web%20Search-6C47FF?style=flat-square&logoColor=white)](https://tavily.com/)
[![Live App](https://img.shields.io/badge/🚀%20Live%20App-Render-46E3B7?style=flat-square)](https://multi-agent-research-system-x05v.onrender.com)

> **An autonomous AI research pipeline that breaks any topic into sub-questions, searches the live web in parallel, analyses findings, and writes a fully sourced research report — in under 2 minutes.**

---

## 📖 Table of Contents

- [What It Does](#-what-it-does)
- [Live Demo](#-live-demo)
- [Architecture](#-architecture)
- [The Four Agents](#-the-four-agents)
- [Key Features](#-key-features)
- [Tech Stack](#-tech-stack)
- [Project Structure](#-project-structure)
- [Getting Started](#-getting-started)
- [API Reference](#-api-reference)
- [Environment Variables](#-environment-variables)
- [Report Structure](#-report-structure)
- [Deployment](#-deployment)
- [License](#-license)

---

## 🧠 What It Does

The **Multi-Agent AI Research System** replaces the single-prompt approach to AI research with a pipeline of **4 specialised agents**, each with one job, orchestrated by a **LangGraph state machine**. Users type a topic, click Research, and watch each agent work in real time — the finished report arrives in under 2 minutes, complete with citations.

```
"Impact of AI on healthcare in 2025"
        ↓
🧠 Planner   →  5 focused sub-questions                          (4.2s)
🔍 Researcher → 18 sources across 5 parallel web searches       (28.7s)
📊 Analyst   →  5 themes with confidence ratings                (11.3s)
✍️  Writer    →  Full markdown report with executive summary     (19.1s)
                                                          ──────────────
                                                          Total:  63.3s
```

---

## 🎥 Live Demo

The system is live and deployed on [Render](https://render.com):

| Service | URL |
|---|---|
| 🖥️ **Frontend** | [multi-agent-research-system-x05v.onrender.com](https://multi-agent-research-system-x05v.onrender.com) |
| ⚙️ **Backend API** | [research-backend-i8ua.onrender.com](https://research-backend-i8ua.onrender.com) |
| 📖 **API Docs** | [research-backend-i8ua.onrender.com/docs](https://research-backend-i8ua.onrender.com/docs) |

> **Note:** Render free-tier services spin down after inactivity — the first request may take 30–60 seconds to wake up.

**To use the live app:**

1. Open the [frontend](https://multi-agent-research-system-x05v.onrender.com)
2. Enter any research topic
3. Click **🚀 Research**
4. Watch all 4 agents run live with per-agent timing
5. Download the finished `.md` report

---

## 🏗️ Architecture

```
User Input (topic)
        │
        ▼
┌─────────────────┐
│   🧠 Planner    │  Gemini API call #1
│                 │  Breaks topic into 3–5 sub-questions
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  🔍 Researcher  │  Tavily calls #1–5  (parallel, ThreadPoolExecutor)
│                 │  Gemini API call #2  (extracts key findings)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   📊 Analyst    │  Gemini API call #3
│                 │  Groups findings into themes, rates confidence
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│    ✍️  Writer    │  Gemini API call #4
│                 │  Writes final markdown report with citations
└─────────────────┘
         │
         ▼
  reports/{job_id}_{topic}.md   ← saved to disk automatically
```

**Per research job:** 4 Gemini API calls + 3–5 Tavily API calls

The **FastAPI backend** exposes REST + SSE endpoints. The **Streamlit frontend** consumes the SSE stream and updates the UI agent-by-agent in real time.

---

## 🤖 The Four Agents

| Agent | Role | Output |
|---|---|---|
| 🧠 **Planner** | Analyses the topic and generates 3–5 focused sub-questions that cover different angles | List of targeted research questions |
| 🔍 **Researcher** | Runs parallel Tavily web searches for each sub-question using `ThreadPoolExecutor`, then uses Gemini to extract the key findings | Structured findings with source URLs |
| 📊 **Analyst** | Groups findings into themes, identifies patterns, and assigns a confidence rating (High / Medium / Low) to each theme | Thematic analysis with confidence scores |
| ✍️ **Writer** | Synthesises everything into a polished markdown report — executive summary, key findings, detailed analysis, conclusion, and cited sources | Final `.md` research report |

---

## ✨ Key Features

- ⚡ **Real-time SSE Streaming** — FastAPI Server-Sent Events push each agent's result to the Streamlit UI the moment it finishes, not after the full pipeline completes
- 🔀 **Parallel Web Search** — all sub-questions searched simultaneously via `ThreadPoolExecutor`, cutting search time by ~5× (30s → 8s)
- 🔁 **Retry with Exponential Backoff** — all Gemini and Tavily API calls automatically retry up to 3 times (2s → 4s → 8s delays) on transient errors
- 🛡️ **Prompt Injection Protection** — user input sanitised against 8 regex patterns before touching any LLM prompt
- 🧹 **Auto Memory Management** — job store auto-evicts entries after 1 hour (TTL) and caps at 200 concurrent jobs to prevent RAM exhaustion
- 💾 **Disk Persistence** — every completed report auto-saved as a `.md` file in the `reports/` directory
- 🌐 **Configurable CORS** — allowed origins set via environment variable, not hardcoded
- 📄 **Structured Reports** — every report follows a consistent schema: executive summary → key findings → thematic analysis → conclusion → cited sources

---

## 🛠️ Tech Stack

| Category | Technology |
|---|---|
| **Language** | Python 3.11 |
| **AI Orchestration** | LangGraph, LangChain |
| **LLM** | Google Gemini 2.5 Flash |
| **Web Search** | Tavily Search API |
| **Backend** | FastAPI, Uvicorn |
| **Frontend** | Streamlit |
| **Streaming** | Server-Sent Events (SSE) |
| **Concurrency** | `ThreadPoolExecutor`, `asyncio`, `queue.Queue`, `threading` |
| **Config & Validation** | `python-dotenv`, Pydantic v2 |
| **Deployment** | Render (free tier) |

---

## 📁 Project Structure

```
multi-agent-research-system/
│
├── backend/
│   ├── agents.py        # The 4 AI agents — Planner, Researcher, Analyst, Writer
│   ├── config.py        # All settings, API keys, constants, and TTL config
│   ├── graph.py         # LangGraph pipeline — wires agents into a state machine
│   ├── main.py          # FastAPI server — REST + SSE endpoints, job store, CORS
│   ├── tools.py         # Tavily search — parallel web search logic
│   ├── requirements.txt # Backend dependencies
│   └── Procfile         # Render deployment start command
│
├── frontend/
│   ├── app.py           # Streamlit UI — SSE consumer, live agent status, download
│   ├── requirements.txt # Frontend dependencies
│   └── Procfile         # Render deployment start command
│
├── reports/             # Auto-generated research reports saved here as .md files
├── .env                 # API keys — not committed to git
├── .gitignore
├── requirements.txt     # Full dependencies for local development
└── README.md
```

---

## 🚀 Getting Started

### Prerequisites

- Python 3.11 or higher
- A **Google Gemini API key** — free at [aistudio.google.com](https://aistudio.google.com)
- A **Tavily API key** — free tier (1,000 searches/month) at [tavily.com](https://tavily.com)

### 1. Clone the repository

```bash
git clone https://github.com/Prabhath66/multi-agent-research-system.git
cd multi-agent-research-system
```

### 2. Create and activate a virtual environment

```bash
python -m venv venv

# macOS / Linux
source venv/bin/activate

# Windows
venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Set up API keys

Create a `.env` file in the project root:

```env
GOOGLE_API_KEY=your_gemini_api_key_here
TAVILY_API_KEY=your_tavily_api_key_here
ALLOWED_ORIGINS=http://localhost:8501
BACKEND_URL=http://localhost:8000
```

### 5. Start the backend

```bash
cd backend
uvicorn main:app --reload
```

Backend live at → `http://localhost:8000`  
Auto-generated API docs → `http://localhost:8000/docs`

### 6. Start the frontend (new terminal)

```bash
streamlit run frontend/app.py
```

Frontend live at → `http://localhost:8501`

### 7. Research something

1. Open `http://localhost:8501`
2. Type any research topic
3. Click **🚀 Research**
4. Watch all 4 agents work with live timing
5. Download the `.md` report

---

## 📡 API Reference

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/research` | Submit a topic — returns `job_id` |
| `GET` | `/research/{job_id}` | SSE stream of live agent progress events |
| `GET` | `/research/{job_id}/report` | Poll for the completed markdown report |
| `GET` | `/health` | Server health check |

Full interactive docs available at [research-backend-i8ua.onrender.com/docs](https://research-backend-i8ua.onrender.com/docs) (Swagger UI) or `http://localhost:8000/docs` locally.

### Example Request

```bash
curl -X POST https://research-backend-i8ua.onrender.com/research \
  -H "Content-Type: application/json" \
  -d '{"topic": "impact of quantum computing on cryptography"}'
```

```json
{ "job_id": "a3f91c2d-..." }
```

---

## 🔑 Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `GOOGLE_API_KEY` | ✅ Yes | — | Google Gemini API key |
| `TAVILY_API_KEY` | ✅ Yes | — | Tavily Search API key |
| `ALLOWED_ORIGINS` | No | `http://localhost:8501` | Comma-separated CORS origins |
| `BACKEND_URL` | No | `http://localhost:8000` | Backend URL used by the Streamlit frontend |

---

## 📄 Report Structure

Every generated report follows this consistent schema:

```markdown
# Research Report: [Topic]

## Executive Summary
A concise overview of the research findings.

## Key Findings
Bullet-point highlights from across all sources.

## Detailed Analysis
### Theme 1 — [confidence: High/Medium/Low]
### Theme 2 — [confidence: High/Medium/Low]
...

## Conclusion
Synthesis and implications.

## Sources
- [Source Title](URL)
- ...
```

---

## ☁️ Deployment

Both services are deployed independently on [Render](https://render.com) — free tier, no credit card required.

| Service | Root Directory | Deployed URL |
|---|---|---|
| **Backend** | `backend` | [research-backend-i8ua.onrender.com](https://research-backend-i8ua.onrender.com) |
| **Frontend** | `frontend` | [multi-agent-research-system-x05v.onrender.com](https://multi-agent-research-system-x05v.onrender.com) |

**Start commands used on Render:**

- Backend: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- Frontend: `streamlit run app.py --server.port $PORT --server.address 0.0.0.0 --server.headless true`

**Environment variables set on Render:**

- Backend: `GOOGLE_API_KEY`, `TAVILY_API_KEY`, `ALLOWED_ORIGINS` → `https://multi-agent-research-system-x05v.onrender.com`
- Frontend: `BACKEND_URL` → `https://research-backend-i8ua.onrender.com`

> Deploy the backend first, copy its URL, then set it as `BACKEND_URL` when creating the frontend service.

---

## 📄 License

This project is open-source and available under the [MIT License](LICENSE).

---

Made with ❤️ and 🤖 by [Prabhath66](https://github.com/Prabhath66)

⭐ **If this project helped you, drop a star!** ⭐
