# main.py
# This is the FastAPI backend server — the brain of the operation.
# It exposes 4 HTTP endpoints that the Streamlit frontend calls.
# The most important one is the SSE stream endpoint which pushes live
# agent progress to the UI as each agent finishes its work.

import json
import uuid
import asyncio
import queue
import threading
import time
import logging
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from config import (
    API_TITLE,
    API_VERSION,
    ALLOWED_ORIGINS,
    JOB_MAX_AGE_SECONDS,
    JOB_MAX_COUNT,
    REPORTS_DIR,
)
from graph import stream_graph

# Set up logging so we can see what's happening in the server logs
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Create the FastAPI app
app = FastAPI(title=API_TITLE, version=API_VERSION)

# Only allow requests from the configured frontend URL — not from random websites
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Accept"],
)

# In-memory store for active research jobs
# Each entry holds the job status, topic, report, errors, and timing
# Jobs are automatically cleaned up after 1 hour or when the store gets too full
job_store: dict[str, dict] = {}


def evict_expired_jobs() -> None:
    """
    Removes any jobs from memory that are older than JOB_MAX_AGE_SECONDS (1 hour).
    This runs before every new job is created to keep memory usage under control.
    Old jobs are already saved to disk as .md files, so nothing is lost.
    """
    now = time.time()
    expired = [
        jid for jid, job in job_store.items()
        if now - job.get("start_time", now) > JOB_MAX_AGE_SECONDS
    ]
    for jid in expired:
        logger.info("Evicting expired job %s", jid)
        del job_store[jid]


def evict_oldest_if_full() -> None:
    """
    If the job store has hit its maximum size (200 jobs), removes the oldest one
    to make room for the new one. This prevents the server from running out of RAM
    if a lot of research jobs are created in a short period of time.
    """
    while len(job_store) >= JOB_MAX_COUNT:
        oldest = next(iter(job_store))
        logger.info("Job store full — evicting oldest job %s", oldest)
        del job_store[oldest]


def save_report_to_disk(job_id: str, topic: str, report: str) -> None:
    """
    Saves the finished research report as a .md file in the reports/ folder.
    The filename includes the first 8 characters of the job ID and the topic name.
    If the save fails for any reason (e.g. disk full), it just logs a warning
    and moves on — a disk error should never break the API response.
    """
    try:
        safe_topic = "".join(c if c.isalnum() or c in " _-" else "_" for c in topic)[:40]
        filename   = f"{job_id[:8]}_{safe_topic.strip().replace(' ', '_')}.md"
        path       = REPORTS_DIR / filename
        path.write_text(report, encoding="utf-8")
        logger.info("Report saved → %s", path)
    except Exception as exc:
        logger.warning("Failed to save report to disk: %s", exc)


# Request and response data models — Pydantic validates these automatically
class ResearchRequest(BaseModel):
    topic: str = Field(..., min_length=3, max_length=500)


class ResearchResponse(BaseModel):
    job_id: str
    message: str
    stream_url: str


class ReportResponse(BaseModel):
    job_id: str
    status: str           # "pending" | "complete" | "error"
    report: Optional[str]
    errors: list[str]
    elapsed_seconds: Optional[float]


@app.get("/health")
def health_check():
    """
    Simple health check endpoint — returns OK if the server is running.
    Also shows how many jobs are currently in memory and where reports are saved.
    Useful for verifying the deployment is working correctly.
    """
    return {
        "status":      "ok",
        "version":     API_VERSION,
        "active_jobs": len(job_store),
        "reports_dir": str(REPORTS_DIR),
    }


@app.post("/research", response_model=ResearchResponse)
def start_research(request: ResearchRequest):
    """
    Creates a new research job and returns a unique job ID.
    The actual research doesn't start here — it starts when the frontend
    connects to the SSE stream endpoint using the returned job ID.
    Also cleans up old jobs before creating the new one.
    """
    evict_expired_jobs()
    evict_oldest_if_full()

    job_id = str(uuid.uuid4())
    job_store[job_id] = {
        "status":        "pending",
        "topic":         request.topic,
        "report":        "",
        "errors":        [],
        "agent_outputs": {},
        "start_time":    time.time(),
    }
    logger.info("Created job %s — topic: %s", job_id[:8], request.topic[:60])

    return ResearchResponse(
        job_id=job_id,
        message=f"Research job created for: '{request.topic}'",
        stream_url=f"/research/{job_id}",
    )


