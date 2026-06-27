# AGENT.md - Agent Instructions & Architecture

This document serves as the guide for any AI agents or developers contributing to **Airlock Sabotage**. Update this file whenever APIs, dependencies, or core gameplay structures change.

---

## 1. Project Overview
**Airlock Sabotage** is a single-screen, browser-based detective game designed for a hackathon timeframe. The player (acting as the Station Commander) must interrogate 4 crew suspects in a shared chat channel to identify the single saboteur before the oxygen reserve (representing a turn counter of 10 questions) reaches 0%.

---

## 2. Quickstart Commands

### Setup Virtual Environment
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Run Python API Backend (FastAPI)
Starts on `http://localhost:8080` (requires `GEMINI_API_KEY` set in the environment or a `.env` file):
```bash
python3 server.py
```

### Run Static Web Server (Frontend)
Starts on `http://localhost:8000`:
```bash
python3 -m http.server 8000
```

---

## 3. Directory Layout
* `index.html`: Main console page and layout panels.
* `style.css`: Custom CSS containing dark-mode space styling, progress bar colors, and neon alerts.
* `app.js`: Client-side state machine (oxygen levels, interrogations left, win/loss triggers, and keyword-based fallback responses).
* `server.py`: FastAPI server that bridges the frontend fetch requests to the Google Antigravity SDK.
* `requirements.txt`: Python package list (`google-antigravity`, `fastapi`, `uvicorn`, `pydantic`).
* `docs/GAMEPLAY_PROMPT.md`: System prompt structure for the LLM. Contains suspect biographies and alibis.
* `docs/PROJECT_CONTEXT.md`: High-level code architecture notes.

---

## 4. Coding & Architecture Guidelines

### Frontend & Style Guidelines
* **Technologies:** Pure HTML5, CSS3, and modern client-side JavaScript. No heavy JS frameworks (React/Vue/etc.) or CSS libraries (Tailwind) are used.
* **Aesthetics:** High-fidelity glassmorphism, responsive grids, and neon accents. Font pairings are `Outfit` for general text and `Share Tech Mono` for console codes and numbers.
* **Fallback Design:** The frontend in `app.js` must **always** handle fetch failures to `http://localhost:8080/api/interrogate` gracefully. If the server is offline or lacks credentials, the game must fall back to the rule-based keyword replies in `app.js`.

### Backend & Agent Guidelines
* **Framework:** FastAPI with Uvicorn.
* **Agent Integration:** All interactions with Gemini must be routed using the `google.antigravity` SDK.
* **Structured Output:** The backend must request structured JSON from the SDK using Pydantic models. Example:
  ```python
  class CrewInterrogationResponse(pydantic.BaseModel):
      elena: str
      marcus: str
      chen: str
      jax: str
  ```

---

## 5. Core Mystery Mechanics
To avoid breaking the puzzle logic, agents must respect the alibi ground truth:
* **The Saboteur:** Jax Thorne (Security Guard).
* **The Sabotage:** Oxygen line severed in Sector 7 at **04:15**.
* **Jax's Lie:** Claims he was with Dr. Mei-Ling Chen in Sector 4 (Greenhouse) from 04:10 to 04:20.
* **Dr. Chen's Truth:** Was in Sector 4 **alone** all night. She denies seeing Jax.
* **Elena & Marcus:** Their alibis are innocent and corroborate each other (Marcus saw Elena in Sector 2 at 04:05).
