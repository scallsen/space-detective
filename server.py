import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import pydantic
from google.antigravity import Agent, LocalAgentConfig

app = FastAPI()

# Enable CORS so your browser frontend can talk to the backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Enforce structured output from the crew
class CrewInterrogationResponse(pydantic.BaseModel):
    elena: str
    marcus: str
    chen: str
    jax: str

class InterrogationRequest(BaseModel):
    question: str

# Load the system instructions from docs/GAMEPLAY_PROMPT.md
def load_system_instructions():
    try:
        # Resolve path relative to this file
        base_dir = os.path.dirname(os.path.abspath(__file__))
        prompt_path = os.path.join(base_dir, "docs", "GAMEPLAY_PROMPT.md")
        with open(prompt_path, "r") as f:
            content = f.read()
            return content
    except FileNotFoundError:
        # Fallback if docs/GAMEPLAY_PROMPT.md is missing or run from another dir
        return "You are playing the role of four space station crew members. The oxygen line was cut in Sector 7 at 04:15. Characters: Elena, Marcus, Dr. Chen, Jax (who is the saboteur and lies about being with Dr. Chen)."

SYSTEM_INSTRUCTION = load_system_instructions()

@app.post("/api/interrogate")
async def interrogate_crew(payload: InterrogationRequest):
    # Retrieve Gemini API Key from environment
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=500, 
            detail="GEMINI_API_KEY environment variable is not set. Please get a key at https://aistudio.google.com/app/api-keys and export it."
        )
    
    # Configure the Antigravity Agent
    config = LocalAgentConfig(
        api_key=api_key,
        system_instruction=SYSTEM_INSTRUCTION,
        response_schema=CrewInterrogationResponse
    )
    
    try:
        # Run agent transaction
        async with Agent(config=config) as agent:
            response = await agent.chat(payload.question)
            structured_data = await response.structured_output()
            if structured_data is None:
                raise HTTPException(status_code=500, detail="Failed to parse structured JSON from model.")
            return structured_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Serve the static frontend (index.html, app.js, style.css) — must come after API routes
_base_dir = os.path.dirname(os.path.abspath(__file__))
app.mount("/", StaticFiles(directory=_base_dir, html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8080"))
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=False)
