# Esports Pakistan

A full-stack esports tournament platform where organizers host verified tournaments and players register, get seeded into brackets, and compete for prize pools — across Valorant, Tekken 8, Counter-Strike 2, PUBG Mobile, and EA Sports FC. It also includes an AI rules assistant that answers rulebook questions using retrieval-augmented generation (RAG) over uploaded PDF rulebooks.

## Tech stack

**Backend** — Django 4.2 + Django REST Framework, PostgreSQL, JWT auth (`djangorestframework-simplejwt`), Cloudinary for media storage.

**Frontend** — React + Vite, React Router, Tailwind CSS, Framer Motion.

**AI rules assistant** — PyMuPDF (PDF text extraction), `sentence-transformers` (embeddings), ChromaDB Cloud (vector store), Groq (LLM inference).

## Features

- **Players** — browse games and tournaments, register solo or as a team, check in, follow the bracket, and ask the rules assistant questions about any game's official rulebook.
- **Organizers** — apply for organizer status (company details, CNIC, payout method), get admin-approved, then create and publish tournaments (single/double elimination, round robin, Swiss, 3-game guarantee, or group stage + playoff), manage registrations, and generate/advance brackets.
- **Admins** — approve/reject organizer applications, manage the game catalog, moderate tournaments, and upload/manage rulebook PDFs that power the AI assistant.
- **Auth** — email/password with strength validation and email verification, plus Google Sign-In.

## Project structure

```
Esports_gaming_platform/
├── backend/                # Django project
│   ├── config/              # Settings, root URLs
│   ├── core/                 # User model, auth, profiles
│   ├── games/                 # Game catalog
│   ├── organizer/             # Organizer applications/approval
│   ├── tourny_regist/          # Tournaments, registrations, teams
│   ├── brackets/               # Bracket generation & match results
│   ├── partners/                # Sponsor/partner listings
│   ├── dashboard/                 # Aggregate stats
│   └── rag_chat/                   # Rulebook upload + AI chat assistant
└── frontend/                # React + Vite app
    └── src/
        ├── pages/             # Route-level views
        ├── components/         # Shared UI (tournament cards, brackets, admin, chatbot)
        └── lib/                 # API client, auth context, formatting helpers
```

Each backend app owns its own models, serializers, views, and URLs, all mounted under `/api/` in `config/urls.py`.

## Getting started

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in the values below
python manage.py migrate
python manage.py runserver
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The frontend expects the backend at `http://localhost:8000` by default (`VITE_API_URL`).

## Environment variables

Backend (`backend/.env`):

| Variable | Purpose |
|---|---|
| `SECRET_KEY`, `JWT_SECRET_KEY` | Django & JWT signing secrets |
| `DATABASE_URL_DEV` / `DATABASE_URL_PROD` | PostgreSQL connection string |
| `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET` | Media storage |
| `CHROMA_API_KEY`, `CHROMA_TENANT`, `CHROMA_DATABASE` | Vector store for the rules assistant |
| `GROQ_API_KEY`, `GROQ_MODEL` | LLM inference for the rules assistant |
| `GOOGLE_CLIENT_ID` | Google Sign-In |
| `BREVO_API_KEY`, `DEFAULT_FROM_EMAIL` | Verification/reset/announcement emails, sent via Brevo's transactional email API — unset locally, emails print to the console instead of sending |

Frontend (`frontend/.env`):

| Variable | Purpose |
|---|---|
| `VITE_API_URL` | Backend base URL |
| `VITE_GOOGLE_CLIENT_ID` | Google Sign-In (must match the backend's) |

## Testing

```bash
cd backend
python manage.py test
```

## How the rules assistant works

1. An admin uploads a rulebook PDF for a specific game via the admin panel.
2. The backend extracts the text, splits it into per-section chunks, detects which game each chunk belongs to, and embeds them into ChromaDB.
3. When a player asks a question, the same game-detection runs on the question, retrieval is scoped to that game (vector + keyword search, then reranked), and Groq generates an answer grounded only in the retrieved rulebook text — it won't answer beyond what's actually in the uploaded documents.
