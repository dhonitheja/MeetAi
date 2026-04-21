# MeetAI API Reference

## API Header
- Base URL: `http://localhost:8765`
- Authentication: Session-based (auth middleware sets `request.state.user_id`)
- Rate limiting: Applied per-IP via `slowapi`
- All IDs: `hex16` format (16 lowercase hex characters) for local IDs. Provider IDs (`bot_id`, `cus_...`, `sub_...`) follow provider formats.

## /voice

### POST /voice/upload
- Description: Upload a WAV sample and create a reusable encrypted voice profile.
- Request body/params (key fields only): Multipart form with `file` (WAV), query/form `name`, optional `language` (`en` default).
- Response schema (key fields only): `profile_id`, `name`, `language`, `created_at`.
- Auth required: No
- Rate limited: No

### POST /voice/synthesize
- Description: Generate cloned speech from text and stream raw audio bytes.
- Request body/params (key fields only): JSON `text`, `profile_id`.
- Response schema (key fields only): Streaming `audio/raw` response.
- Auth required: No
- Rate limited: No

### POST /voice/synthesize-to-mic
- Description: Generate cloned speech and route it directly to the virtual microphone.
- Request body/params (key fields only): JSON `text`, `profile_id`.
- Response schema (key fields only): `status`.
- Auth required: No
- Rate limited: No

### GET /voice/profiles
- Description: List stored voice profile metadata.
- Request body/params (key fields only): None.
- Response schema (key fields only): Array of `profile_id`, `name`, `language`, `created_at`.
- Auth required: No
- Rate limited: No

### DELETE /voice/profiles/{profile_id}
- Description: Delete a voice profile by ID.
- Request body/params (key fields only): Path `profile_id`.
- Response schema (key fields only): `status`.
- Auth required: No
- Rate limited: No

### GET /voice/devices
- Description: List available output devices used by the virtual mic router.
- Request body/params (key fields only): None.
- Response schema (key fields only): Array of device objects (`index`, `name`, ...).
- Auth required: No
- Rate limited: No

## /face

### POST /face/upload
- Description: Upload one or more reference images and create an encrypted face profile.
- Request body/params (key fields only): Multipart form `files` (1-5 images), query `name`.
- Response schema (key fields only): `profile_id`, `name`, `source_image_hash`, `created_at`.
- Auth required: No
- Rate limited: No

### POST /face/activate/{profile_id}
- Description: Activate a stored face profile for live swapping.
- Request body/params (key fields only): Path `profile_id`.
- Response schema (key fields only): `status`, `profile_id`, `name`.
- Auth required: No
- Rate limited: No

### POST /face/deactivate
- Description: Disable face swap and clear the active target.
- Request body/params (key fields only): None.
- Response schema (key fields only): `status`.
- Auth required: No
- Rate limited: No

### GET /face/profiles
- Description: List stored face profiles (metadata only).
- Request body/params (key fields only): None.
- Response schema (key fields only): Array of `profile_id`, `name`, `source_image_hash`, `created_at`.
- Auth required: No
- Rate limited: No

### DELETE /face/profiles/{profile_id}
- Description: Delete a face profile by ID.
- Request body/params (key fields only): Path `profile_id`.
- Response schema (key fields only): `status`, `profile_id`.
- Auth required: No
- Rate limited: No

### GET /face/status
- Description: Return whether face swap is active and whether the engine is loaded.
- Request body/params (key fields only): None.
- Response schema (key fields only): `active`, `profile_id`, `engine_loaded`.
- Auth required: No
- Rate limited: No

## /meeting

### POST /meeting/join
- Description: Spawn a Recall.ai bot into a validated meeting URL.
- Request body/params (key fields only): JSON `url`, optional `bot_name`.
- Response schema (key fields only): `status`, `bot_id`, `meeting_url`.
- Auth required: No
- Rate limited: No

### GET /meeting/status/{bot_id}
- Description: Fetch current bot status from Recall.ai.
- Request body/params (key fields only): Path `bot_id`.
- Response schema (key fields only): Provider status payload (bot lifecycle fields).
- Auth required: No
- Rate limited: No

### POST /meeting/leave/{bot_id}
- Description: Instruct an active bot to leave a meeting.
- Request body/params (key fields only): Path `bot_id`.
- Response schema (key fields only): Provider leave payload.
- Auth required: No
- Rate limited: No

