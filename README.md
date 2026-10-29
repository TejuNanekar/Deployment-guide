# Deployment-guide
# Matrimony deployment assistant
Answers Matrimony deployment questions from the files already in the Matrimony repos. It does not SSH and it does not run a deploy.
Needs Python 3, Node.js, and a Groq API key. Qdrant runs locally by default.
## Setup
```bash
cd backend
python -m pip install -r requirements.txt
copy .env.example .env
```
In `backend/.env`, set `GROQ_API_KEY` and the two checkout paths:
- `MATRIMONY_PLATFORM_ROOT` — API repo
- `MATRIMONY_UI_ROOT` — UI repo
```bash
cd frontend
npm install
```
## Run
Terminal 1 — API:
```bash
cd backend
python -m app.ingest
python -m uvicorn app.main:app --reload --port 8000
```
Terminal 2 — UI:
```bash
cd frontend
npm run dev
```
Open http://localhost:3000. The API is http://localhost:8000.
After a deploy file changes, pull the repo and run `python -m app.ingest` again (or use **Re-index documents** in the UI).
## Optional Qdrant server
```bash
docker compose up -d
```
Then set `QDRANT_URL=http://localhost:6333` in `backend/.env`. Leave it empty to keep the local file