@app.get("/research/{job_id}")
async def stream_research(job_id: str):
    """
    The main SSE streaming endpoint — runs the research pipeline and pushes
    one update event to the frontend each time an agent finishes its work.
    LangGraph runs in a background thread and puts results into a queue;
    this async function reads from the queue and streams them to the client.
    """
    if job_id not in job_store:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    topic = job_store[job_id]["topic"]

    async def event_generator():
        event_queue: queue.Queue = queue.Queue()

        def run_stream():
            # This runs in a background thread — LangGraph is synchronous
            # so it can't run directly in the async event loop
            try:
                for update in stream_graph(topic, job_id):
                    event_queue.put(update)
            except Exception as exc:
                logger.error("stream_graph error for job %s: %s", job_id[:8], exc)
                event_queue.put({
                    "agent": "error_handler", "agent_label": "❌ Error",
                    "status": "error", "output": str(exc),
                    "step": 0, "total_steps": 4,
                    "elapsed": 0, "cumulative": 0,
                    "report": "", "errors": [str(exc)],
                })
            finally:
                event_queue.put(None)  # None signals that all agents are done

        stream_thread = threading.Thread(target=run_stream, daemon=True)
        stream_thread.start()

        # Keep reading from the queue and sending events to the frontend
        while True:
            try:
                update = event_queue.get_nowait()
            except queue.Empty:
                await asyncio.sleep(0.05)  # briefly yield control to the event loop
                continue

            if update is None:
                break  # all agents are done

            # Update the job store with the latest agent result
            if update.get("report"):
                job_store[job_id]["report"] = update["report"]
            if update.get("errors"):
                job_store[job_id]["errors"] = update["errors"]
            agent_name = update.get("agent", "unknown")
            job_store[job_id]["agent_outputs"][agent_name] = {
                "output": update.get("output", ""),
                "status": update.get("status", "success"),
            }

            # Send this agent's event to the frontend right away
            yield f"data: {json.dumps(update, ensure_ascii=False)}\n\n"

        stream_thread.join()

        # Mark the job as complete and record how long it took
        job_store[job_id]["status"] = "complete"
        job_store[job_id]["elapsed_seconds"] = round(
            time.time() - job_store[job_id]["start_time"], 2
        )

        # Save the report to disk as a .md file
        final_report = job_store[job_id].get("report", "")
        if final_report and not final_report.startswith("# Research Failed"):
            save_report_to_disk(job_id, topic, final_report)

        logger.info("Job %s complete in %.1fs", job_id[:8], job_store[job_id]["elapsed_seconds"])

        # Send a final "done" event so the frontend knows the stream is finished
        yield f"data: {json.dumps({'event': 'done', 'job_id': job_id})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":     "no-cache",
            "X-Accel-Buffering": "no",
            "Connection":        "keep-alive",
        },
    )


@app.get("/research/{job_id}/report", response_model=ReportResponse)
def get_report(job_id: str):
    """
    Returns the current status and report for a given job ID immediately.
    The frontend can call this to check if a job is done without using the SSE stream.
    Returns 'pending' while the job is still running, 'complete' when it's done.
    """
    if job_id not in job_store:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    job = job_store[job_id]
    return ReportResponse(
        job_id=job_id,
        status=job.get("status", "pending"),
        report=job.get("report") or None,
        errors=job.get("errors", []),
        elapsed_seconds=job.get("elapsed_seconds"),
    )


if __name__ == "__main__":
    import uvicorn
    from config import API_HOST, API_PORT
    uvicorn.run("main:app", host=API_HOST, port=API_PORT, reload=True)
