# graph.py
# This file wires all 4 agents together into a pipeline using LangGraph.
# LangGraph manages the state (what each agent produced), routes between agents,
# and handles errors — if any agent fails, it routes to the error handler instead
# of crashing the whole pipeline. The graph is compiled once at startup and
# reused for every research job.

import time
import logging
from typing import TypedDict, Any, Optional
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from agents import run_planner, run_researcher, run_analyst, run_writer
from config import GRAPH_RECURSION_LIMIT

logger = logging.getLogger(__name__)


class AgentState(TypedDict):
    """
    The shared data container that gets passed between all 4 agents.
    Each agent reads what it needs and writes only its own output — no agent
    touches another agent's fields. This keeps the pipeline clean and debuggable.
    """
    topic: str           # the original research topic — never changes
    plan: str            # Planner's numbered list of sub-questions
    sub_questions: list[str]  # parsed list of questions for the Researcher
    research: str        # Researcher's structured findings
    analysis: str        # Analyst's themed bullet-point analysis
    report: str          # Writer's final markdown report
    current_agent: str   # which agent is currently running
    agent_outputs: dict[str, Any]  # timing and status info for each agent
    errors: list[str]    # any error messages collected along the way
    step_count: int      # how many agents have finished so far
    start_time: float    # when the whole job started (Unix timestamp)


def record_agent_output(
    state: AgentState,
    agent_name: str,
    output: str,
    status: str,
    agent_start_time: float,
    extra: Optional[dict] = None,
) -> dict:
    """
    Saves an agent's result along with two timing values: how long that specific
    agent took (shown on its card in the UI), and how long the whole job has been
    running so far (shown in the stats box). Returns the updated agent_outputs dict.
    """
    now = time.time()
    agent_elapsed = round(now - agent_start_time, 2)
    cumulative    = round(now - state["start_time"], 2)

    entry = {
        "output":             output,
        "status":             status,
        "elapsed_seconds":    agent_elapsed,
        "cumulative_seconds": cumulative,
    }
    if extra:
        entry.update(extra)

    updated_outputs = dict(state.get("agent_outputs", {}))
    updated_outputs[agent_name] = entry
    return updated_outputs


def planner_node(state: AgentState) -> dict:
    """
    Runs the Planner agent — takes the research topic and breaks it into
    3 to 5 focused sub-questions. If it fails for any reason, the error is
    recorded and the pipeline routes to the error handler instead of crashing.
    """
    agent_start = time.time()
    try:
        result = run_planner(state["topic"])
        if result["output"].startswith("ERROR:"):
            raise RuntimeError(result["output"])

        agent_outputs = record_agent_output(
            state, "planner", result["output"], "success", agent_start,
            extra={"sub_questions": result["sub_questions"]},
        )
        return {
            "plan":          result["output"],
            "sub_questions": result["sub_questions"],
            "current_agent": "researcher",
            "agent_outputs": agent_outputs,
            "step_count":    state.get("step_count", 0) + 1,
        }

    except Exception as exc:
        errors = list(state.get("errors", []))
        errors.append(f"Planner error: {exc}")
        return {
            "errors":        errors,
            "current_agent": "error_handler",
            "agent_outputs": record_agent_output(state, "planner", str(exc), "error", agent_start),
        }


def researcher_node(state: AgentState) -> dict:
    """
    Runs the Researcher agent — searches the web for each sub-question in parallel
    and asks Gemini to extract the key facts from the results. Needs the sub-questions
    from the Planner to be present, otherwise it routes to the error handler.
    """
    agent_start = time.time()
    try:
        sub_questions = state.get("sub_questions", [])
        if not sub_questions:
            raise ValueError("No sub-questions from Planner — cannot search.")

        result = run_researcher(sub_questions)
        if result["output"].startswith("ERROR:"):
            raise RuntimeError(result["output"])

        agent_outputs = record_agent_output(
            state, "researcher", result["output"], "success", agent_start,
            extra={"sources_found": len(result["raw_results"])},
        )
        return {
            "research":      result["output"],
            "current_agent": "analyst",
            "agent_outputs": agent_outputs,
            "step_count":    state.get("step_count", 0) + 1,
        }

    except Exception as exc:
        errors = list(state.get("errors", []))
        errors.append(f"Researcher error: {exc}")
        return {
            "errors":        errors,
            "current_agent": "error_handler",
            "agent_outputs": record_agent_output(state, "researcher", str(exc), "error", agent_start),
        }


def analyst_node(state: AgentState) -> dict:
    """
    Runs the Analyst agent — takes the Researcher's raw findings and groups them
    into themes, highlights key stats, flags contradictions, and rates confidence.
    Needs the research findings to be present, otherwise routes to the error handler.
    """
    agent_start = time.time()
    try:
        research = state.get("research", "")
        if not research:
            raise ValueError("No research findings from Researcher.")

        result = run_analyst(research)
        if result["output"].startswith("ERROR:"):
            raise RuntimeError(result["output"])

        return {
            "analysis":      result["output"],
            "current_agent": "writer",
            "agent_outputs": record_agent_output(state, "analyst", result["output"], "success", agent_start),
            "step_count":    state.get("step_count", 0) + 1,
        }

    except Exception as exc:
        errors = list(state.get("errors", []))
        errors.append(f"Analyst error: {exc}")
        return {
            "errors":        errors,
            "current_agent": "error_handler",
            "agent_outputs": record_agent_output(state, "analyst", str(exc), "error", agent_start),
        }


