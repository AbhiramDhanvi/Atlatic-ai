# Verification record

- Local application tests: 23 passed.
- Offline guardrail/workflow evaluation: 42 checks passed; controlled adapters, not live inference scores.
- Live Supabase schema: nine application tables with RLS, eleven table/storage policies, private document bucket.
- Live transactional database regression: eleven assertions passed, covering cross-user documents/messages/conversations/storage isolation, forged ownership rejection, approval privilege checks, anonymous function privileges, own-vector retrieval and daily quota enforcement. All fixtures rolled back.
- JavaScript syntax and Python compilation passed.
- Render Free initial deployment reached live. Public liveness and configuration endpoints returned 200; anonymous document access returned 401. GitHub CI passed.
- Gemini embeddings returned HTTP 200 with 768 dimensions. The initial legacy chat model returned 404; Gemini 3.5 Flash returned HTTP 200 with answer candidates and is now the configured model.
- Browser upload/chat and administrator registration still require the owner to create and verify their account. Do not claim these checks passed from unit tests alone.

The Supabase advisor identified inherited anonymous EXECUTE privileges during initial verification. Migration 002 explicitly revokes them. Its authenticated SECURITY DEFINER advisory surface is intentional and documented in SECURITY.md.
