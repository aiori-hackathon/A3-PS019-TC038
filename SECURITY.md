# Security

PrivacyTwin produces evidence *about* personal data without keeping the personal data itself.

## Design

| Control | Implementation |
| --- | --- |
| Read-only sources | SQLite opened with `file:…?mode=ro` + `PRAGMA query_only=ON`; a write probe inside a rolled-back transaction must be refused before scanning. PostgreSQL uses a read-only transaction and warns if the user can write. |
| Bounded processing | 500 / 1,000 / 5,000 rows per table (head, random, stratified), processed in memory; CSV ≤ 20 MB, SQLite ≤ 50 MB. Uploaded SQLite files use a private temp copy deleted in a `finally` block. |
| No raw values persisted | Only schema metadata, counts, ratios, rule IDs, masked examples and keyed MinHash fingerprints (32 × 32-bit HMAC values per column, server-side pepper + per-workspace salt). `tests/test_no_raw_values.py` scans the database, WAL and every export for raw sample values. |
| Workspace isolation | No accounts. The browser generates a 256-bit key; the server uses `sha256(key)` to scope every query. |
| CSRF | Writes require `X-CSRF-Token = HMAC(secret, workspace‖Origin)`; non-allow-listed origins are refused; CORS is restricted to `PRIVACYTWIN_ALLOWED_ORIGINS`. |
| Input handling | Upload type/size checks, header de-duplication, quoted SQL identifiers, CSV formula-injection guards, user-supplied regexes run with a per-call timeout. |
| Rate limiting | 600 requests/min per client IP; 40 scans/exports per 10 min. |
| Headers | API: `Content-Security-Policy: default-src 'none'`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `X-Frame-Options: DENY`. Frontend headers in `web/vercel.json`. |
| Errors | Generic messages to clients; stack traces only in server logs. |
| Tamper evidence | SHA-256 hash-chained audit log (append-only trigger); evidence-pack manifest hashes, with the manifest hash anchored in the audit chain. |
| Prompt guard | Chat questions are normalised and limited to 300 characters; instruction-override, role-play, system-prompt, raw-data, secret and code-injection prompts get a fixed safe reply and never reach the LLM (logged as `ai.prompt_blocked`); 30 AI requests per 5 minutes per workspace. `privacytwin/guard.py`, `tests/test_guard.py`. |
| LLM (Groq) | Optional, enabled by `GROQ_API_KEY`. Receives workspace **metadata only** (table/column names, classes, signal scores, gap fields, rule IDs). Raw values and masked examples are never sent (`tests/test_llm.py` asserts this). Without a key the app runs fully offline. |

## Secrets

Set `PRIVACYTWIN_SECRET` (CSRF HMAC key) and `PRIVACYTWIN_FINGERPRINT_PEPPER` in production; `render.yaml` generates both. The Groq key is read from `GROQ_API_KEY` or the git-ignored `data/groq-key.txt`. No secrets are committed to this repository.

## Known limitations

- Hashes in the evidence pack detect changes after export; they do not prove authorship (there is no signing key).
- The in-memory rate limiter is per process.
- Workspace keys are bearer secrets stored in the browser's local storage.

## Reporting a vulnerability

Open a GitHub issue titled “Security” **without** exploit details or personal data and ask for a private contact, or use GitHub's private vulnerability reporting if it is enabled. We aim to respond within 7 days.