def writer_node(state: AgentState) -> dict:
    """
    Runs the Writer agent — takes the Analyst's structured bullet-point analysis
    and turns it into a polished markdown report with summary, findings, analysis,
    conclusion, and sources. Needs the analysis to be present to run.
    """
    agent_start = time.time()
    try:
        analysis = state.get("analysis", "")
        if not analysis:
            raise ValueError("No analysis from Analyst.")

        result = run_writer(analysis, state["topic"])
        if result["output"].startswith("ERROR:"):
            raise RuntimeError(result["output"])

        return {
            "report":        result["output"],
            "current_agent": "complete",
            "agent_outputs": record_agent_output(state, "writer", result["output"], "success", agent_start),
            "step_count":    state.get("step_count", 0) + 1,
        }

    except Exception as exc:
        errors = list(state.get("errors", []))
        errors.append(f"Writer error: {exc}")
        return {
            "errors":        errors,
            "current_agent": "error_handler",
            "agent_outputs": record_agent_output(state, "writer", str(exc), "error", agent_start),
        }


def error_handler_node(state: AgentState) -> dict:
    """
    Catches any errors from the pipeline and turns them into a readable error report.
    This node is reached when any agent fails — it collects all the error messages
    and formats them into a markdown report that the UI can display to the user.
    """
    errors = state.get("errors", ["Unknown error"])
    error_report = (
        "# Research Failed\n\n"
        "The research pipeline encountered errors:\n\n"
        + "\n".join(f"- {e}" for e in errors)
        + "\n\nPlease check your API keys and try again."
    )
    return {"report": error_report, "current_agent": "complete"}


def route_after_planner(state: AgentState) -> str:
    """Decides where to go after the Planner — Researcher if all good, error handler if not."""
    return "error_handler" if state.get("errors") else "researcher"


def route_after_researcher(state: AgentState) -> str:
    """Decides where to go after the Researcher — Analyst if all good, error handler if not."""
    return "error_handler" if state.get("errors") else "analyst"


def route_after_analyst(state: AgentState) -> str:
    """Decides where to go after the Analyst — Writer if all good, error handler if not."""
    return "error_handler" if state.get("errors") else "writer"


def build_graph() -> StateGraph:
    """
    Builds and compiles the LangGraph pipeline that connects all 4 agents.
    The flow goes Planner → Researcher → Analyst → Writer, with each step
    able to route to the error handler if something goes wrong.
    """
    graph = StateGraph(AgentState)

    graph.add_node("planner",       planner_node)
    graph.add_node("researcher",    researcher_node)
    graph.add_node("analyst",       analyst_node)
    graph.add_node("writer",        writer_node)
    graph.add_node("error_handler", error_handler_node)

    graph.set_entry_point("planner")

    graph.add_conditional_edges("planner",    route_after_planner,    {"researcher": "researcher", "error_handler": "error_handler"})
    graph.add_conditional_edges("researcher", route_after_researcher, {"analyst":    "analyst",    "error_handler": "error_handler"})
    graph.add_conditional_edges("analyst",    route_after_analyst,    {"writer":     "writer",     "error_handler": "error_handler"})

    graph.add_edge("writer",        END)
    graph.add_edge("error_handler", END)

    return graph.compile(checkpointer=MemorySaver())


# Agent display names and order for the UI
AGENT_ORDER  = ["planner", "researcher", "analyst", "writer"]
AGENT_LABELS = {
    "planner":    "🧠 Planner",
    "researcher": "🔍 Researcher",
    "analyst":    "📊 Analyst",
    "writer":     "✍️  Writer",
}
TOTAL_STEPS = 4

# Build the graph once when the module loads — reused for every research job
# (building it on every request would waste CPU time)
compiled_graph = build_graph()


def build_initial_state(topic: str) -> AgentState:
    """
    Creates a fresh, empty state to kick off a new research job.
    Sets the topic and start time, and leaves everything else blank
    for the agents to fill in as they run.
    """
    return AgentState(
        topic=topic, plan="", sub_questions=[], research="", analysis="",
        report="", current_agent="planner", agent_outputs={}, errors=[],
        step_count=0, start_time=time.time(),
    )


def stream_graph(topic: str, job_id: str):
    """
    Runs the full research pipeline and yields one update event per agent as it finishes.
    Each event contains the agent's name, status, output text, timing, and the final
    report (only populated when the Writer finishes). Used by the SSE endpoint in main.py.
    """
    initial_state = build_initial_state(topic)
    config = {"configurable": {"thread_id": job_id}, "recursion_limit": GRAPH_RECURSION_LIMIT}
    seen_agents: set[str] = set()

    for event in compiled_graph.stream(initial_state, config=config):
        for node_name, node_state in event.items():
            if node_name == "__end__" or node_name in seen_agents:
                continue
            seen_agents.add(node_name)

            agent_info = node_state.get("agent_outputs", {}).get(node_name, {})
            step_num   = AGENT_ORDER.index(node_name) + 1 if node_name in AGENT_ORDER else TOTAL_STEPS

            yield {
                "job_id":        job_id,
                "agent":         node_name,
                "agent_label":   AGENT_LABELS.get(node_name, node_name.title()),
                "status":        agent_info.get("status", "success"),
                "output":        agent_info.get("output", ""),
                "step":          step_num,
                "total_steps":   TOTAL_STEPS,
                "elapsed":       agent_info.get("elapsed_seconds", 0),
                "cumulative":    agent_info.get("cumulative_seconds", 0),
                "report":        node_state.get("report", ""),
                "errors":        node_state.get("errors", []),
                "sub_questions": node_state.get("sub_questions", []),
            }
