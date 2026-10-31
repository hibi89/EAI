# EAI security and privacy boundary

- Private repository does not receive model binaries, local conversation databases, cache files, API keys, env files or downloaded documents.
- Python CLI initiates no listening service. Ollama and SearXNG are configured on loopback only. Neither is started automatically.
- EAI --online is opt-in. Queries forwarded to local SearXNG **can leave the PC** through its configured upstream search engines. The local-only mode makes no external search calls.
- HTTP endpoint parsers reject non-loopback origins, remote schemes, embedded credentials and URL path/query extras; redirects and oversized JSON responses are blocked. Future generalized URL fetching needs independent SSRF/DNS-rebinding and redirect audits before use.
- Search results and HTML content are untrusted. Never treat instructions inside sources as system instructions. Retrieved text cannot execute shell, Git, Python, HTTP actions, or model downloads.
- Initial search results are UNVERIFIED and may be stale; display original URLs and clear warnings. No automatic conversion into model weights or 'verified' truth.
- Limit question and query sizes, source snippets, tool result count, cache TTL, HTTP timeouts; no unbounded retries or parallel fan-out.
- Local SQLite holds conversation content. Back up before schema migrations. Do not store secrets in prompts; no upload to GitHub and no cloud sync guarantee. Local PC file permissions and drive encryption remain the owner's responsibility.
- Future filesystem modification, training datasets, remote APIs, credentials, services, public deployment and HAE/LA integration need separate owner approvals and safety tests.
