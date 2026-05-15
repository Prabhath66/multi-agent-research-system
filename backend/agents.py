# agents.py
# This file contains the 4 AI agents that do the actual research work.
# Each agent has one specific job — Planner breaks the topic into questions,
# Researcher searches the web, Analyst organises findings, Writer writes the report.
# They run one after another, each passing their output to the next.

import re
import time
import logging
from typing import Any
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage

from config import (
    GOOGLE_API_KEY,
    GEMINI_MODEL,
    GEMINI_TEMPERATURE,
    GEMINI_MAX_TOKENS,
    MAX_SEARCH_QUERIES,
    LLM_MAX_RETRIES,
    LLM_RETRY_BASE_DELAY,
)
from tools import run_research_searches, format_results_for_agent

logger = logging.getLogger(__name__)

# One shared Gemini model instance — all 4 agents use this same object
llm = ChatGoogleGenerativeAI(
    model=GEMINI_MODEL,
    google_api_key=GOOGLE_API_KEY,
    temperature=GEMINI_TEMPERATURE,
    max_output_tokens=GEMINI_MAX_TOKENS,
)

# Maximum length we allow for a research topic
MAX_TOPIC_LENGTH = 500

# Patterns that look like someone trying to hijack the AI with fake instructions
INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"disregard\s+(all\s+)?previous",
    r"you\s+are\s+now\s+a",
    r"new\s+instructions?:",
    r"system\s*prompt",
    r"<\s*/?system\s*>",
    r"\[INST\]",
    r"###\s*instruction",
]
INJECTION_RE = re.compile("|".join(INJECTION_PATTERNS), re.IGNORECASE)


def sanitise_topic(topic: str) -> str:
    """
    Cleans up the user's research topic before it touches any AI prompt.
    Trims whitespace, cuts it to 500 characters, removes invisible control
    characters, and blocks any text that looks like a prompt injection attack.
    """
    topic = topic.strip()[:MAX_TOPIC_LENGTH]

    if INJECTION_RE.search(topic):
        raise ValueError(
            "Topic contains disallowed content. "
            "Please enter a genuine research topic."
        )

    topic = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", topic)

    if not topic:
        raise ValueError("Topic cannot be empty after sanitisation.")

    return topic


def call_llm(system_prompt: str, user_message: str) -> str:
    """
    Sends a message to Gemini and returns the response text.
    If the call fails due to a temporary issue (like a rate limit), it waits
    and tries again — up to 3 times with increasing delays (2s, 4s, 8s).
    """
    last_exc: Exception | None = None

    for attempt in range(1, LLM_MAX_RETRIES + 1):
        try:
            response = llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_message),
            ])
            return response.content.strip()

        except Exception as exc:
            last_exc = exc
            error_str = str(exc).lower()

            # These errors won't get better with retrying, so stop immediately
            permanent = ["api key", "invalid", "permission", "not found", "400", "401", "403"]
            if any(p in error_str for p in permanent):
                logger.error("Permanent LLM error (no retry): %s", exc)
                raise

            if attempt < LLM_MAX_RETRIES:
                delay = LLM_RETRY_BASE_DELAY * (2 ** (attempt - 1))
                logger.warning(
                    "LLM call failed (attempt %d/%d), retrying in %.1fs: %s",
                    attempt, LLM_MAX_RETRIES, delay, exc,
                )
                time.sleep(delay)
            else:
                logger.error("LLM call failed after %d attempts: %s", LLM_MAX_RETRIES, exc)

    raise RuntimeError(f"LLM call failed after {LLM_MAX_RETRIES} attempts: {last_exc}")


# System prompt that tells Gemini how to behave as the Planner agent
PLANNER_SYSTEM_PROMPT = """You are a Research Planner. Your only job is to decompose a research topic into focused sub-questions.

RULES:
- Generate exactly 3 to 5 sub-questions (never fewer, never more).
- Each sub-question must be specific and searchable — not vague.
- Together the sub-questions must cover the topic comprehensively.
- Sub-questions must be DIFFERENT from each other — no overlap.
- Do NOT answer the questions. Do NOT search. Only plan.
- Format: Return ONLY a numbered list like this:
  1. [sub-question]
  2. [sub-question]
  ...

BAD example (too vague): "What is AI?"
GOOD example (specific): "What are the main industrial applications of generative AI in 2024?"
"""


def run_planner(topic: str) -> dict[str, Any]:
    """
    Takes the user's research topic and breaks it into 3 to 5 focused questions.
    First sanitises the topic to block any harmful input, then asks Gemini to
    generate the questions, and finally parses them into a clean Python list.
    """
    clean_topic = sanitise_topic(topic)
    user_message = f"Research topic: {clean_topic}\n\nGenerate the sub-questions now."
    output = call_llm(PLANNER_SYSTEM_PROMPT, user_message)

    sub_questions = parse_numbered_list(output)
    sub_questions = sub_questions[:MAX_SEARCH_QUERIES]

    return {
        "output": output,
        "sub_questions": sub_questions,
    }


def parse_numbered_list(text: str) -> list[str]:
    """
    Pulls out the items from a numbered list like '1. Question one\\n2. Question two'.
    Goes through each line, finds the ones that start with a number and a dot,
    and returns just the text after the number as a clean Python list.
    """
    lines = text.strip().split("\n")
    items = []
    for line in lines:
        match = re.match(r"^\s*\d+\.\s+(.+)", line)
        if match:
            items.append(match.group(1).strip())
    return items if items else [text]


