# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Auto HR Copilot** is an automated recruitment execution platform. It integrates with the BOSS 直聘 (zhipin.com) recruitment platform via Chrome remote debugging to fetch job listings and candidates, translates job descriptions (JDs) into structured hiring profiles using LLM or rule-based fallback, and performs evidence-based candidate screening with grades S/A/B/C.

## Development Commands

### Backend (FastAPI, Python 3.11+)
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
# API: http://127.0.0.1:8000
# Swagger docs: http://127.0.0.1:8000/docs
# Health check: http://127.0.0.1:8000/health
```

### Frontend (Next.js 15 + React 19 + TypeScript)
```bash
cd frontend
npm install
npm run dev      # Dev server: http://127.0.0.1:3000
npm run build    # Production build
npm run lint     # Lint check
```

There are no automated tests in this codebase. Validation is done via mock data and manual testing.

## Architecture

### Four-Layer Backend
- **`backend/app/api/routes/`** — FastAPI routers (jobs, candidates, tasks, boss, feedback, settings, dashboard). Request validation only; no business logic.
- **`backend/app/schemas/`** — Pydantic request payload schemas (separate from domain models).
- **`backend/app/services/`** — All business logic (19 modules). The canonical layer for any new feature.
- **`backend/app/models/domain.py`** — All Pydantic domain models (`JobProfile`, `CandidateAnalysis`, `CandidateCard`, `ScreeningTask`, etc.). Source of truth for data shapes.

### App Startup (Lifespan)
`main.py` uses a FastAPI lifespan context to start two background async services at boot:
- `task_state_manager` — monitors in-flight tasks, marks interrupted tasks as `failed` on restart
- `task_scheduler` — continuously executes pending screening tasks in the background

Both are shut down cleanly when the server stops. A `WindowsProactorEventLoopPolicy` workaround is applied automatically when running on Windows.

### Frontend
- **`frontend/app/`** — Next.js App Router pages. Uses React Server Components where possible.
- **`frontend/components/`** — Reusable UI components.
- **`frontend/lib/api.ts`** — Centralized API client with 1500ms timeout and automatic fallback to mock data when the backend is unreachable.
- **`frontend/lib/types.ts`** — TypeScript types that mirror backend Pydantic models. Must be kept in sync manually with `domain.py`.

### Core Data Flows

**JD Translation Pipeline:**
`job_service.translate_jd()` → `jd_translator.translate()` → LLM API call (OpenAI-compatible) → on failure, automatic fallback to `RuleBasedJDTranslator`. All LLM requests are traced via `llm_trace_service` and retrievable at `/api/settings/traces`.

**Candidate Screening — Two Flows:**
- **Scheduler-driven** (primary): `task_scheduler` picks up queued tasks and calls `screening_executor.execute()`, which fetches candidates from Boss or mock data, calls `candidate_screening_service.analyze()` for LLM scoring, and persists `CandidateCard` + `CandidateAnalysis`. Supports pause/resume. Frontend polls `/api/screening-tasks`.
- **Legacy streaming** (`task_service.run_screening()`): in-memory only, no pause/resume. The SSE endpoint `/api/screening-tasks/stream` pushes task state and job updates with a 30-second heartbeat.

**Task State Machine:** Full lifecycle is `pending` → `queued` → `running` → `pausing` → `paused` → `resuming` → `running` → `completed`/`failed`/`cancelling` → `cancelled`. `task_state_manager` owns all transitions; never mutate task status outside it.

**Candidate Data Model Split:** `CandidateCard` is the lightweight list view (grade, name, summary). `CandidateDetail` is the full view and additionally holds `timeline`, `original_resume`, `parsed_resume`, and `analysis`. Both are in `domain.py`.

**Evidence-Based Scoring:**
`CandidateAnalysis` stores per-criterion `CandidateEvidence` items, each typed as one of: `action`, `number`, `timeline`, `value`, or `risk`. This provides human-readable justification alongside the S/A/B/C grade.

**Boss Integration:**
`boss_launcher` starts Chrome with `--remote-debugging-port=9222` → user logs in manually → `boss_connector` uses Chrome DevTools Protocol to call BOSS WAPI endpoints (candidate list, resume detail, chat/greeting, favorite). Falls back to mock data if connection fails.

### State & Persistence
- **In-memory store**: `backend/app/services/mock_data.py` holds current active job, candidates, and task during a session.
- **Disk persistence**: `storage/runtime_state.json` (task recovery on restart), `storage/llm_settings.json` (LLM config), `storage/llm_traces/` (per-call audit logs). Logs rotate at 2 MB (5 backups) via a custom `_SafeRotatingFileHandler` that handles Windows file-locking.
- If the backend restarts mid-task, `runtime_state_service` marks the interrupted task as `failed` with a recovery message. State file loading tries `utf-8-sig` → `utf-8` → `gbk` → `gb18030` to handle corrupted or legacy encodings.

## LLM Configuration

LLM settings are managed via the UI at `/settings/llm` or via environment variables:

| Variable | Default | Description |
|---|---|---|
| `AUTO_HR_LLM_API_KEY` | — | Required to enable LLM mode |
| `AUTO_HR_LLM_BASE_URL` | OpenAI v1 | Base URL for OpenAI-compatible API |
| `AUTO_HR_LLM_MODEL` | gpt-4.1-mini | Model name |
| `AUTO_HR_LLM_API_STYLE` | `chat_completions` | `chat_completions` or `responses` |
| `AUTO_HR_LLM_TIMEOUT_SECONDS` | 45 | Request timeout |

Config precedence: `storage/llm_settings.json` (file) takes priority over `AUTO_HR_LLM_*` env vars when the file exists. The codebase is pre-configured for Zhipu GLM-4-Flash.

## Key Implementation Notes

- **LLM fallback**: `jd_translator.py` and `candidate_screening_service.py` always implement a rule-based path. LLM errors must be caught and routed to fallback — never let LLM failures surface as 500 errors.
- **Boss WAPI**: All Boss API endpoints and URL patterns are in `config.json` (root) and `boss_connector.py`. The connector is large (~38KB) — read it carefully before modifying. TLS verification is intentionally disabled in `boss_connector.py` to work around `UNEXPECTED_EOF_WHILE_READING` errors on Windows with the Boss API.
- **Boss job cache**: `job_service` caches the Boss job list for 45 seconds. Stale listings during that window are expected behavior, not a bug.
- **Mock data**: `mock_data.py` serves as both the in-memory store and fallback mock candidates. Frontend `lib/mock-data.ts` provides client-side fallbacks — used when backend is unreachable.
- **Trace IDs**: Every LLM call gets a trace ID from `llm_logging.py`. Traces are stored in `storage/llm_traces/` and visible in the UI at `/settings/llm/traces`.
- **`domain.py` ↔ `types.ts` sync**: These files must stay in sync. When modifying Pydantic models, update the TypeScript types accordingly.
- **PDF parsing**: `pypdf` is used for resume PDF extraction. `playwright` is listed as a dependency for future browser automation (not yet wired into the main flow).
- **Legacy script**: `webBossAI.py` (root) is the original standalone automation script. It is intentionally decoupled from this project and should not be modified or imported.
- **Windows keyboard control**: `main.py` starts a daemon thread that listens for `P` (pause) and `S` (resume) keypresses via `msvcrt` to control the active screening task without an API call. Windows-only; no-op on other platforms.
- **JD category detection**: `RuleBasedJDTranslator` applies category-specific scoring rules for after-sales, B2B sales, project management, field operations, and procurement roles based on keyword matching in the JD text.
- **Age constraints**: `ScreeningBlueprint` supports optional `age_min`/`age_max` fields extracted from the JD and applied during screening.
- **Frontend navigation**: Nav links in `frontend/app/layout.tsx` are hardcoded to a specific job ID (e.g., `/jobs/job-001/...`). Switching the active job requires updating these links, not just changing session state.

## Desktop Packaging (Electron)

The app can be distributed as a zero-install Windows desktop app: one double-click opens it without Python/Node.js prerequisites.

### Architecture

```
Electron (main.js)
 ├─ spawns resources/backend/backend.exe   (PyInstaller — FastAPI on :8000)
 ├─ spawns electron.exe --ELECTRON_RUN_AS_NODE resources/frontend/server.js  (Next.js SSR on :3000)
 ├─ polls /health until both are ready
 └─ opens BrowserWindow → http://127.0.0.1:3000
