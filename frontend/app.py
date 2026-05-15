# app.py
# This is the Streamlit frontend — the web UI that users interact with.
# It talks to the FastAPI backend over HTTP, shows the 4 agent cards updating
# in real time as each agent finishes, and renders the final research report.
# The frontend has no AI logic — it's purely a display layer.

import json
import requests
import streamlit as st
import os

st.set_page_config(
    page_title="Multi-Agent Research System",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Backend URL — defaults to localhost for local dev, override with BACKEND_URL env var for deployment
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")


# Custom CSS for the dark-themed UI
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

    html, body, [class*="css"] {
        font-family: 'Space Grotesk', sans-serif;
    }

    .main-header {
        text-align: center;
        padding: 2rem 0 1rem;
    }

    .main-title {
        font-size: 2.5rem;
        font-weight: 700;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.25rem;
    }

    .main-subtitle {
        font-size: 1rem;
        color: #888;
        margin-bottom: 2rem;
    }

    .agent-card {
        border-radius: 12px;
        padding: 1rem 1.25rem;
        margin-bottom: 0.75rem;
        border: 1px solid;
        transition: all 0.3s ease;
    }

    .agent-waiting {
        background: #1a1a2e;
        border-color: #2d2d4e;
        opacity: 0.6;
    }

    .agent-running {
        background: #0d1b2a;
        border-color: #4a90e2;
        box-shadow: 0 0 12px rgba(74, 144, 226, 0.3);
        opacity: 1;
    }

    .agent-success {
        background: #0a1f0a;
        border-color: #22c55e;
        opacity: 1;
    }

    .agent-error {
        background: #1f0a0a;
        border-color: #ef4444;
        opacity: 1;
    }

    .agent-name {
        font-size: 1.05rem;
        font-weight: 600;
        margin-bottom: 0.2rem;
    }

    .agent-status-text {
        font-size: 0.8rem;
        color: #aaa;
    }

    .stat-box {
        background: #12121f;
        border: 1px solid #2d2d4e;
        border-radius: 8px;
        padding: 0.75rem 1rem;
        text-align: center;
    }

    .stat-value {
        font-size: 1.4rem;
        font-weight: 700;
        color: #667eea;
    }

    .stat-label {
        font-size: 0.75rem;
        color: #888;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }

    .report-container {
        background: #0f0f1a;
        border: 1px solid #2d2d4e;
        border-radius: 12px;
        padding: 2rem;
    }

    .source-pill {
        display: inline-block;
        background: #1a1a2e;
        border: 1px solid #2d2d4e;
        border-radius: 20px;
        padding: 0.2rem 0.75rem;
        font-size: 0.8rem;
        margin: 0.2rem;
        color: #667eea;
        text-decoration: none;
    }

    stButton button {
        background: linear-gradient(135deg, #667eea, #764ba2);
        border: none;
        color: white;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)


# The 4 agents shown in the UI — their keys match what the backend sends
AGENTS = [
    {"key": "planner",    "label": "🧠 Planner",    "desc": "Breaks topic into focused sub-questions"},
    {"key": "researcher", "label": "🔍 Researcher",  "desc": "Searches the web for each sub-question"},
    {"key": "analyst",    "label": "📊 Analyst",     "desc": "Groups findings into themes"},
    {"key": "writer",     "label": "✍️  Writer",      "desc": "Writes the final report"},
]


def render_agent_card(placeholder, agent: dict, state: str, output: str = "", elapsed: float = 0):
    """
    Draws a single agent card into a Streamlit placeholder element.
    The card changes colour and icon based on the agent's state: waiting (grey),
    running (blue glow), success (green), or error (red). If the agent has output,
    it shows a collapsible 'View output' section below the card.
    """
    css_class   = f"agent-{state}"
    icon        = {"waiting": "⬜", "running": "🔵", "success": "✅", "error": "❌"}.get(state, "⬜")
    status_text = {"waiting": "Waiting...", "running": "Working...", "success": f"Done ({elapsed:.1f}s)", "error": "Failed"}.get(state, "")

    html = f"""
    <div class="agent-card {css_class}">
        <div class="agent-name">{icon} {agent['label']}</div>
        <div class="agent-status-text">{agent['desc']} · {status_text}</div>
    </div>
    """
    placeholder.markdown(html, unsafe_allow_html=True)

    if output and state in ("success", "error"):
        with placeholder.expander("View output", expanded=False):
            st.markdown(output)


def start_research_job(topic: str) -> str | None:
    """
    Sends the research topic to the backend to create a new job.
    The backend returns a unique job ID that we use to connect to the SSE stream.
    Returns None and shows an error message if the request fails.
    """
    try:
        resp = requests.post(
            f"{BACKEND_URL}/research",
            json={"topic": topic},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()["job_id"]
    except Exception as exc:
        st.error(f"Failed to start research job: {exc}")
        return None


def stream_and_update(job_id: str, card_placeholders: list, stats_placeholder):
    """
    Connects to the backend SSE stream and updates the UI as each agent finishes.
    Reads one JSON event per agent from the stream, updates that agent's card to
    show it's done, marks the next agent as running, and updates the stats box.
    Returns the final report text, total elapsed time, and any errors when done.
    """
    url          = f"{BACKEND_URL}/research/{job_id}"
    final_report = ""
    cumulative   = 0.0
    errors       = []
    agent_states  = {a["key"]: "waiting" for a in AGENTS}
    agent_outputs = {a["key"]: "" for a in AGENTS}
    agent_elapsed = {a["key"]: 0.0 for a in AGENTS}

    # Show the Planner as running right away while we wait for the first event
    agent_states["planner"] = "running"
    for i, agent in enumerate(AGENTS):
        render_agent_card(card_placeholders[i], agent, agent_states[agent["key"]])

    try:
        with requests.get(url, stream=True, timeout=300) as resp:
            for raw_line in resp.iter_lines():
                if not raw_line:
                    continue
                line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
                if not line.startswith("data: "):
                    continue

                try:
                    event = json.loads(line[6:])  # strip the "data: " prefix
                except json.JSONDecodeError:
                    continue

                if event.get("event") == "done":
                    break  # all agents finished, stream is complete

                agent_key  = event.get("agent", "")
                status     = event.get("status", "success")
                output     = event.get("output", "")
                elapsed    = event.get("elapsed", 0.0)    # how long this agent took
                cumulative = event.get("cumulative", 0.0) # total time so far
                errors     = event.get("errors", [])

                if event.get("report"):
                    final_report = event["report"]

                # Update this agent's card and mark the next one as running
                if agent_key in agent_states:
                    agent_states[agent_key]  = status
                    agent_outputs[agent_key] = output
                    agent_elapsed[agent_key] = elapsed

                    keys = [a["key"] for a in AGENTS]
                    if agent_key in keys:
                        idx = keys.index(agent_key)
                        if idx + 1 < len(keys):
                            next_key = keys[idx + 1]
                            if agent_states[next_key] == "waiting":
                                agent_states[next_key] = "running"

                # Redraw all 4 agent cards with their latest states
                for i, agent in enumerate(AGENTS):
                    render_agent_card(
                        card_placeholders[i],
                        agent,
                        agent_states[agent["key"]],
                        agent_outputs[agent["key"]],
                        agent_elapsed[agent["key"]],
                    )

                # Update the stats box with agents done count and total time
                completed = sum(1 for s in agent_states.values() if s == "success")
                stats_placeholder.markdown(
                    f"""
                    <div style="display:flex;gap:1rem;margin:1rem 0;">
                        <div class="stat-box" style="flex:1;">
                            <div class="stat-value">{completed}/4</div>
                            <div class="stat-label">Agents Done</div>
                        </div>
                        <div class="stat-box" style="flex:1;">
                            <div class="stat-value">{cumulative:.0f}s</div>
                            <div class="stat-label">Total Elapsed</div>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    except Exception as exc:
        st.error(f"Streaming error: {exc}")

    return final_report, cumulative, errors


# Page header
st.markdown("""
<div class="main-header">
    <div class="main-title">🔬 Multi-Agent Research System</div>
    <div class="main-subtitle">4 specialised AI agents collaborate to research any topic in real time</div>
</div>
""", unsafe_allow_html=True)

# Topic input and research button
col_input, col_btn = st.columns([5, 1])
with col_input:
    topic = st.text_input(
        "Research Topic",
        placeholder="e.g. The impact of quantum computing on modern cryptography",
        label_visibility="collapsed",
    )
with col_btn:
    start = st.button("🚀 Research", use_container_width=True, type="primary")

st.caption("💡 Try: *Future of renewable energy storage* · *AI regulation in 2024* · *CRISPR gene editing breakthroughs*")
st.divider()

# Agent pipeline section — 4 cards side by side
st.markdown("### 🤖 Agent Pipeline")
st.caption("Each agent has a single responsibility. Watch them work in sequence.")

card_cols = st.columns(4)
card_placeholders = []
for i, (col, agent) in enumerate(zip(card_cols, AGENTS)):
    with col:
        ph = st.empty()
        render_agent_card(ph, agent, "waiting")
        card_placeholders.append(ph)

stats_placeholder  = st.empty()
report_placeholder = st.empty()

# When the user clicks Research
if start and topic.strip():
    # Reset all cards to waiting state
    for i, agent in enumerate(AGENTS):
        render_agent_card(card_placeholders[i], agent, "waiting")
    report_placeholder.empty()

    # Create the job on the backend
    job_id = start_research_job(topic.strip())
    if not job_id:
        st.stop()

    st.toast(f"Research job started: {job_id[:8]}...", icon="🚀")

    # Stream agent progress and update the UI in real time
    final_report, total_time, errors = stream_and_update(job_id, card_placeholders, stats_placeholder)

    # Show the finished report
    if final_report:
        st.success(f"✅ Research complete in {total_time:.1f} seconds!")

        with report_placeholder.container():
            st.markdown("---")
            st.markdown("## 📄 Research Report")

            st.download_button(
                label="⬇️ Download Report (.md)",
                data=final_report,
                file_name=f"research_{topic[:30].replace(' ', '_')}.md",
                mime="text/markdown",
            )

            with st.container():
                st.markdown(final_report)

    elif errors:
        st.error("Research failed:\n" + "\n".join(f"• {e}" for e in errors))

elif start and not topic.strip():
    st.warning("Please enter a research topic first.")


# Sidebar with architecture info and settings
with st.sidebar:
    st.markdown("### 🏗️ Architecture")
    st.markdown("""
**Flow:**
```
Topic Input
    ↓
🧠 Planner      → Sub-questions
    ↓
🔍 Researcher   → Web search (Tavily)
    ↓
📊 Analyst      → Thematic analysis
    ↓
✍️  Writer       → Markdown report
```

**Why 4 agents?**
- Each agent has ONE job
- Failures are isolated
- Outputs are inspectable
- Easy to upgrade individually

**Powered by:**
- LangGraph state machine
- Google Gemini 2.5 Flash
- Tavily Search API
- FastAPI + SSE streaming
    """)

    st.markdown("### ⚙️ Settings")
    st.caption(f"Backend: `{BACKEND_URL}`")

    if st.button("🔍 Health Check"):
        try:
            r = requests.get(f"{BACKEND_URL}/health", timeout=5)
            st.json(r.json())
        except Exception as exc:
            st.error(f"Backend unreachable: {exc}")
