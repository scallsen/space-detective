import asyncio
import os
import re
from pathlib import Path
from typing import Optional

import pydantic
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from google.antigravity import Agent, LocalAgentConfig
from pydantic import BaseModel

import database

BASE_DIR = Path(__file__).resolve().parent
STORY_DIR = BASE_DIR / "Story"
load_dotenv(BASE_DIR / ".env")


def configure_environment():
    """Normalize env vars used by Antigravity, ADK, and google-genai."""
    gemini_api_key = os.getenv("GEMINI_API_KEY")
    google_api_key = os.getenv("GOOGLE_API_KEY")

    if gemini_api_key and not google_api_key:
        os.environ["GOOGLE_API_KEY"] = gemini_api_key
    elif google_api_key and not gemini_api_key:
        os.environ["GEMINI_API_KEY"] = google_api_key

    os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "FALSE")
    os.environ.setdefault("GOOGLE_GENAI_MODEL", "gemini-3.5-flash")


configure_environment()
database.seed_database(force=False)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RoleAgentResponse(pydantic.BaseModel):
    response: str


class CrewInterrogationResponse(pydantic.BaseModel):
    chief_engineer: str
    technician: str
    botanist: str
    security_guard: str


class InterrogationRequest(BaseModel):
    question: str


ROLE_ORDER = ("Chief Engineer", "Technician", "Botanist", "Security Guard")
ROLE_RESPONSE_KEYS = {
    "Chief Engineer": "chief_engineer",
    "Technician": "technician",
    "Botanist": "botanist",
    "Security Guard": "security_guard",
}
ROLE_PROFILE_FILES = {
    "Chief Engineer": "Chief Engineer.md",
    "Technician": "Technician.md",
    "Botanist": "Botanist.md",
    "Security Guard": "Security Guard.md",
}
ROLE_AGENT_FILES = {
    "Chief Engineer": "Agents/Chief Engineer.md",
    "Technician": "Agents/Technician.md",
    "Botanist": "Agents/Botanist.md",
    "Security Guard": "Agents/Security Guard.md",
}
ROLE_ALIASES = {
    "chief engineer": "Chief Engineer",
    "engineer": "Chief Engineer",
    "technician": "Technician",
    "botanist": "Botanist",
    "security guard": "Security Guard",
    "security": "Security Guard",
    "guard": "Security Guard",
}
MAX_RESPONSE_SENTENCES = 3


def normalize_role(role: str) -> str:
    normalized = ROLE_ALIASES.get(role.strip().lower(), role.strip())
    if normalized not in ROLE_ORDER:
        raise ValueError(f"Unknown role: {role}. Use one of: {', '.join(ROLE_ORDER)}")
    return normalized


def read_story_file(filename: str) -> str:
    path = STORY_DIR / filename
    try:
        return path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return f"[Missing Story/{filename}]"


DB_TOOL_INSTRUCTIONS = """
Database memory rules:
- Your database tools are already scoped to your assigned role.
- The SQLite story database is the source of truth for scenario, character profile, alibi, time, sector, and witness facts.
- Use your database tools before answering factual questions about where you were, what you saw, alibis, time windows, sectors, oxygen alarms, or contradictions.
- You may inspect another role only through get_alibi_for_role, which returns only records visible to your own role.
- If a tool returns no visible evidence, answer with uncertainty instead of inventing a fact.
- Keep all database, SQL, table, tool, and hidden flag details off-screen. The captain should hear natural in-role dialogue only.
- Use two sentences by default. Never return more than three sentences.
"""


def limit_response_sentences(text: str, max_sentences: int = MAX_RESPONSE_SENTENCES) -> str:
    """Cap role dialogue so one agent cannot flood the interrogation UI."""
    clean_text = " ".join(text.strip().split())
    if not clean_text:
        return clean_text

    sentences = re.findall(r"[^.!?]+(?:[.!?]+|$)", clean_text)
    if len(sentences) <= max_sentences:
        return clean_text

    return " ".join(sentence.strip() for sentence in sentences[:max_sentences])


