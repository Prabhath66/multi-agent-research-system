# config.py
# This is the central settings file for the whole project.
# Every other file imports its settings from here — API keys, model names,
# timeouts, limits — so there's only one place to change things.

import os
from pathlib import Path
from dotenv import load_dotenv

# Find the project root folder and load the .env file from there
BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"
load_dotenv(dotenv_path=ENV_PATH)

# API Keys — loaded from .env file, never hardcoded
GOOGLE_API_KEY: str = os.getenv("GOOGLE_API_KEY", "")
TAVILY_API_KEY: str = os.getenv("TAVILY_API_KEY", "")

# Stop the server immediately if either key is missing
if not GOOGLE_API_KEY:
    raise EnvironmentError(
        "GOOGLE_API_KEY is not set. Add it to your .env file.\n"
        "Get a free key at: https://aistudio.google.com"
    )

if not TAVILY_API_KEY:
    raise EnvironmentError(
        "TAVILY_API_KEY is not set. Add it to your .env file.\n"
        "Get a free key at: https://tavily.com"
    )

# Gemini model settings
GEMINI_MODEL: str       = "gemini-2.5-flash"
GEMINI_TEMPERATURE: float = 0.4    # lower means more factual, less creative
GEMINI_MAX_TOKENS: int  = 8192

# Tavily search settings
TAVILY_MAX_RESULTS: int  = 5        # how many results to fetch per question
TAVILY_SEARCH_DEPTH: str = "basic"  # "basic" is faster, "advanced" is deeper

# LangGraph pipeline settings
MAX_SEARCH_QUERIES: int    = 5   # max number of sub-questions the Planner can generate
GRAPH_RECURSION_LIMIT: int = 50  # safety cap to prevent infinite loops in the graph

# Retry settings — how many times to retry a failed API call and how long to wait
LLM_MAX_RETRIES: int        = 3    # retry Gemini up to 3 times
LLM_RETRY_BASE_DELAY: float = 2.0  # wait 2s, then 4s, then 8s between retries
TAVILY_MAX_RETRIES: int     = 3    # retry Tavily up to 3 times
TAVILY_RETRY_BASE_DELAY: float = 1.0  # wait 1s, then 2s, then 4s between retries

# Job store memory limits — prevents the server from running out of RAM
JOB_MAX_AGE_SECONDS: int = 3600  # delete jobs from memory after 1 hour
JOB_MAX_COUNT: int       = 200   # never keep more than 200 jobs in memory at once

# FastAPI server settings
API_HOST: str    = "0.0.0.0"
API_PORT: int    = 8000
API_TITLE: str   = "Multi-Agent Research System"
API_VERSION: str = "1.0.0"

# CORS — which websites are allowed to call this backend
# Set ALLOWED_ORIGINS in your .env to restrict access in production
# Example: ALLOWED_ORIGINS=https://myapp.com,https://staging.myapp.com
raw_origins: str = os.getenv("ALLOWED_ORIGINS", "http://localhost:8501")
ALLOWED_ORIGINS: list[str] = [o.strip() for o in raw_origins.split(",") if o.strip()]

# Streamlit frontend URL — used when the frontend needs to know where the backend is
STREAMLIT_BACKEND_URL: str = os.getenv(
    "BACKEND_URL", f"http://localhost:{API_PORT}"
)

# Reports folder — where finished research reports are saved as .md files
REPORTS_DIR: Path = BASE_DIR / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
