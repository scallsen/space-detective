# PROJECT_CONTEXT.md

Welcome to the **Airlock Sabotage** hackathon project! This document outlines the codebase, architecture, state flow, and next steps for developers (and AI agents) working on this repository.

---

## 1. Project Directory Structure
* `index.html`: The main user interface. It is a single-screen dashboard layout.
* `style.css`: Clean, dark-themed, sci-fi glassmorphism styles.
* `app.js`: Game state, event listeners, mock interrogation replies, and logic to trigger win/loss.
* `docs/GAMEPLAY_PROMPT.md`: System prompt structure for the LLMs (includes the alibis, contradictions, and personalities).
* `docs/PROJECT_CONTEXT.md`: This file.

---

## 2. Core Game Loop & State
The game is managed clientside in `app.js` using a single global state object:
* `oxygen`: Begins at 100% and decreases by 10% after each question asked (10 total questions).
* `questionsAsked`: Tracks the number of interrogations.
* `gameOver`: Boolean flag.
* `saboteur`: The guilty crew member (Jax).
* `suspects`: Array containing Elena, Marcus, Dr. Chen, and Jax.

---

## 3. Interrogation Logic
In a fully implemented version, querying the crew will post to an LLM API endpoint. 
Currently, in `app.js`, we implement a **rule-based mock response system** that simulates the LLM replies to allow quick frontend testing:
* The mock matches keywords (e.g., "where", "alibi", "Chen", "Jax", "Elena", "Marcus", "04:15") to return context-appropriate dialogue.
* If a question doesn't match any keywords, characters respond with their generic, role-specific defensive/neutral alibi statements.

---

## 4. Next Steps for Development
1. **Wire up LLM Endpoint:** Replace the mock response system in `app.js` with an actual `fetch()` to your serverless function or backend API that invokes Gemini or another LLM using the prompt in `docs/GAMEPLAY_PROMPT.md`.
2. **Audio/Sfx:** Add low, ambient spaceship humming, keypress bleeps, and a loud alarm sound when oxygen drops below 30%.
3. **Animations:** Add subtle screen shake and red light flashing overlay when "Vent" is clicked.