def build_role_system_instructions(role: str) -> str:
    role = normalize_role(role)
    shared_instructions = read_story_file("SystemInstructions.md")
    scenario = read_story_file("Scenario.md")
    role_profile = read_story_file(ROLE_PROFILE_FILES[role])
    role_agent_instructions = read_story_file(ROLE_AGENT_FILES[role])

    return (
        f"{shared_instructions}\n\n"
        "# Scenario\n"
        f"{scenario}\n\n"
        "# Your Role Profile\n"
        f"{role_profile}\n\n"
        "# Your Private Role Instructions\n"
        f"{role_agent_instructions}\n\n"
        "# Output Contract\n"
        "Return a JSON object with one field named `response`. "
        f"The `response` must be only what the {role} says to the captain. "
        "Use two sentences by default and never more than three sentences.\n\n"
        f"{DB_TOOL_INSTRUCTIONS}"
    )


ROLE_SYSTEM_INSTRUCTIONS = {
    role: build_role_system_instructions(role)
    for role in ROLE_ORDER
}


def build_role_bound_tools(role: str) -> list:
    role = normalize_role(role)

    def get_public_scenario() -> dict:
        """Read the public case setup shared by all roles."""
        return database.get_scenario()

    def get_my_profile() -> dict:
        """Read your own role and personality profile."""
        return database.get_my_personality(role)

    def get_my_logs(
        timestamp: Optional[str] = None,
        sector: Optional[str] = None,
        log_type: Optional[str] = None,
        keyword: Optional[str] = None,
    ) -> dict:
        """Read only incident logs visible to your role, with optional filters."""
        return database.get_my_logs(
            role,
            timestamp=timestamp,
            sector=sector,
            log_type=log_type,
            keyword=keyword,
        )

    def get_my_logs_in_time_range(start_time: str, end_time: str) -> dict:
        """Read only logs visible to your role inside a time range."""
        return database.get_logs_in_time_range(role, start_time, end_time)

    def get_alibi_for_role(suspect_role: str) -> dict:
        """Find what your role can truthfully say about another role's alibi."""
        return database.get_alibi(role, normalize_role(suspect_role))

    def get_my_shared_alibi(timestamp: Optional[str] = None) -> dict:
        """Find visible moments where your role was with someone else."""
        return database.get_who_was_with_me(role, timestamp=timestamp)

    def search_my_logs(keyword: str) -> dict:
        """Keyword-search only the logs visible to your role."""
        return database.search_logs(role, keyword)

    return [
        get_public_scenario,
        get_my_profile,
        get_my_logs,
        get_my_logs_in_time_range,
        get_alibi_for_role,
        get_my_shared_alibi,
        search_my_logs,
    ]


async def ask_role_agent(role: str, question: str, api_key: str) -> str:
    role = normalize_role(role)
    config = LocalAgentConfig(
        api_key=api_key,
        model=os.getenv("GOOGLE_GENAI_MODEL", "gemini-3.5-flash"),
        system_instructions=ROLE_SYSTEM_INSTRUCTIONS[role],
        tools=build_role_bound_tools(role),
        response_schema=RoleAgentResponse,
    )

    role_question = (
        f"The captain is interrogating the {role}.\n"
        f"Captain's question: {question}\n\n"
        f"Answer only as the {role}. Use role names, not personal names. "
        "Use two sentences by default and never more than three sentences."
    )

    async with Agent(config=config) as agent:
        response = await agent.chat(role_question)
        structured_data = await response.structured_output()
        if structured_data is None:
            raise RuntimeError(f"{role} failed to return structured output.")
        return limit_response_sentences(structured_data.response)


@app.post("/api/interrogate")
async def interrogate_crew(payload: InterrogationRequest):
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="Set GEMINI_API_KEY or GOOGLE_API_KEY in your environment or .env file.",
        )

    try:
        role_answers = await asyncio.gather(
            *[
                ask_role_agent(role, payload.question, api_key)
                for role in ROLE_ORDER
            ]
        )
        return CrewInterrogationResponse(
            **{
                ROLE_RESPONSE_KEYS[role]: answer
                for role, answer in zip(ROLE_ORDER, role_answers)
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


app.mount("/", StaticFiles(directory=BASE_DIR, html=True), name="static")


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8080"))
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=False)