```

User data (`storage/`, `logs/`) is written to `%APPDATA%\AutoHR\` (passed to `backend.exe` via `AUTHR_DATA_DIR` env var), so it persists across app updates.

### Build Commands

```powershell
# Full build (from repo root):
.\scripts\build-desktop.ps1

# Or step by step:
python -m PyInstaller backend.spec --distpath dist/backend --workpath build/pyinstaller --noconfirm
cd frontend && npm run build
# Copy static assets into standalone:
Copy-Item -Recurse -Force .next\static .next\standalone\.next\static
cd ..\desktop && npm run build
```

Output: `dist/desktop/AutoHR Setup *.exe` (installer) and `dist/desktop/AutoHR-portable-*.exe`.

### Key Files

- `desktop/main.js` — Electron main process: port-conflict detection, process lifecycle, BrowserWindow
- `desktop/package.json` — electron-builder config with `extraResources` mapping
- `backend/launcher.py` — PyInstaller entry point (imports `app.main` for static analysis)
- `backend.spec` — PyInstaller spec (excludes playwright, ~35 MB output)
- `frontend/next.config.ts` — `output: 'standalone'` for self-contained Node.js server bundle

### Caveats

- Port 8000 (API) and 3000 (UI) must be free. Electron shows a clear error dialog if they're occupied (e.g., C-Lodop print service uses 8000).
- The `ELECTRON_RUN_AS_NODE=1` trick runs `frontend/server.js` via the bundled Electron binary — no separate Node.js needed.
- Rebuild `backend.exe` whenever Python dependencies change; rebuild the frontend whenever UI/API contracts change.
