# SECURITY

Last updated: 2026-04-21

This document describes security-relevant behavior in the current MeetAI codebase. It is intended for security reviewers, enterprise assessors, and penetration testers.

## 1. Biometric Data Policy

- Voice audio is processed in volatile memory only.
- Raw WAV bytes are not written to persistent storage by the voice upload and embedding pipeline.
- Only derived voice embeddings are persisted, and they are encrypted before disk write.
- Face images are processed in volatile memory only.
- Original face photos are not persisted.
- For face uploads, only `SHA256` source hash metadata (deduplication/audit) and encrypted embeddings are stored.
- Biometric embedding data is encrypted at rest using Fernet with keys derived from machine-scoped environment secrets.
- Biometric artifacts stay on-device unless a user/operator explicitly configures external processing.
- Explicit external integrations in this codebase are:
- `Recall.ai` for meeting bot/transcript webhooks.
- `Stripe` for billing checkout, customer portal, and billing webhooks.

## 2. Encryption Standard

MeetAI profile encryption currently follows this model:

```text
Cipher wrapper: Fernet
Fernet primitives: AES-128-CBC + HMAC-SHA256
KDF: PBKDF2HMAC(SHA256, iterations=480000, length=32 bytes)
KDF password input: PERSONA_MACHINE_ID + PERSONA_USER_SALT
Per-profile salt: os.urandom(16), stored with encrypted payload
```

Scope of encrypted-at-rest profile data:

- Voice profiles (`./data/voice_profiles/*.json`)
- Face profiles (`./data/face_profiles/*.json`)
- Persona profiles (`./data/personas/*.json`)

Key handling:

- Keys are derived on demand during save/load operations.
- Derived keys are held in process memory only.
- Derived keys are not persisted to disk.

## 3. Webhook Security

### Recall.ai transcripts (`POST /meeting/webhook`)

- `X-Recall-Signature` is required.
- Raw body is read first (`await request.body()`), before JSON parsing.
- HMAC-SHA256 verification is performed using `RECALL_WEBHOOK_SECRET`.
- Signature verification occurs before payload processing.
- Missing or invalid signature returns HTTP `401` immediately.

Verification model:

```text
expected = HMAC_SHA256(RECALL_WEBHOOK_SECRET, raw_request_body)
accept if hmac.compare_digest(expected, provided_signature)
```

### Stripe billing (`POST /billing/webhook`)

- `Stripe-Signature` is required.
- Raw body is used for verification.
- Verification is performed via `stripe.Webhook.construct_event(...)` (wrapped by `construct_event(...)`) using `STRIPE_WEBHOOK_SECRET`.
- Subscription state mutation happens only after successful event construction/signature validation.
- Invalid signature returns HTTP `400`.

## 4. API Security Controls

- Rate limiting: SlowAPI limiter is configured with keying based on authenticated user when present, otherwise client IP.
- Input validation: Pydantic models are used for typed request validation on API bodies.
- ID validation: profile/persona IDs are validated using strict full-match patterns, including:

```python
re.fullmatch(r"[a-f0-9]{16}", profile_id)
```

- File upload controls:
- MIME allowlists are enforced on upload endpoints.
- Face upload validates both MIME type and magic bytes.
- Upload size caps are enforced (for example, face images and WAV uploads).
- Global body limit: `MaxBodySizeMiddleware` rejects requests over `50 MB`.
- Paid feature access: subscription tier is verified server-side (`SubscriptionGateMiddleware`) using server-side subscription storage.

## 5. Electron Security

- `contextIsolation: true` in `BrowserWindow` configuration.
- `nodeIntegration: false` in renderer process.
- Screen capture exclusion is applied on overlay window creation via `win.setContentProtection(true)`, which maps to:
- Windows: `SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE)`
- macOS: `NSWindowSharingNone`
- Auto-updater is implemented with `electron-updater`; signature verification is relied on from the updater framework.
- Update feed is locked to static GitHub owner/repo configuration in main-process code (not runtime user-configurable input).
- Global shortcuts are registered in the Electron main process only (`globalShortcut`), not from renderer code.

## 6. Secrets Management

- Required secrets and keys are read from environment variables.
- Startup validation raises `EnvironmentError` when required secrets are missing or malformed.
- `.env` is excluded from source control via `.gitignore`.
- Structured logging is configured via `structlog` (when installed) or Python logging fallback.
- Operational policy: secret values must not be logged.
- CI/CD policy: repository/deployment secrets are expected to be stored in GitHub Actions secrets (or equivalent secure secret store), not in source files.

## 7. Known Limitations

- Authentication is currently implemented with a mock/session-style middleware (`X-User-ID` into `request.state`) and is not a production multi-tenant JWT auth layer.
- ChromaDB local persistence does not add application-layer authentication; do not expose backing storage/ports to untrusted networks.
- Voice/face processing is designed for local execution; if operators deploy cloud GPU/off-device inference, the data-flow threat model changes because data leaves the local machine boundary.
- Linux overlay capture exclusion is not guaranteed equivalent to Windows/macOS protections; overlay visibility may occur depending on compositor/window manager.

## 8. Vulnerability Disclosure

Report security issues to:

- Email: `saitejaragula007@gmail.com`

Disclosure process:

- Initial acknowledgment target: within 72 hours.
- In-scope:
- Production application code
- API endpoints
- Encryption and key-derivation implementation
- Out-of-scope:
- Third-party managed service internals (Stripe, Recall.ai, OpenAI)
- Coordinated disclosure request:
- Do not publish details publicly before a patch or mitigation is available.

