<img width="1125" height="705" alt="Screenshot 2026-06-27 at 6 18 14 PM" src="https://github.com/user-attachments/assets/f4d0da1d-29f1-4814-b7c3-f60d5b90277d" />

# Airlock Sabotage

A single-screen, browser-based detective game set aboard a space station in 2142. As the Station Commander, you must interrogate four crew suspects in a tense real-time deduction challenge — before the oxygen runs out.

Built for a Google Gemini AI Hackathon (Tokyo, June 27 2026) using the Google Agent Platform.

---

## Gameplay

The station's oxygen feed line has been severed. Four crew members had access to Sector 7. You have **10 questions** before life support fails completely.

- Select a suspect from the crew sidebar
- Type your interrogation query and hit **TRANSMIT**
- All four suspects respond simultaneously — watch for contradictions
- When you've found your culprit, hit **VENT** to eject them through the airlock
- Vent the wrong person and the real saboteur disables the escape pods

Each suspect is powered by an independent Gemini AI agent with its own backstory, alibi, and access to a shared evidence database. The agent playing the saboteur will lie. The others will tell the truth — but only about what they actually know.

<img width="2584" height="1024" alt="Character Lineup" src="https://github.com/user-attachments/assets/938ee6af-9dee-4f84-8e0e-bc49563cf2d7" />

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | HTML5, CSS3, vanilla JavaScript |
| Backend API | Python, FastAPI, Uvicorn |
| AI Agents | Google Gemini 2.5 Flash via `google-antigravity` |
| Evidence DB | SQLite (seeded at startup) |
| Deployment | Docker, Google Cloud Build |

---

## Prerequisites

- Python 3.11+
- A Gemini API key — set as `GEMINI_API_KEY` in a `.env` file or your environment

---

## Running Locally

**1. Set up the Python environment**

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**2. Add your API key**

```bash
echo "GEMINI_API_KEY=your_key_here" > .env
```

**3. Start the backend**

```bash
python3 server.py
```

The API starts on `http://localhost:8080`.

**4. Serve the frontend**

In a second terminal:

```bash
python3 -m http.server 8000
```

Open `http://localhost:8000` in your browser.

> **Offline fallback:** If the backend is unreachable, the game automatically falls back to keyword-based responses so the game remains playable without an API key.

---

## Running with Docker

```bash
docker build -t airlock-sabotage .
docker run -e GEMINI_API_KEY=your_key_here -p 8080:8080 airlock-sabotage
```

Then open `http://localhost:8080`.

---

## Project Structure

```
.
├── index.html          # Game UI — HUD, scene, dialog box, overlays
├── style.css           # Retro terminal aesthetic — scanlines, neon, pixel fonts
├── app.js              # Client-side state machine — oxygen, turns, win/loss
├── server.py           # FastAPI backend — one Gemini agent per crew role
├── database.py         # SQLite setup and role-scoped query tools
├── requirements.txt    # Python dependencies
├── Dockerfile
├── cloudbuild.yaml     # Google Cloud Build config
└── Story/
    ├── Scenario.md             # Public case briefing (shared by all agents)
    ├── SystemInstructions.md   # Shared agent behaviour rules
    ├── IncidentLogs.md         # Evidence seeded into the database
    ├── Chief Engineer.md       # Role profile
    ├── Technician.md
    ├── Botanist.md
    ├── Security Guard.md
    └── Agents/                 # Private per-agent instructions (including the lie)
        ├── Chief Engineer.md
        ├── Technician.md
        ├── Botanist.md
        └── Security Guard.md
```

---

## How the Agents Work

Each crew member is a separate Gemini agent with:

- A **system prompt** built from the shared scenario, their role profile, and private instructions that determines character.
- **Role-scoped database tools** — agents can only query logs and alibis visible to their own role
- **Structured output** — responses are returned as `{"response": "..."}` and validated by Pydantic

All four agents run concurrently per question (`asyncio.gather`), so every suspect answers at the same time, just like a real interrogation channel.

The saboteur's private instructions tell it to lie about its whereabouts. The innocent suspects tell the truth — including the one whose alibi directly contradicts the saboteur's story.

---

## Environment Variables

| Variable | Description |
|---|---|
| `GEMINI_API_KEY` | Gemini API key (or use `GOOGLE_API_KEY`) |
| `GOOGLE_GENAI_MODEL` | Model override (default: `gemini-2.5-flash`) |
| `GOOGLE_GENAI_USE_VERTEXAI` | Set to `TRUE` to use Vertex AI instead |
| `GOOGLE_CLOUD_PROJECT` | Required when using Vertex AI |
| `GOOGLE_CLOUD_LOCATION` | Vertex AI region (default: `us-central1`) |
| `PORT` | Server port (default: `8080`) |