### POST /meeting/webhook
- Description: Ingest Recall.ai transcript events after strict HMAC verification.
- Request body/params (key fields only): Raw JSON payload + `X-Recall-Signature` header.
- Response schema (key fields only): `status`, `line_processed`.
- Auth required: No (signed webhook required)
- Rate limited: No

### POST /meeting/summarize
- Description: Summarize stored transcript lines for a bot and return action-oriented notes.
- Request body/params (key fields only): JSON `bot_id`.
- Response schema (key fields only): `bot_id`, `summary`.
- Auth required: No
- Rate limited: No

### GET /meeting/active
- Description: List active in-memory meeting bots tracked by the server.
- Request body/params (key fields only): None.
- Response schema (key fields only): `bots` map keyed by `bot_id`.
- Auth required: No
- Rate limited: No

## /persona

### POST /persona/create
- Description: Create and save an encrypted persona that binds voice and face profiles.
- Request body/params (key fields only): JSON `display_name`, `voice_id`, `face_id`, optional `system_prompt`.
- Response schema (key fields only): `persona_id`, `display_name`, `voice_id`, `face_id`, `created_at`.
- Auth required: No
- Rate limited: No

### GET /persona/list
- Description: List persona metadata without encrypted payload contents.
- Request body/params (key fields only): None.
- Response schema (key fields only): Array of `persona_id`, `display_name`, `created_at`.
- Auth required: No
- Rate limited: No

### POST /persona/activate/{persona_id}
- Description: Activate a persona and apply linked face/voice profile selection.
- Request body/params (key fields only): Path `persona_id`.
- Response schema (key fields only): `status`, `persona_id`, `display_name`, `voice_id`, `face_id`.
- Auth required: No
- Rate limited: No

### GET /persona/active
- Description: Return the currently active persona metadata (if any).
- Request body/params (key fields only): None.
- Response schema (key fields only): `active`, `persona_id`, optional profile metadata.
- Auth required: No
- Rate limited: No

### DELETE /persona/delete/{persona_id}
- Description: Delete a persona by ID.
- Request body/params (key fields only): Path `persona_id`.
- Response schema (key fields only): `status`, `persona_id`.
- Auth required: No
- Rate limited: No

## /rag

### POST /rag/upload
- Description: Upload and ingest a PDF or DOCX document into the vector store.
- Request body/params (key fields only): Multipart form `file` (PDF/DOCX, max 20MB).
- Response schema (key fields only): `source`, `chunks`.
- Auth required: No
- Rate limited: No

### GET /rag/files
- Description: List indexed source files and chunk counts.
- Request body/params (key fields only): None.
- Response schema (key fields only): Array of `source`, `chunks`.
- Auth required: No
- Rate limited: No

### DELETE /rag/file/{source_name}
- Description: Delete all chunks associated with a source file.
- Request body/params (key fields only): Path `source_name`.
- Response schema (key fields only): `status`, `chunks_removed`.
- Auth required: No
- Rate limited: No

### POST /rag/query
- Description: Retrieve top matching chunks for query text.
- Request body/params (key fields only): Query `text` (1-500 chars), optional `n_results` (1-10).
- Response schema (key fields only): `results` array (chunk text/metadata).
- Auth required: No
- Rate limited: No

### POST /rag/cleanup
- Description: Remove old documents/chunks beyond the configured retention count.
- Request body/params (key fields only): Query `keep_latest` (1-100, default 20).
- Response schema (key fields only): `status`, `chunks_deleted`.
- Auth required: No
- Rate limited: No

## /billing

### GET /billing/tier/{user_id}
- Description: Return server-side subscription status tier for a user.
- Request body/params (key fields only): Path `user_id`.
- Response schema (key fields only): `user_id`, `tier`.
- Auth required: No
- Rate limited: No

### POST /billing/portal
- Description: Create a Stripe Customer Portal session for the authenticated user.
- Request body/params (key fields only): `request.state.user_id` from auth middleware.
- Response schema (key fields only): `portal_url`.
- Auth required: Yes
- Rate limited: No

### POST /billing/webhook
- Description: Process signed Stripe billing webhooks and sync subscription state.
- Request body/params (key fields only): Raw JSON payload + `Stripe-Signature` header.
- Response schema (key fields only): `status`.
- Auth required: No (signed webhook required)
- Rate limited: No

### POST /billing/checkout
- Description: Create a Stripe Checkout URL for upgrading to `pro` or `team`.
- Request body/params (key fields only): JSON `tier`, `user_id`.
- Response schema (key fields only): `checkout_url`.
- Auth required: No
- Rate limited: No
