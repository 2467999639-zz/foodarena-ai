# AGENTS.md — team AI rules & architecture constraints

These rules guide AI coding assistants working in this repository. They are
treaty-level, like code review comments: call them out when an edit violates
them, and update them through a PR rather than unilaterally.

## Project

FoodArena AI (校园干饭辩论赛) is an AI-native campus food-decision demo built
for an agile engineering practice course. Two chef agents (川辣派 Sichuan
spicy, 粤式养生派 Cantonese wellness) debate over three rounds and a judge
emits a structured report, all driven through SiliconFlow DeepSeek.

## Repository layout

- `src/foodarena_ai/` — Python package (FastAPI + SQLAlchemy + Pydantic).
  - `domain.py`  — Pydantic contracts and the synthetic demo `MENU`.
  - `db.py`      — SQLAlchemy ORM rows + repository mapping.
  - `service.py` — `DebateService` orchestrator and the debate lifecycle.
  - `main.py`    — FastAPI routes.
  - `security.py`— prompt-injection defence and log redaction.
  - `prompts.py` — versioned persona/judge prompts (`PROMPT_VERSION`).
- `frontend/` — React + Vite + TypeScript SPA.
- `tests/` — pytest unit tests and `tests/features/*.feature` BDD suites.
- `eval/` — synthetic eval set (`evalset.json`) + `score_evalset.py`.

## Non-negotiables

1. No real API keys, personal data, or unredacted logs are ever committed.
   `.env` is git-ignored; `.env.example` lists only placeholders.
2. Every external-model response crosses a Pydantic boundary before use.
3. Tests never hit the network or require a real key; the mock provider
   (`MockChefProvider`) must stay deterministic.
4. `main` is protected: changes land via PR with CI green and a review.
5. Angular conventional commits: `feat:`, `fix:`, `test:`, `docs:`, `chore:`.
6. Backend lints clean under `ruff check`/`ruff format --check`; frontend under
   `tsc`, `eslint`, and `vitest`.

## Lifecycle

Session states: `PENDING -> RUNNING -> VALIDATING -> SUCCESS` (or `FAILED`).
A session can only start a debate from `PENDING`; re-entry returns stored
state and never spawns a second debate chain.
