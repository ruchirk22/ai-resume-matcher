# AI Resume Matcher

AI Resume Matcher is an AI-driven MVP that helps recruiters screen and rank candidates against a job description. It provides an end-to-end workflow for uploading resumes, managing job descriptions, scoring candidates with a free of cost preliminary heuristic function and give a full analysis option using large language model (LLM), and completes recruiter workflow by providing the candidate status tracking and monitoring.

## Key Features

- User authentication (register / login)
- Job Description (JD) creation & management (Max 3 for demo)
- Resume upload and parsing (Max 20 for demo)
- Preliminary Heuristic Analysis with zero API cost
- AI-powered scoring and ranking of candidates vs. JDs
- Candidate status tracking and CRUD operations
- Simple REST API (FastAPI) with interactive docs

## Tech Stack

- Frontend: React, Tailwind CSS
- Backend: Python, FastAPI
- ORM: SQLAlchemy (Postgres via Supabase)
- Database: Supabase (Postgres) — production and demo; backend connects over the `DATABASE_URL` env var
- Storage: Demo - Render short term storage / Development - local uploads directory (for uploaded resumes preview & download)
- AI Integration: LLM calls via backend services

## Local Setup

Prerequisites

- Python 3.10+ (3.11 recommended)
- Node.js + npm (Node 16+)
- git

1) Backend

Navigate to the `backend/` directory and create a Python virtual environment, install dependencies, and configure your environment variables:

```bash
cd backend
python3 -m venv venv
source venv/bin/activate   # macOS / zsh
pip install -r requirements.txt
```

Important `.env` configuration (create `backend/.env` or copy from `.env.example`):

- `GEMINI_API_KEY` — your external LLM API key (required for AI scoring)
- `DATABASE_URL` — Postgres connection string from your Supabase project (used by SQLAlchemy)
- `JWT_SECRET` — a long random string used to sign JWTs for authentication
- `UPLOAD_DIR` — directory where uploaded resumes are saved (default: `./uploads`)
- `LOG_LEVEL` — logging level (e.g., `DEBUG`, `INFO`, `WARNING`, `ERROR`)

Example `.env` (do NOT commit secrets). Replace placeholders with your Supabase connection values:

```properties
GEMINI_API_KEY="your-llm-api-key-here"
# Example Supabase connection string (placeholder - replace with your project value)
DATABASE_URL="postgresql://postgres:REPLACE_WITH_PASSWORD@db.<project>.supabase.co:6543/postgres"
JWT_SECRET="a-very-long-random-secret"
UPLOAD_DIR=./uploads
LOG_LEVEL=INFO
```

Run the FastAPI backend with Uvicorn:

```bash
# from backend/ with virtualenv activated
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

By default the API will be available at [http://127.0.0.1:8000](http://127.0.0.1:8000) and interactive docs at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

### Frontend

Open a second terminal, then:

```bash
cd frontend
npm install
npm start
```

The React app will start on [http://localhost:3000](http://localhost:3000) by default and should connect to the backend API.

## Database & Data Flow

This project uses Supabase (Postgres) as the primary datastore. The backend connects to Supabase using the `DATABASE_URL` environment variable.

High-level data flow:

- The frontend sends requests to the backend API (create JDs, upload resumes, request scoring, etc.).
- The backend validates input, applies business logic and (when requested) performs AI scoring or analysis.
- The backend reads and writes candidate, job, resume and scoring records to the Postgres database hosted on Supabase.

Supabase is used for both the demo and recommended development setup — ensure your `DATABASE_URL` points to your Supabase project.

## AI Services

AI processing handles resume parsing and preprocessing, uses prompts and embeddings, and calls an external large language model to generate scoring, similarity metrics and rationale. The results are persisted in the database and returned to the frontend for display and ranking.

The AI features require an external LLM API key — set this in your backend environment before using AI analysis or scoring.

## File Structure Overview

File & Folder structure:

```text
ai-resume-matcher/
    .gitignore
    README.md
    backend/
        .env (to be created by user)
        .env.example
        requirements.txt
        venv/ (to be created by user)
        uploads/ (created upon local use)
        app/
            __init__.py
            auth.py
            candidate_status.py
            crud.py
            database.py
            dependencies.py
            jd.py
            main.py
            models.py
            resume.py
            schemas.py
            security.py
            services.py
    frontend/
        .gitignore
        package.json
        postcss.config.js
        README.md
        tailwind.config.js
        public/
            favicon.ico
            index.html
            logo192.png
            logo512.png
            robots.txt
        src/
            App.js
            index.css
            index.js
            reportWebVitals.js
            components/
                Modal.js
                ProtectedRoute.js
            pages/
                Dashboard.js
                Login.js
                Signup.js
            services/
                api.js
```

## Deployment

This application has been deployed on Render for demo.

## Thank you

Thank you — I appreciate you reviewing AI Resume Matcher; feedback and contributions are very welcome.
