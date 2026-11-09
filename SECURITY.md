# Security

Never commit API keys, passwords, refresh/access tokens, or private documents. Supabase publishable keys are public identifiers, not admin keys. RLS is mandatory and independently enforced during vector search. Anonymous callers have no table access and no execute permission on application database functions. No service-role key is needed by the server.

Report vulnerabilities privately to the repository owner using GitHub's security advisory feature if enabled; do not include secrets in public issues. This educational free-tier deployment has no security certification, uptime SLA, managed queue, automated backup policy, or comprehensive prompt-injection defense. Regex checks are defense in depth, not a guarantee of safety. Approval is a decision record, not an executor.

Use a separate test project for adversarial testing. Inspect Supabase advisers after migrations. Authenticated SECURITY DEFINER execution for admin membership checks, atomic quota reservation and guarded approval decisions is intentional. All use a fixed search path and explicit authorization.
