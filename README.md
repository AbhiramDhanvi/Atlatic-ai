# Atlatic AI

A private document assistant with source-cited RAG, persistent conversation history, email/password authentication, human review records, audit events, and reproducible evaluations. Built with FastAPI and LangGraph, with Gemini inference and Supabase Auth, Storage, PostgreSQL and pgvector.

Derived from [entbappy/ATLAS-Enterprise-AI](https://github.com/entbappy/ATLAS-Enterprise-AI), upstream commit `511bd7f4483ed7e869cb453aadc46abcdfd9a2a5`, and its [video tutorial](https://www.youtube.com/watch?v=q08xK7Jd1nM). Apache-2.0 attribution is retained in LICENSE and NOTICE. The repository is a free-tier adaptation, not an identical AWS deployment.

## Features

- Responsive dark dashboard: chat, documents, recent conversations, approvals, activity and evaluation guidance.
- Real Supabase sign-up/sign-in and session refresh; no shared demo administrator or embedded password.
- Every data and storage call carries the user's JWT. Database RLS independently isolates documents, embeddings, conversations, messages and feedback.
- Private PDF/DOCX/TXT/Markdown upload; extraction, overlapping chunks, normalized Gemini embeddings and atomic pgvector insertion.
- LangGraph input checks → retrieval → evidence-conditioned generation → output and citation checks.
- Persistent follow-up context and citations with document title, page and excerpt.
- Sensitive action requests enter an approval queue. Decisions are records only; no automatic action executor is provided, matching the tutorial's scope.
- Owners can explicitly delete their own files and indexed evidence in Documents.
- Daily per-user/global AI limits, private activity events and latency tracking.
- 52 evaluation cases, offline regressions, opt-in live RAG metrics and an optional Gemini judge. No fabricated quality scores.
- Docker, GitHub Actions verification and Render Free deployment configuration.

## What changes from the tutorial?

| Tutorial | Atlatic free-tier adaptation |
|---|---|
| Bedrock Nova/Titan | Gemini text generation/embeddings |
| Pinecone | Supabase pgvector, with RLS enforced during retrieval |
| S3 | Private Supabase Storage bucket |
| PostgreSQL | Supabase PostgreSQL |
| Shared demo principal | Verified Supabase Auth users |
| EC2/ECR | Render Free Python service or Docker |
| Optional external tracing | Private application audit events and response timing |
| Syntax CI | API/behavior tests plus offline evaluation checks |

The full video transcript was not available during initial implementation. The linked repository and published tutorial architecture are the implementation references; do not describe this as a line-by-line video reproduction.

## Local setup

Use Python 3.12. From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
# Windows: .venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
cp .env.example .env
```

1. Create a Supabase Free project. In its SQL editor apply `supabase/migrations/001_atlatic.sql` then `002_explicit_privileges.sql` in order. Both must succeed before exposing the application.
2. Copy the project's URL and publishable key into `.env`. Never use a service-role/secret key in this app.
3. Add `GEMINI_API_KEY` privately. Select a chat and embedding model with free quota in your account; verify current model availability. The defaults are configuration examples, not a guarantee that a particular model stays available forever.
4. Keep `EMBED_DIM=768`, matching the SQL column. Switching embedding models requires a new index or clearing/re-ingesting your own documents; do not mix embedding spaces.
5. Under Supabase Auth, configure the deployed Site URL and allowed redirect URLs. Keep email confirmation enabled. The app tells new users to confirm their email and then sign in.
6. For reliable email delivery beyond Supabase's testing limits, configure your own SMTP provider within that provider's free allowance.

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000`. Sign up, verify your email, sign in and add the fictional handbook. Ask "How many annual leave days are allowed?" then "How many can be carried forward?".

Passwords are submitted only to Supabase Auth through the backend and never stored in application tables or logs. Browser access and refresh tokens are stored in sessionStorage for this single-page app; sign out on shared devices. A restrictive CSP and text-only rendering reduce script-injection exposure. For a higher-assurance production application, replace browser token storage with hardened server sessions.

## Administrator setup

Create and confirm the intended administrator account first. In Supabase's SQL editor run the following after replacing the example email. This is an operator-only task; users cannot promote themselves.

```sql
insert into public.atlatic_admins(user_id)
select id from auth.users
where email = 'owner@example.com' and email_confirmed_at is not null
on conflict do nothing;
```

Administrators can review approval requests but cannot browse other users' documents or conversations. Admin membership and quota tables intentionally deny direct user access. SECURITY DEFINER functions for quota and approval decisions are narrow, have fixed search paths, reject anonymous callers, and explicitly verify privileges; this intentional authenticated EXECUTE surface can appear in Supabase's advisory report.

## Deploy on Render Free

Connect this repository to a Render Python Web Service:

- Plan: **Free**; region: Singapore.
- Build: `pip install -r requirements.txt` (or the committed lockfile for exact tested dependencies).
- Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
- Set `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `GEMINI_API_KEY`, `GEMINI_CHAT_MODEL`, and `GEMINI_EMBED_MODEL` in Render's Environment settings.
- Health check: `/health/live`. This permits a setup-incomplete UI to start; `/health/ready` returns 503 until required configuration is present and checks Supabase Auth. It does not claim live inference was checked.
- Enable deploys after GitHub checks pass. `render.yaml` supplies a matching Blueprint configuration.
- All persistent files and data are in Supabase, never Render's ephemeral disk.

Docker is also supported:

```bash
docker build -t atlatic-ai .
docker run --rm --env-file .env -p 8000:8000 atlatic-ai
```

Render Free can sleep and has no always-on guarantee. Supabase can pause inactive free projects. Gemini quotas and data-use terms depend on the selected tier. Use public/fictional documents for the free provider tier. Do not enable paid billing or assume that usage alerts are hard spending caps. This repository does not provision paid AWS resources.

## Limits and recovery

- 5 MB per upload; 40 chunks of up to 1,200 characters with 180-character overlap; at most 100 PDF pages. Scanned documents need OCR, which is not included.
- 20 indexed documents per user through the commit operation.
- Per-user UTC-day quotas: 30 chat runs and 5 ingestion runs. App-wide caps: 100 chat runs and 20 ingestion runs. Judge calls also consume the chat quota when run by the evaluation tool.
- Quotas reserve attempted runs, including failed provider calls; they do not refund failures automatically.
- Ingestion is synchronous and bounded. It embeds before writing and commits relational data atomically. Failed commits attempt object cleanup. Long documents must be split; durable background jobs are a future production extension.
- Deletion removes indexed data first. If storage cleanup fails, the UI reports it; an operator can remove that owner-scoped orphan object in Supabase.
- A free quota exhaustion returns 429 and is not retried aggressively. The backend surfaces setup-needed errors, rather than returning a pretend AI answer.
- Rate limiting of authentication attempts is per-process; Supabase also applies provider-side Auth limits. A production deployment should add a durable edge rate limiter.

## Tests and evaluations

```bash
python -m pytest tests -q
python -m evals.run --offline --output eval-reports/offline.json
```

Offline evaluation uses controlled model/retrieval adapters. It tests guardrail behavior and workflow routing, **not live model quality**. `tests/rls.sql` runs transactional two-user database fixtures and rolls back all changes. Run it against a dedicated test project using the Supabase SQL editor or the connected SQL tool; never replace it with a production password.

For live evaluation:

1. Use a dedicated confirmed test account.
2. Upload `samples/handbook.txt` to that account through the UI.
3. Set a short-lived `EVAL_ACCESS_TOKEN` privately in your local process. Do not commit tokens or reports containing private source text.
4. Run:

```bash
python -m evals.run --output eval-reports/live.json
# Optional additional model calls:
python -m evals.run --judge --output eval-reports/judged.json
```

The report includes dataset hash, Git commit, model IDs, retrieval settings, latency, reference fact coverage, expected document retrieval, citation-number validity and optionally judge correctness/faithfulness/relevance estimates. String matching is a heuristic; citation numbering is not a semantic grounding proof. Judge scores need human review. Preserve a held-out dataset when tuning prompts, chunk sizes or thresholds. Nothing publishes eval text to other users.

## API

Public: `/`, `/health/live`, `/health/ready`, `/api/config`, `/api/auth/*`.
Authenticated: `/api/me`, `/api/documents`, `/api/documents/sample`, `/api/conversations`, `/api/conversations/{id}/messages`, `/api/chat`, `/api/feedback`, `/api/approvals`, `/api/activity`.
Admin-only: `POST /api/approvals/{id}/decision`.
Interactive reference: `/api/docs`.

Original upstream teaching documents are retained under `docs/upstream` for attribution and historical context. Their AWS instructions do not apply to this adaptation. Use this README for the current setup.