# System prompt that tells Gemini how to behave as the Researcher agent
RESEARCHER_SYSTEM_PROMPT = """You are a Research Specialist. You have been given raw search results from the web.

Your job:
1. Read through ALL search results carefully.
2. Extract the most important facts, statistics, quotes, and data points.
3. Note the source URL for every fact you extract.
4. Identify which sub-question each fact answers.
5. Flag any gaps — sub-questions with little or no useful search results.

OUTPUT FORMAT (use this exactly):
## Research Findings

### [Sub-question text]
- [Fact or finding]. Source: [URL]
- [Fact or finding]. Source: [URL]
...

### [Next sub-question]
...

## Gaps Identified
- [Any topic not well covered by search results]

RULES:
- Be factual. Do not add your own opinions.
- Do not fabricate facts. Only use what is in the search results.
- Include source URLs for every finding.
- Be thorough — extract as much useful information as possible.
"""


def run_researcher(sub_questions: list[str]) -> dict[str, Any]:
    """
    Searches the web for each sub-question (all at the same time, in parallel)
    and then asks Gemini to read through all the results and pull out the key facts.
    Returns both the organised findings text and the raw search results.
    """
    raw_results = run_research_searches(sub_questions)
    formatted = format_results_for_agent(raw_results)

    user_message = (
        f"Sub-questions to research:\n"
        + "\n".join(f"{i+1}. {q}" for i, q in enumerate(sub_questions))
        + f"\n\nSearch results:\n{formatted}\n\n"
        "Extract and organise the research findings now."
    )

    output = call_llm(RESEARCHER_SYSTEM_PROMPT, user_message)

    return {
        "output": output,
        "raw_results": raw_results,
    }


# System prompt that tells Gemini how to behave as the Analyst agent
ANALYST_SYSTEM_PROMPT = """You are a Research Analyst. You receive raw research findings and must produce structured analysis.

Your job:
1. Identify the 3-7 most important THEMES or topics across all findings.
2. Group related facts under each theme.
3. Highlight key statistics and data points.
4. Note any contradictions between sources.
5. Identify remaining knowledge gaps.
6. Rate confidence level for each theme: HIGH / MEDIUM / LOW.

CRITICAL RULES:
- Do NOT write prose paragraphs.
- Do NOT write an introduction or conclusion.
- Use ONLY bullet points and headers.
- Attribute every bullet to its source URL.
- This output goes to a Writer — make it easy for them to write from.

OUTPUT FORMAT:
## Theme: [Theme Name] | Confidence: [HIGH/MEDIUM/LOW]
- [Key insight]. [Source URL]
- [Supporting fact]. [Source URL]
- ⚠️ CONTRADICTION: [Conflicting info if any]. Sources: [URLs]

## Theme: [Next Theme]
...

## Knowledge Gaps
- [Topic not covered]
- [Question that remains unanswered]
"""


def run_analyst(research_findings: str) -> dict[str, Any]:
    """
    Takes the raw research findings from the Researcher and organises them into themes.
    Groups related facts together, highlights key stats, flags contradictions between
    sources, and rates how confident we are in each theme.
    """
    user_message = (
        f"Raw research findings:\n\n{research_findings}\n\n"
        "Produce the structured thematic analysis now."
    )
    output = call_llm(ANALYST_SYSTEM_PROMPT, user_message)
    return {"output": output}


# System prompt that tells Gemini how to behave as the Writer agent
WRITER_SYSTEM_PROMPT = """You are a Professional Research Writer. You receive structured analysis and must write a polished report.

OUTPUT STRUCTURE (follow exactly):
# Research Report: [Topic]

## Executive Summary
[2-3 sentences capturing the most important overall finding. Written for a non-expert.]

## Key Findings
1. **[Finding title]**: [1-2 sentence explanation]
2. **[Finding title]**: [1-2 sentence explanation]
3. **[Finding title]**: [1-2 sentence explanation]
[Add up to 5 total]

## Detailed Analysis

### [Theme 1 Name]
[2-3 paragraphs of professional prose synthesising the bullet points from the analysis. Clear language, no jargon.]

### [Theme 2 Name]
...

[Cover all themes from the analysis]

## Conclusion
[1 paragraph. Synthesise the overall picture. Note what remains uncertain. Avoid repetition of Key Findings.]

## Sources
- [Title or description]. [URL]
- [Title or description]. [URL]
[List all unique URLs mentioned in the analysis]

WRITING RULES:
- Use clear, direct language. No jargon.
- Write for an intelligent non-expert reader.
- Do not invent facts not present in the analysis.
- Every claim in Detailed Analysis must be traceable to the analysis input.
- The Sources section must list every URL from the analysis.
"""


def run_writer(analysis: str, topic: str) -> dict[str, Any]:
    """
    Takes the Analyst's structured bullet-point analysis and turns it into a
    polished, readable research report with an executive summary, key findings,
    detailed sections per theme, a conclusion, and a full list of sources.
    """
    user_message = (
        f"Research topic: {topic}\n\n"
        f"Structured analysis:\n\n{analysis}\n\n"
        "Write the complete research report now."
    )
    output = call_llm(WRITER_SYSTEM_PROMPT, user_message)
    return {"output": output}
