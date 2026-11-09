# Verification record

- Local application tests: 23 passed.
- Offline guardrail/workflow evaluation: 42 checks passed; controlled adapters, not live inference scores.
- Live Supabase schema: nine application tables with RLS, eleven table/storage policies, private document bucket.
- Live transactional database regression: eleven assertions passed, covering cross-user documents/messages/conversations/storage isolation, forged ownership rejection, approval privilege checks, anonymous function privileges, own-vector retrieval and daily quota enforcement. All fixtures rolled back.
- JavaScript syntax and Python compilation passed.
- Live Gemini generation, browser upload/chat, deployment and administrator registration must be confirmed after credentials and deployment are configured. Do not claim these checks passed from unit tests alone.

The Supabase advisor identified inherited anonymous EXECUTE privileges during initial verification. Migration 002 explicitly revokes them. Its authenticated SECURITY DEFINER advisory surface is intentional and documented in SECURITY.md.
