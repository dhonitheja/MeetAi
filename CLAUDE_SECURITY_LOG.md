# 🔒 Claude Security Log — PersonaAI

---

## Sprint 5 — SA-05 Patch Audit

**Timestamp:** 2026-04-21T21:00Z  
**Auditor:** Claude Sonnet 4.6 (Security Role)  
**Scope:** electron/main/auto_updater.js · electron/renderer/preload/shortcuts_api.js · electron/main/keyboard_shortcuts.js · electron/renderer/overlay/UpdateToast.jsx · electron/main/index.js

---

### CONFIRMED FIXED

| ID | Was | File | Now |
|---|---|---|---|
| **M-01** | `update-available` handler called `downloadUpdate()` silently | `auto_updater.js:51-60` | ✅ FIXED — handler sends notification only; comment explicitly states download starts only via user click → `ipcMain.handle('download-update')` |
| **M-01b** | `AppAutoUpdater` class alongside `setupAutoUpdater` — two implementations | `auto_updater.js` | ✅ FIXED — single `setupAutoUpdater` function only; `AppAutoUpdater` class removed |
| **M-01c** | `autoDownload = false` present | `auto_updater.js:36` | ✅ CONFIRMED — still set |
| **M-01d** | Download only via explicit IPC | `auto_updater.js:103-111` — `ipcMain.handle('download-update')` only | ✅ CONFIRMED |
| **M-02** | `contextBridge` exposed `registerShortcuts()` — renderer could trigger main-process registration | `shortcuts_api.js:106-113` | ✅ FIXED — `window.shortcuts` exposes `onVoiceSpeak`, `onFaceToggle`, `removeAll` only; no `registerShortcuts` |
| **M-02b** | `'register-shortcuts'` in `SEND_CHANNELS` | `shortcuts_api.js:22-26` | ✅ FIXED — `SEND_CHANNELS` contains only `'install-now'`, `'update:check'`, `'update:install'` |
| **M-02c** | `ipcMain.on('register-shortcuts')` in keyboard_shortcuts.js | `keyboard_shortcuts.js` | ✅ FIXED — `ipcMain` import removed entirely; file only exports `registerShortcuts` / `unregisterShortcuts` |
| **M-02d** | Shortcuts triggered from main on `did-finish-load` | `index.js:46-47` | ✅ CONFIRMED — `overlayWin.webContents.on('did-finish-load', () => { registerShortcuts(overlayWin); })` |
| **m-05** | `UpdateToast` listened on per-channel names; `auto_updater` sent on `update:status` — mismatch | `UpdateToast.jsx:10-31` | ✅ FIXED — single `window.electronAPI.on("update:status", (_, data) => { switch(data.type) {...} })` matches exactly what `auto_updater.js` sends |

---

### CRITICAL

None.

### MAJOR

None.

### MINOR

**m-01 — `LISTEN_CHANNELS` in preload still contains stale per-channel names**
- File: `shortcuts_api.js:8-15`
- `LISTEN_CHANNELS` includes `'update:available'`, `'update:progress'`, `'update:downloaded'`, `'update:error'`, `'update:checking'` — these are legacy channel names no longer sent by `auto_updater.js`. They're harmless dead entries (channel allowlist validation only blocks, never permits extra). No security impact; cleanup opportunity.

---

### Sprint 5 Final Score: 9 / 10

All CRITICALs: none. All MAJORs resolved. One stale-entry minor. Score limited to 9 by the open m-01 through m-04 minors from the initial SA-05 audit (PersonaManager silent catch, error message exposure in class version now removed, etc.) — all low risk. **Sprint 6 fully unblocked.**

---

## Sprint 5 — Persona + UI + Updater Audit (SA-05)

**Timestamp:** 2026-04-21T20:00Z  
**Auditor:** Claude Sonnet 4.6 (Security Role)  
**Scope:** backend/persona/persona_manager.py · backend/routers/persona.py · electron/main/keyboard_shortcuts.js · electron/main/auto_updater.js · electron/renderer/overlay/OverlayShell.jsx · electron/renderer/overlay/PersonaManager.jsx · electron/renderer/overlay/UpdateToast.jsx · electron/renderer/preload/shortcuts_api.js · electron/main/index.js  
**Note:** `backend/persona/__init__.py` is empty — nothing to audit.

---

### CRITICAL (block merge)

None.

---

### MAJOR (fix before Sprint 6)

**M-01 — `auto_updater.js`: `autoDownload = false` set, but `update-available` handler immediately calls `autoUpdater.downloadUpdate()` — contradicts the flag**
- File: `electron/main/auto_updater.js` (class version read from `index.js` import)
- The `AppAutoUpdater` class at line 21 sets `autoUpdater.autoDownload = false`. Comment says "We want to ask user or at least notify." But the `update-available` event handler at line 36 immediately calls `autoUpdater.downloadUpdate()` with the comment "Auto-download for stealth/silent updates if requested."
- Risk: Download starts without any user interaction or consent. On slow connections this consumes bandwidth silently. More importantly, a supply-chain compromise of the GitHub release would be downloaded and staged without user awareness — `quitAndInstall` is then one IPC message away.
- Note: The `setupAutoUpdater` function version (lines 34-106) correctly does NOT call `downloadUpdate()` on `update-available` — only exposes it via `ipcMain.handle('download-update')`. The `AppAutoUpdater` class version used by `index.js` has the silent-download bug.
- Fix: Remove `autoUpdater.downloadUpdate()` from the `update-available` handler in `AppAutoUpdater`. Let the user trigger download via `UpdateToast`'s Download button (which calls `window.electronAPI.invoke('download-update')` → `ipcMain.handle('download-update')` in `setupAutoUpdater`). The two updater implementations should be consolidated into one.

**M-02 — `contextBridge` exposes `registerShortcuts()` — renderer can trigger main-process shortcut registration**
- File: `electron/renderer/preload/shortcuts_api.js:81-83,134-143`
- Code:
  ```javascript
  function registerShortcuts() {
    ipcRenderer.send('register-shortcuts');
  }
  // ...
  contextBridge.exposeInMainWorld('shortcuts', {
    registerShortcuts,   // ← exposed to renderer
    ...
  });
  ```
- `window.shortcuts.registerShortcuts()` is callable from renderer JavaScript. The `ipcMain.on('register-shortcuts', handleRegisterShortcuts)` handler in `keyboard_shortcuts.js:92` validates the sender window (`BrowserWindow.fromWebContents(event.sender)`) and passes it to `registerShortcuts(win)` — the guard prevents null-window abuse. But exposing registration capability to the renderer violates the checklist requirement and the principle stated in the file's own comment: "Renderer NEVER calls globalShortcut directly." A compromised renderer (XSS in overlay HTML) can call `window.shortcuts.registerShortcuts()` repeatedly, triggering multiple `registerShortcuts(win)` calls. The `_registered` guard prevents double-registration, so the practical risk is low — but the surface exists.
- Fix: Remove `registerShortcuts` from `contextBridge.exposeInMainWorld('shortcuts', {...})`. Registration should be triggered by main process on window-ready event, not by renderer request.

---

### MINOR (tech debt)

**m-01 — `auto_updater.js` has two implementations: `AppAutoUpdater` class and `setupAutoUpdater` function — only class is used**
- `index.js` imports and instantiates `AppAutoUpdater`. The `setupAutoUpdater` function (lines 30-109) is never called and is dead code. The class version has the M-01 silent-download bug; the function version does not. Consolidate into one, use the function version's correct behavior.

**m-02 — `auto_updater.js` error handler sends `err.message` in `AppAutoUpdater` class (line 46)**
- Code: `this._sendStatus('error', err.message || 'Update error')`  
- `err.message` from `electron-updater` can contain internal paths (e.g. `ENOENT /home/user/.config/MeetAi/...`). The `setupAutoUpdater` function version correctly sends generic `'Update check failed'` string. Align class version with function version.

**m-03 — `PersonaManager.jsx`: `fetchAll` empty `catch {}` swallows all errors silently**
- File: `PersonaManager.jsx:52`
- Same pattern flagged in CoPilot.jsx (SA-03 m-01). Add `catch (e) { console.warn('[PersonaManager] fetchAll failed:', e.message); }`.

**m-04 — `persona_manager.py`: `list_personas()` reads envelope fields directly — `system_prompt` not filtered out of plaintext envelope**
- File: `backend/persona/persona_manager.py:158-167`
- The on-disk JSON has two sections: plaintext envelope (`persona_id`, `display_name`, `voice_id`, `face_id`, `created_at`, `salt`, `ciphertext`) and the ciphertext payload (all fields including `system_prompt`). `list_personas()` reads the envelope — `system_prompt` is NOT in the envelope, so it is correctly never returned. ✅ Confirmed clean — downgraded to noted.

**m-05 — `UpdateToast.jsx` uses both `window.electronAPI` and legacy `AppAutoUpdater` event names**
- File: `UpdateToast.jsx:27-37`
- `UpdateToast` listens for `'update:available'`, `'update:progress'`, `'update:downloaded'`, `'update:error'` via `window.electronAPI.on(...)`. The `setupAutoUpdater` function sends `'update:available'`, `'update:progress'`, `'update:downloaded'` — matching. But `AppAutoUpdater` (used by `index.js`) sends `'update:status'` with `{ type, data }` not individual channel names. The `UpdateToast` will never receive events in the current configuration. Consequence: update notifications are silently dropped in production. Fix: align `AppAutoUpdater._sendStatus()` to send per-event channels OR rewrite `UpdateToast` to listen on `'update:status'` and switch on `type`.

---

### APPROVED (checklist items confirmed clean)

| Checklist Item | File:Line | Verdict |
|---|---|---|
| PBKDF2HMAC + SHA256 + 480,000 iterations | `persona_manager.py:67-72` | ✅ CONFIRMED |
| Per-persona `os.urandom(16)` salt | `persona_manager.py:86` | ✅ CONFIRMED |
| Derived key never written to disk | `persona_manager.py:87-88` — key only in local var | ✅ CONFIRMED |
| Fernet used for encryption | `persona_manager.py:88,98` | ✅ CONFIRMED |
| `json.loads` on decryption — no eval/pickle | `persona_manager.py:130` | ✅ CONFIRMED |
| `PERSONA_MACHINE_ID` + `PERSONA_USER_SALT` → `EnvironmentError` if missing | `persona_manager.py:60-65` | ✅ CONFIRMED |
| `persona_manager._validate_id`: `HEX16_PATTERN.fullmatch()` | `persona_manager.py:55` | ✅ CONFIRMED |
| `HEX16_PATTERN = re.compile(r"[a-f0-9]{16}")` — no anchors, fullmatch only | `persona_manager.py:18` | ✅ CONFIRMED |
| `persona.py` router `_validate_id`: `PERSONA_ID_PATTERN.fullmatch()` | `persona.py:24` | ✅ CONFIRMED |
| `voice_id` validator uses `VOICE_ID_PATTERN.fullmatch()` | `persona.py:48` | ✅ CONFIRMED |
| `face_id` validator uses `FACE_ID_PATTERN.fullmatch()` | `persona.py:55` | ✅ CONFIRMED |
| `Persona.__post_init__`: `voice_id` validated with `HEX16_PATTERN.fullmatch()` | `persona_manager.py:33` | ✅ CONFIRMED |
| `Persona.__post_init__`: `face_id` validated with `HEX16_PATTERN.fullmatch()` | `persona_manager.py:35` | ✅ CONFIRMED |
| `"abc12345\n"` rejected — `\n` not in `[a-f0-9]` character class | all fullmatch sites | ✅ CONFIRMED |
| `"../../etc"` rejected — `.` and `/` not in `[a-f0-9]` | all fullmatch sites | ✅ CONFIRMED |
| `system_prompt` control chars stripped `[\x00-\x1f\x7f]` | `persona.py:64` | ✅ CONFIRMED |
| `system_prompt` length capped at 2000 | `persona_manager.py:37`, `persona.py:65` | ✅ CONFIRMED |
| Feed URL hardcoded literal — provider/owner/repo set directly | `auto_updater.js:34-38` | ✅ CONFIRMED |
| No `skipSignatureValidation` flag | full file scan | ✅ CONFIRMED |
| No `disableWebInstaller` flag | full file scan | ✅ CONFIRMED |
| `autoUpdater.autoDownload = false` | `auto_updater.js:41` (setupAutoUpdater), line 21 (AppAutoUpdater) | ✅ SET (see M-01 — AppAutoUpdater overrides via immediate downloadUpdate call) |
| `install-now` IPC calls `quitAndInstall` only — no shell exec | `auto_updater.js:104-107` | ✅ CONFIRMED |
| Error handler sends generic message to renderer | `auto_updater.js:79-81` (setupAutoUpdater) | ✅ CONFIRMED (see m-02 for AppAutoUpdater class) |
| `globalShortcut.register` in main process only | `keyboard_shortcuts.js:34,46,53` | ✅ CONFIRMED |
| Renderer never imports `globalShortcut` | full renderer scan | ✅ CONFIRMED |
| `ipcMain.on('register-shortcuts')` validates sender window | `keyboard_shortcuts.js:84-89` | ✅ CONFIRMED |
| `unregisterShortcuts` called on `app will-quit` | `index.js:69-71` | ✅ CONFIRMED |
| contextBridge exposes listener functions | `shortcuts_api.js:134-143` | ✅ CONFIRMED (see M-02 for `registerShortcuts` exposure) |
| `OverlayShell`: all fetch() calls have try/catch | `OverlayShell.jsx:72-76` — `.catch(() => null)` on each | ✅ CONFIRMED |
| `PersonaManager`: `voice_id`/`face_id` only from API response `profile_id` fields | `PersonaManager.jsx:296-314` — `<select>` populated from `voiceProfiles`/`faceProfiles` fetched from `/voice/profiles`, `/face/profiles` | ✅ CONFIRMED |
| `UpdateToast`: install-now fires only on explicit user click | `UpdateToast.jsx:107` — inside `onClick` handler | ✅ CONFIRMED |
| No API keys or secrets in any React component | full scan of all 3 JSX files | ✅ CONFIRMED |
| No `re.match()` calls in any router (cross-sprint regression) | grep across all routers + persona + meeting + rag | ✅ CONFIRMED — zero hits |

---

### SECURITY SCORE: 8 / 10

No CRITICALs. Two MAJORs:
- M-01: `AppAutoUpdater.update-available` silently calls `downloadUpdate()` — contradicts `autoDownload=false`, silent supply-chain staging risk
- M-02: `contextBridge` exposes `registerShortcuts()` to renderer — violates stated design principle, low-probability XSS amplification surface

Five MINORs (m-01 through m-05), most consequential being m-05 (update notifications silently dropped in production due to event name mismatch). Fix M-01 + M-02 and score reaches 9/10. **Sprint 6 unblocked (score ≥ 8).**

---

## Sprint 4 — M-new-01 Patch Confirmation

**Timestamp:** 2026-04-21T19:00Z  
**Auditor:** Claude Sonnet 4.6 (Security Role)  
**Scope:** `backend/routers/meeting.py` — `BOT_ID_PATTERN` and all call sites

| Check | File:Line | Result |
|---|---|---|
| `BOT_ID_PATTERN` has no `^`/`$` anchors | `routers/meeting.py:25` — `r"[a-zA-Z0-9_-]{8,64}"` | ✅ CONFIRMED |
| `_validate_bot_id` uses `BOT_ID_PATTERN.fullmatch()` | `routers/meeting.py:43` | ✅ CONFIRMED |
| `SummarizeRequest.validate_bot_id` uses `BOT_ID_PATTERN.fullmatch()` | `routers/meeting.py:80` | ✅ CONFIRMED |
| No `.match()` calls remain for `BOT_ID_PATTERN` | full file scan | ✅ CONFIRMED — zero hits |
| `"abc12345\n"` rejected | `fullmatch(r"[a-zA-Z0-9_-]{8,64}", "abc12345\n")` → `None` — `\n` not in character class | ✅ CORRECT |

**Sprint 4 Final Score: 9 / 10.** All CRITICALs and MAJORs resolved. Sprint 5 unblocked.

---

## Sprint 4 — SA-04 Re-audit (Targeted)

**Timestamp:** 2026-04-21T18:00Z  
**Auditor:** Claude Sonnet 4.6 (Security Role)  
**Scope:** backend/routers/meeting.py (new) · backend/meeting/recall_client.py · backend/rag/document_store.py · backend/meeting/transcript_handler.py  
**Purpose:** Verify C-01, C-02, M-01, M-02, M-03 from SA-04 are resolved.

---

### CONFIRMED FIXED

| ID | Was | File | Now |
|---|---|---|---|
| **C-01** | `backend/routers/meeting.py` missing — no webhook HTTP surface | `routers/meeting.py` | ✅ FIXED — file exists, `/meeting/webhook` POST handler implemented |
| **C-01a** | HMAC not validated before JSON parse | `routers/meeting.py:152-168` | ✅ FIXED — raw body read → signature check → 401 if fail → json.loads only after pass |
| **C-01b** | Missing signature not rejected | `routers/meeting.py:155-158` | ✅ FIXED — `if not x_recall_signature: raise HTTPException(401, ...)` |
| **C-01c** | Invalid signature not rejected | `routers/meeting.py:161-164` | ✅ FIXED — `if not handler.verify_webhook_signature(...): raise HTTPException(401, ...)` |
| **C-02** | Webex/Teams `[^\s]+` open wildcard — SSRF | `recall_client.py:11-26` | ✅ FIXED — all patterns use bounded character classes, no `[^\s]+` |
| **C-02a** | Webex subdomain wildcard — any `*.webex.com` accepted | `recall_client.py:23-25` | ✅ FIXED — only `webex.com` and `www.webex.com` |
| **C-02b** | `http://` not pre-screened | `recall_client.py:63` | ✅ FIXED — `if not url.startswith("https://"): return False` |
| **M-01** | `_resolve_source_name` accepted raw metadata — no sanitization at store layer | `document_store.py:347` | ✅ FIXED — `_resolve_source_name` calls `_sanitize_source_name()` before returning |
| **M-01b** | `_sanitize_source_name` did not exist as static method | `document_store.py:350-353` | ✅ FIXED — `_sanitize_source_name(name)` strips `[^a-zA-Z0-9._-]` → `_`, caps at 128 chars |
| **M-02** | Ingest/delete sanitizer mismatch — files with special chars always 404 on delete | `document_store.py:97,217` | ✅ FIXED — both `add_document` (line 97) and `delete_document` (line 217) call `_sanitize_source_name` |
| **M-03** | `on_new_line` race docstring missing | `transcript_handler.py:96-115` | ✅ FIXED — docstring warns about fine-grained locking and post-lock callback behavior |

---

### CRITICAL (block merge)

None.

---

### MAJOR (fix before Sprint 5)

**M-new-01 — `_validate_bot_id` uses `BOT_ID_PATTERN.match()` with `^...$` — `\n` edge case**
- File: `backend/routers/meeting.py:25,43-44` and `80-81`
- Code:
  ```python
  BOT_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{8,64}$")
  
  def _validate_bot_id(bot_id: str) -> str:
      if not BOT_ID_PATTERN.match(bot_id):   # ← re.match + $ has \n edge case
  ```
- `re.match` with `$` anchor: `$` matches before a trailing newline in Python. So `"abc12345\n"` (9 chars) passes `^[a-zA-Z0-9_-]{8,64}$` via `re.match`. The validated ID then enters `_active_bots[bot_id]` dict and is passed to `recall_client.bot_get_status(validated_bot_id)` which constructs `f"{RECALL_API_BASE}/bot/{bot_id}/"`. A trailing newline in an HTTP path is not a header injection (httpx normalizes), but the ID stored in `_active_bots` has a trailing newline — lookup by clean ID will miss it, causing ghost entries.
- Same pattern used in `SummarizeRequest.validate_bot_id` (line 80).
- Fix: Replace `BOT_ID_PATTERN.match(bot_id)` with `BOT_ID_PATTERN.fullmatch(bot_id)` at both call sites, or remove `^`/`$` anchors and use `re.fullmatch(r"[a-zA-Z0-9_-]{8,64}", bot_id)`:
  ```python
  BOT_ID_PATTERN = re.compile(r"[a-zA-Z0-9_-]{8,64}")
  
  if not BOT_ID_PATTERN.fullmatch(bot_id):
      raise HTTPException(400, "Invalid bot_id format")
  ```

---

### MINOR (tech debt)

**m-01 — `MEETING_URL_PATTERNS` use `$` anchor AND `fullmatch()` — double-anchored, redundant**
- File: `recall_client.py:13-25`
- Each pattern has trailing `$` AND `validate_meeting_url()` uses `pattern.fullmatch(url)`. `fullmatch` already anchors both ends — `$` is redundant. No security impact; just cleaner to remove `$` from patterns and rely on `fullmatch`. Low priority.

**m-02 — `/meeting/summarize` transcript formatted as raw f-string — no sanitization before LLM**
- File: `routers/meeting.py:186`
- Code: `formatted = "\n".join(f"{line.speaker}: {line.text}" for line in transcript.lines)`
- `line.speaker` and `line.text` are already sanitized by `TranscriptHandler._sanitize_speaker()` and `_sanitize_text()` at ingest time (✅). No re-sanitization needed here. Confirmed clean — downgraded from concern to noted.

**m-03 — `JoinRequest.validate_url` instantiates `RecallClient()` for URL validation only**
- File: `routers/meeting.py:55-59`
- `RecallClient.__init__` reads `RECALL_API_KEY` from env and raises `EnvironmentError` if missing. This means URL validation in Pydantic raises `ValueError` wrapping `EnvironmentError` — FastAPI converts to 422. Acceptable but odd: URL validation should not depend on API key presence. Consider extracting `MEETING_URL_PATTERNS` / `validate_meeting_url` as a standalone function so validation doesn't require a live client.

---

### CHECKLIST — Section 1 & 2 Final Status

| Checklist Item | File:Line | Verdict |
|---|---|---|
| `/webhook`: HMAC validated before `json.loads()` | `routers/meeting.py:152-168` | ✅ CONFIRMED |
| Missing signature → 401 immediately | `routers/meeting.py:155-158` | ✅ CONFIRMED |
| Invalid signature → 401 immediately | `routers/meeting.py:161-164` | ✅ CONFIRMED |
| No data stored/processed until HMAC passes | `routers/meeting.py:166-172` | ✅ CONFIRMED |
| `bot_id` validated before every route | `routers/meeting.py:43,118,130,179` | ✅ CONFIRMED (see M-new-01 for `match` vs `fullmatch`) |
| `MEETING_URL_PATTERNS` use `fullmatch` | `recall_client.py:65` | ✅ CONFIRMED |
| No `[^\s]+` patterns | `recall_client.py:13-25` | ✅ CONFIRMED — all paths bounded |
| Webex: only `webex.com` + `www.webex.com` | `recall_client.py:23-25` | ✅ CONFIRMED |
| Teams: bounded path chars `[a-zA-Z0-9%._~:@!$&'()*+,;=/-]{10,500}` | `recall_client.py:17-19` | ✅ CONFIRMED |
| `http://` rejected pre-pattern | `recall_client.py:63` | ✅ CONFIRMED |
| `zoom.us.evil.com` subdomain spoofing rejected | `recall_client.py:13` — `zoom\.us` exact match | ✅ CONFIRMED |
| `_sanitize_source_name()` exists as static method | `document_store.py:350-353` | ✅ CONFIRMED |
| `add_document()` calls `_sanitize_source_name` at line 97 | `document_store.py:97` | ✅ CONFIRMED |
| `delete_document()` calls `_sanitize_source_name` at line 217 | `document_store.py:217` | ✅ CONFIRMED |
| Ingest and delete use identical sanitizer | `document_store.py:97,217,347,350` | ✅ CONFIRMED |
| `process_event()` docstring warns about post-lock callback | `transcript_handler.py:96-115` | ✅ CONFIRMED |
| `on_new_line` still wrapped in try/except | `transcript_handler.py:148-152` | ✅ CONFIRMED |
| `verify_webhook_signature` uses `hmac.compare_digest` | `transcript_handler.py:84` | ✅ CONFIRMED |

---

### SPRINT 4 FINAL SCORE: 8 / 10

All CRITICALs resolved. All prior MAJORs resolved. One new MAJOR found (M-new-01: `re.match` + `$` `\n` edge case on `BOT_ID_PATTERN` — the same class of bug fixed in Sprint 3 for face/voice routers). Fix is one-line: `BOT_ID_PATTERN.fullmatch(bot_id)`. Three low-risk MINORs. Score reaches 9/10 after M-new-01 is patched. **Sprint 5 is unblocked (score ≥ 8).**

---

## Sprint 4 — RAG + Meeting Bot Audit (SA-04)

**Timestamp:** 2026-04-21T16:00Z  
**Auditor:** Claude Sonnet 4.6 (Security Role)  
**Scope:** backend/rag/document_store.py · backend/rag/copilot_engine.py · backend/routers/rag.py · backend/meeting/recall_client.py · backend/meeting/transcript_handler.py · electron/renderer/overlay/CoPilot.jsx  
**Missing (audit blocked):**
- `backend/routers/meeting.py` — does not exist. Webhook endpoint (HMAC validation, bot spawn/leave routes) cannot be audited. **Merge blocker** — checklist section 1 (webhook HMAC) is partially unauditable without this file.

---

### CRITICAL (block merge)

**C-01 — `backend/routers/meeting.py` missing — webhook has no HTTP surface**
- Risk: `TranscriptHandler.verify_webhook_signature()` is correctly implemented but nothing calls it via HTTP. No `/meeting/webhook` POST endpoint exists anywhere in the router tree. Recall.ai will POST events to a URL that returns 404. Transcript pipeline is dead. Any future developer adding the route may forget to call `verify_webhook_signature()` first.
- Fix: Deliver `backend/routers/meeting.py` with a `/meeting/webhook` POST handler that:
  1. Reads raw request body before JSON parsing
  2. Calls `handler.verify_webhook_signature(body, sig_header)` — returns 401 if False
  3. Only then calls `handler.process_event(json.loads(body))`

**C-02 — SSRF: Teams and Webex URL patterns not anchored — match accepts arbitrary suffixes**
- File: `backend/meeting/recall_client.py:12-16`
- Code:
  ```python
  re.compile(r"https://teams\.microsoft\.com/l/meetup-join/[^\s]+"),
  re.compile(r"https://[a-zA-Z0-9.-]+\.webex\.com/[^\s]+"),
  ```
- `fullmatch()` is called (line 53: `pattern.fullmatch(url)`) — so `fullmatch` anchors the entire string. This is actually correct for stopping suffix-based bypass. **However**, `[^\s]+` matches any non-whitespace character including `@evil.com`, `#fragment`, `?redirect=http://internal/`. For Webex: `[a-zA-Z0-9.-]+\.webex\.com` matches `evil.webex.com.attacker.com` is rejected by `fullmatch` but `webex.com\x00evil` passes if null byte is in URL before stripping. Main residual risk: Webex pattern allows arbitrary subdomains — `anything.webex.com/payload` passes. Attacker who controls a `*.webex.com` DNS record (or internal DNS) can SSRF to internal services via Recall.ai bot spawn.
- Fix: Restrict Webex to known official hosts:
  ```python
  re.compile(r"https://(?:webex\.com|[\w-]+\.webex\.com)/[A-Za-z0-9/_=-]+"),
  ```
  And add explicit reject for any URL containing `@`, `..`, or control characters before pattern check:
  ```python
  def validate_meeting_url(self, url: str) -> bool:
      if not url.startswith("https://"):
          return False
      if any(c in url for c in ('@', '..', '\x00', '\n', '\r')):
          return False
      return any(pattern.fullmatch(url) for pattern in MEETING_URL_PATTERNS)
  ```

---

### MAJOR (fix before Sprint 5)

**M-01 — `_resolve_source_name` accepts arbitrary `original_filename` from metadata — unsanitized before ChromaDB `where` query**
- File: `backend/rag/document_store.py:323-329`
- Code:
  ```python
  requested_source = metadata.get("original_filename") or metadata.get("source")
  if isinstance(requested_source, str) and requested_source.strip():
      source_name = requested_source.strip()
  ```
- `source_name` flows into `base_meta["source"]` and then into `collection.upsert(metadatas=...)` and `collection.get(where={"source": source})`. ChromaDB's `where` filter uses the value as a string literal, not a query parameter — no SQL injection risk. But an attacker supplying `original_filename: "../../etc/passwd"` stores that string as metadata, which later flows into `delete_document("../../etc/passwd")` → `collection.get(where={"source": "../../etc/passwd"})`. No path traversal at ChromaDB level, but the router's `_sanitize_collection_id` is only applied at the HTTP layer — the `document_store.py` layer itself never sanitizes. If `document_store.add_document()` is called directly (not via router), unsanitized metadata enters ChromaDB.
- Fix: Apply sanitization inside `_resolve_source_name()`:
  ```python
  import re
  _SAFE_SOURCE = re.compile(r"[^a-zA-Z0-9._\- ]")

  @staticmethod
  def _resolve_source_name(file_path, metadata):
      source_name = file_path.name
      if metadata:
          requested = metadata.get("original_filename") or metadata.get("source")
          if isinstance(requested, str) and requested.strip():
              source_name = _SAFE_SOURCE.sub("_", requested.strip())[:128]
      return source_name
  ```

**M-02 — `delete_document` in router accepts URL path param — sanitized to `_sanitize_collection_id` but source lookup may not match**
- File: `backend/routers/rag.py:122-132`
- Code:
  ```python
  safe_name = _sanitize_collection_id(source_name)   # replaces [^a-zA-Z0-9._-] with _
  deleted = store.delete_document(safe_name)
  if deleted == 0:
      raise HTTPException(404, ...)
  ```
- `_sanitize_collection_id` replaces special chars with `_`. If the stored `source` metadata contains the original filename (e.g. `My Resume (2024).pdf`), the sanitized lookup name becomes `My_Resume__2024_.pdf` — no match, always returns 0, always 404. User can never delete a file with spaces/parens via the API. Not a security issue but a functional bug introduced by the sanitizer mismatch.
- Fix: Store the sanitized name at ingest time (already happens via `original_filename` in router's metadata dict — ✓). Ensure `delete_document` is passed the same sanitized form. The path is correct when the router is used end-to-end; the bug only manifests if raw filenames with special chars are stored via direct `add_document()` calls. Covered by M-01 fix above (sanitize at store layer).

**M-03 — `on_new_line` callback called OUTSIDE the lock in `TranscriptHandler.process_event()`**
- File: `backend/meeting/transcript_handler.py:145-149`
- Code:
  ```python
  with self._lock:
      ...
      self._transcripts[bot_id].lines.append(line)

  if self.on_new_line:      # ← lock released before callback
      try:
          self.on_new_line(line)
      ...
  ```
- The lock is released before the callback fires. If `on_new_line` calls `get_recent_lines()` or `get_transcript()` (which both acquire `self._lock`), that's fine — no deadlock. But if a concurrent `clear_meeting(bot_id)` runs between `lines.append` and `on_new_line`, the callback receives a line from a meeting that no longer exists in `_transcripts`. The `line` object itself is safe (it's a dataclass copy), but `on_new_line` may attempt operations on a cleared meeting. Low probability, but real for long-running meetings.
- This is the correct design to avoid holding the lock during a potentially slow callback. The risk is documented: `on_new_line` must not assume the meeting still exists in `_transcripts`.
- Fix: Add a docstring warning. If `on_new_line` needs to look up the meeting, it must handle `None` from `get_transcript()`.

---

### MINOR (tech debt)

**m-01 — `CoPilot.jsx`: empty `catch {}` in `fetchDocCount` silently swallows errors**
- File: `electron/renderer/overlay/CoPilot.jsx:30`
- `catch {}` with no body means network errors during doc count fetch are invisible. Add `catch (e) { console.warn('[CoPilot] fetchDocCount failed:', e.message); }`.

**m-02 — `CoPilot.jsx`: `suggestion` rendered as raw text — XSS not possible (React escapes by default)**
- File: `CoPilot.jsx:164` — `{suggestion}` inside `<p>` tag. React's JSX escapes string content — no `dangerouslySetInnerHTML`. No XSS risk. Confirmed clean.

**m-03 — `document_store.py`: `_fallback_mode` reads raw file bytes with `decode("utf-8", errors="replace")` — no magic byte check**
- File: `backend/rag/document_store.py:243-244`
- Fallback mode reads any file bytes as text without magic byte validation. Router performs magic byte check before calling `add_document()` — so this is only exploitable if `add_document()` is called directly in fallback mode with a non-PDF/DOCX file. Defense-in-depth: add magic byte check inside `_add_document_fallback()`.

**m-04 — `recall_client.py`: `webhook_url` passed to Recall.ai API without validation**
- File: `backend/meeting/recall_client.py:83-86`
- If `bot_spawn()` is called with a caller-supplied `webhook_url`, that URL is forwarded to Recall.ai with no validation. Recall.ai will POST transcript events to it — an attacker who controls `webhook_url` receives live meeting audio transcripts.
- This is not a direct SSRF (Recall.ai makes the HTTP call, not the server), but it is a data exfiltration vector if `webhook_url` is user-controlled.
- Fix: If `webhook_url` is derived from config (not user input), document that. If it can come from a user request, validate it is a known internal endpoint.

**m-05 — `COLLECTION_NAME = "meetai_docs"` hardcoded constant — confirmed not user-controlled**
- File: `backend/rag/document_store.py:30`
- `self.client.get_or_create_collection(name=COLLECTION_NAME)` — hardcoded string. No user input reaches collection name. ✅ Confirmed clean.

---

### APPROVED (checklist items confirmed clean)

| Checklist Item | File:Line | Verdict |
|---|---|---|
| `RECALL_API_KEY`: `os.environ` only, `EnvironmentError` if missing | `recall_client.py:35-39` | ✅ CONFIRMED |
| `RECALL_WEBHOOK_SECRET`: `os.environ` only, `logger.critical` if missing | `transcript_handler.py:71-77` | ✅ CONFIRMED |
| `hmac.compare_digest` used — no timing attack | `transcript_handler.py:84` | ✅ CONFIRMED |
| `bot_id` validated `re.fullmatch(r"[a-zA-Z0-9_-]{8,64}", bot_id)` | `recall_client.py:103,118` | ✅ CONFIRMED |
| `validate_meeting_url()` called inside `bot_spawn()` before API call | `recall_client.py:70-74` | ✅ CONFIRMED |
| Zoom pattern: HTTPS only, anchored subdomain, numeric meeting ID | `recall_client.py:12` | ✅ CLEAN |
| Google Meet pattern: HTTPS, exact 3-4-3 code format | `recall_client.py:14` | ✅ CLEAN |
| `fullmatch()` used — not `match()` or `search()` | `recall_client.py:53` | ✅ CONFIRMED |
| Transcript wrapped in labelled block before LLM | `copilot_engine.py:179-190` | ✅ CONFIRMED |
| System prompt instructs LLM to ignore transcript commands | `copilot_engine.py:38-39` | ✅ CONFIRMED |
| `_sanitize_transcript()` strips control chars `[\x00-\x1f\x7f]` | `copilot_engine.py:84` | ✅ CONFIRMED |
| No raw user text in f-string prompts — all via `_sanitize_transcript()` | `copilot_engine.py:154,176` | ✅ CONFIRMED |
| PDF magic bytes `b"%PDF"` (4 bytes) | `routers/rag.py:51-52` | ✅ CORRECT |
| DOCX magic bytes `b"PK\x03\x04"` (ZIP header) | `routers/rag.py:53-54` | ✅ CORRECT |
| File size capped at 20MB | `routers/rag.py:27,84-86` | ✅ CONFIRMED |
| Temp file deleted in `finally` block | `routers/rag.py:108-110` | ✅ CONFIRMED |
| `source_name` sanitized via `_sanitize_collection_id` before ChromaDB | `routers/rag.py:102,128` | ✅ CONFIRMED (see M-01 for defense-in-depth gap) |
| `COLLECTION_NAME = "meetai_docs"` hardcoded — never user-controlled | `document_store.py:30` | ✅ CONFIRMED |
| `delete_document()` `source_name.strip()` — no path construction | `document_store.py:208-227` | ✅ CONFIRMED |
| `self._lock` on every read/write of `_transcripts` | `transcript_handler.py:140-143,157-167,170-172` | ✅ CONFIRMED |
| `on_new_line` callback in try/except | `transcript_handler.py:146-149` | ✅ CONFIRMED |
| `MeetingTranscript.lines` modified only under lock | `transcript_handler.py:140-143` | ✅ CONFIRMED |
| `CoPilot.jsx`: `latestTranscript.slice(0, 500)` before API call | `CoPilot.jsx:55` | ✅ CONFIRMED |
| `CoPilot.jsx`: main query fetch in try/catch/finally | `CoPilot.jsx:53-83` | ✅ CONFIRMED |
| No API keys or secrets in React component | `CoPilot.jsx` full scan | ✅ CLEAN |

---

### SECURITY SCORE: 6 / 10

**Two CRITICALs block Sprint 5:**
- C-01: `backend/routers/meeting.py` missing — no HTTP surface for webhook, HMAC validation dead letter
- C-02: Webex/Teams SSRF patterns — `[^\s]+` allows arbitrary path/query content; Webex subdomain wildcard

**Three MAJORs** require fixes before Sprint 5. Fix C-01 + C-02 + M-01 and score reaches 8/10. Sprint 5 does not start until score ≥ 8.

---

## Sprint 3 — SA-03 IPC Follow-up Audit

**Timestamp:** 2026-04-21T14:00Z  
**Auditor:** Claude Sonnet 4.6 (Security Role)  
**Scope:** electron/main/screen_protection.js · electron/main/share_detector.js · backend/stealth/screen_protection.py  
**Also verified:** M-new-01 (get_target_embedding) · M-new-02 (upload_face race) · M-new-03 (duplicate /health)

---

### CONFIRMED FIXED (M-new items from SA-03 Final)

| ID | Was | File | Now |
|---|---|---|---|
| **M-new-01** | `get_target_embedding()` missing — race in `upload_face` | `face_swap_engine.py:202-211` | ✅ FIXED — method exists, `self._lock` + `.copy()` |
| **M-new-02** | `upload_face` read `engine._lock`/`_target_face` directly | `routers/face.py:125-128` | ✅ FIXED — calls `engine.get_target_embedding()` |
| **M-new-03** | Duplicate `@app.get("/health")` — first handler unreachable | `server.py` | ✅ FIXED — single handler at line 538 |

---

### Section 6 — Electron / IPC Audit

#### `electron/main/share_detector.js`

**[ ✅ ] `exec()` has `timeout: 3000` on every call**
- Line 64: `exec(cmd, { timeout: 3000 }, (err, stdout) => {`
- Timeout applied on the sole `exec()` call. Stale process list cannot hang the poll loop.

**[ ✅ ] `exec()` stdout used only for string matching — no eval(), no shell**
- Lines 70-73: `stdout.toLowerCase()` → `.includes(name.toLowerCase())` only.
- `stdout` is never passed to `eval()`, `new Function()`, `shell`, `exec()` recursively, or any interpreter. MEETING_PROCESSES entries are hardcoded constants — not derived from stdout.

**[ ✅ ] Callbacks `onShareStart` / `onShareEnd` wrapped in try/catch**
- Lines 78-81 and 86-89: both callbacks wrapped in `try { this.onShareStart?.() } catch (e) { console.error(...) }`.
- Callback throw cannot crash the poll interval.

**[ ✅ ] No user input reaches `exec()` command construction**
- `cmd` is a ternary over `process.platform` — hardcoded strings `'tasklist /FO CSV /NH'` and `'ps -e -o comm='`. No external variable interpolated into the command string. No injection surface.

**MINOR — m-01:** `targets` list on Linux is empty (`[]`) — `_poll()` returns early at line 57. Correct behavior but not logged. Consider `console.log('[ShareDetector] Linux: process detection not supported, polling disabled')` once at `start()` for operator visibility.

---

#### `electron/main/screen_protection.js`

**[ ✅ ] `setContentProtection()` receives no user input**
- `ElectronScreenProtection.apply(win)` calls `win.setContentProtection(true)` — hardcoded boolean, no external value. The `win` parameter is a `BrowserWindow` reference from Electron internals — not constructed from user data.

**[ ✅ ] Null/destroyed window guard present**
- Line 21: `if (!win || win.isDestroyed()) { console.error(...); return false; }` — prevents crash on stale window reference.

**[ ✅ ] `setContentProtection` call wrapped in try/catch**
- Lines 25-32: exceptions from the Electron API caught, logged, return false.

**[ ✅ ] `remove()` has debug warning**
- Line 51: `console.warn('[ScreenProtection] REMOVED - debug only, do not ship')` — clear signal if called accidentally in production.

**MINOR — m-02:** `remove()` has no guard against destroyed window — `win.setContentProtection(false)` would throw. Trivial fix: mirror the null check from `apply()`.

---

#### `backend/stealth/screen_protection.py`

**[ ✅ ] No user input reaches ctypes calls**
- `apply(hwnd: int)` — `hwnd` typed as `int`. `SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)` passes the integer handle and a hardcoded constant. No string formatting, no shell, no path construction from `hwnd`.

**[ ✅ ] Linux no-op: logs warning, returns False, does not crash**
- Lines 26-29: `else:` branch logs `logger.warning(...)` and `return False`. No import errors, no ctypes calls, no exception possible.

**[ ✅ ] Windows path wrapped in try/except — returns False on failure**
- Lines 33-43: all ctypes calls in try block, `logger.error` on failure, `return False`.

**[ ✅ ] macOS path wrapped in try/except — `ImportError` handled separately**
- Lines 45-60: `ImportError` caught with install hint; generic `Exception` caught. Both return False.

**[ ✅ ] `verify()` Windows path uses `ctypes.byref` correctly — no buffer overflow risk**
- Line 67: `ctypes.c_uint32(0)` allocated on Python heap, `GetWindowDisplayAffinity` writes into it via `ctypes.byref`. Correct ctypes pattern.

**MINOR — m-03:** `_apply_windows` and `_apply_macos` use f-string in `logger.info/error` (lines 37, 39, 53) — minor: prefer `%s` lazy formatting (`logger.info("... hwnd=%s", hwnd)`) to avoid string construction cost when log level is above INFO.

**MINOR — m-04:** `WDA_EXCLUDEFROMCAPTURE = 0x00000011` — value is correct per Windows SDK (Win10 19041+). No issue. Note: on Windows < 19041 `SetWindowDisplayAffinity` accepts only `WDA_NONE (0)` or `WDA_MONITOR (1)` — `0x11` returns failure. Current code logs the error code via `ctypes.get_last_error()` correctly. Document the build requirement in README.

---

### CRITICAL (block merge)

None.

---

### MAJOR (fix before Sprint 4)

None. All prior MAJORs resolved.

---

### MINOR (tech debt)

| ID | File | Note |
|---|---|---|
| m-01 | `share_detector.js:start()` | Add one-time log on Linux that polling is disabled |
| m-02 | `screen_protection.js:remove()` | Add null/destroyed-window guard (mirror `apply()`) |
| m-03 | `screen_protection.py:37,39,53` | Use `%s` lazy logging instead of f-strings |
| m-04 | `screen_protection.py` | Document Win10 19041+ build requirement |

---

### APPROVED (section 6 — all checklist items passed)

| Checklist Item | File:Line | Verdict |
|---|---|---|
| `exec()` has `timeout: 3000` | `share_detector.js:64` | ✅ CONFIRMED |
| `exec()` stdout — string match only, no eval/shell | `share_detector.js:70-73` | ✅ CONFIRMED |
| `setContentProtection()` receives no user input | `screen_protection.js:26` | ✅ CONFIRMED |
| `onShareStart` callback in try/catch | `share_detector.js:78-81` | ✅ CONFIRMED |
| `onShareEnd` callback in try/catch | `share_detector.js:86-89` | ✅ CONFIRMED |
| No user input reaches ctypes calls | `screen_protection.py:18-20,35` | ✅ CONFIRMED |
| Linux no-op — logs warning, returns False | `screen_protection.py:26-29` | ✅ CONFIRMED |
| `get_target_embedding()` thread-safe via `self._lock` + `.copy()` | `face_swap_engine.py:202-211` | ✅ CONFIRMED |
| `upload_face()` calls `get_target_embedding()` — no direct `_lock` access | `routers/face.py:125` | ✅ CONFIRMED |
| Single `/health` endpoint | `server.py:538` | ✅ CONFIRMED |

---

### SPRINT 3 FINAL SCORE: 9 / 10

All CRITICALs resolved. All MAJORs resolved (including M-new-01/02/03). IPC section fully audited — no issues found beyond 4 MINORs. One point deducted for 4 open MINORs (m-01 through m-04 above) which are low-risk but should be cleaned before Sprint 4 ships to production. **Sprint 4 is unblocked.**

---

## Sprint 3 — Final Security Audit (SA-03)

**Timestamp:** 2026-04-21T12:00Z  
**Auditor:** Claude Sonnet 4.6 (Security Role)  
**Scope:** face_swap_engine.py · face_profile_manager.py · virtual_cam_router.py · routers/face.py · server.py · src/voice/voice_profile.py  
**Missing (not yet delivered — checklist items blocked):**
- `backend/stealth/screen_protection.py` — does not exist
- `electron/main/screen_protection.js` — does not exist
- `electron/main/share_detector.js` — does not exist
- `electron/renderer/overlay/FaceClone.jsx` — does not exist

Checklist sections 6 (Electron/IPC) and stealth items remain **blocked** until these files are delivered.

---

### CONFIRMED FIXED (previous CRITICALs/MAJORs now resolved)

| ID | Was | File | Now |
|---|---|---|---|
| **C-01** (prior) | `_run_swap()` calls `get_model()` per frame — TOCTOU + fd exhaustion | `face_swap_engine.py:155-165` | ✅ FIXED — uses `self.swapper` + null check |
| **C-02** (prior) | WebP check only validates `RIFF` prefix — WAV/AVI passes | `routers/face.py:44` | ✅ FIXED — `data[:4]==b"RIFF" and data[8:12]==b"WEBP"` |
| **C-03** (voice) | `torch.load()` TypeError fallback drops `weights_only=True` — pickle RCE | `src/voice/voice_profile.py:112` | ✅ FIXED — `torch.load(..., weights_only=True)` only, no try/except |
| **M-01** (prior) | `engine._lock`/`_target_face` accessed directly from router — bypass safe interface | `routers/face.py:145-158` | ✅ FIXED — `activate_face()` calls `engine.set_target_from_embedding()` |
| **M-01b** (prior) | `re.match` in `face_profile_manager._validate_profile_id` — `\n` edge case | `face_profile_manager.py:49` | ✅ FIXED — `re.fullmatch(r"[a-f0-9]{16}", ...)` |
| **M-01c** (prior) | `re.match` in `routers/face.py _validate_profile_id` | `routers/face.py:33` | ✅ FIXED — `re.fullmatch(r"[a-f0-9]{16}", ...)` |
| **M-02** (prior) | `activate` endpoint directly mutated `engine._target_face` | `routers/face.py:145-158` | ✅ FIXED — calls `set_target_from_embedding()` |
| **M-03** (prior) | `CameraError` logged as `logger.critical` — wrong severity | `virtual_cam_router.py:64-69` | ✅ FIXED — `logger.error(...)` |
| **M-04** (prior) | No `MaxBodySizeMiddleware` in server.py | `server.py:515-527` | ✅ FIXED — `MaxBodySizeMiddleware` at 50MB, added before routers |

---

### CRITICAL (block merge)

None. All prior CRITICALs confirmed resolved.

---

### MAJOR (fix before Sprint 4)

**M-01 — `upload_face` reads embedding directly from `engine._lock` block**
- File: `backend/routers/face.py:125-128`
- Code:
  ```python
  with engine._lock:
      raw_embedding = engine._target_face.embedding if engine._target_face else None
  ```
- `set_target_from_embedding()` now exists and is used by `activate_face()` — but `upload_face()` still reaches into `engine._lock` + `_target_face` directly to extract the embedding after `set_target_face()`. The pattern is: call `engine.set_target_face(image_bytes)` → then immediately lock and read `engine._target_face.embedding`.
- Risk: `set_target_face()` acquires `self._lock` internally. The router then immediately acquires the same lock. Between those two acquisitions, a concurrent `deactivate_face()` call (which calls `clear_target()`) can null out `_target_face`, causing `raw_embedding is None` at line 127. Low-probability race but non-zero.
- Fix: Add `FaceSwapEngine.get_target_embedding() -> np.ndarray | None` that locks, copies, and returns the embedding. Router calls that after `set_target_face()`.

**M-02 — `delete_face_profile` returns 200 on missing profile in old code path**
- File: `backend/routers/face.py:174-182`
- Current code **correctly** raises `HTTPException(404)` when `FileNotFoundError` from `_manager.delete()` — this is fixed. Confirmed OK. Downgraded to minor note: delete raises `FileNotFoundError` (line 152 of face_profile_manager.py) only when `path.exists()` is False — correct.
- **No action needed.** Reclassified as APPROVED.

**M-03 — Duplicate `@app.get("/health")` in server.py**
- File: `backend/server.py:539` and `backend/server.py:594`
- Two `@app.get("/health")` handlers registered. FastAPI/Starlette uses the last registered route — the first handler (detailed face/voice/rag status) is silently shadowed by the second (simple ok/whisper/rag/llm). The detailed health endpoint is unreachable.
- Fix: Merge into one handler or rename one to `/health/detail`.

---

### MINOR (tech debt)

**m-01 — `ONNX session` (`self.swapper`) not explicitly released in `unload()`**
- File: `backend/face/face_swap_engine.py:202-215`
- `self.swapper = None` drops the Python reference but native C++ ONNX runtime context may not free until GC runs. Not a security issue; GPU/CPU memory leak risk on rapid reload cycles.

**m-02 — `source_image_hash` exposed in `ProfileResponse`**
- File: `backend/routers/face.py:49-52, 137-142`
- SHA256 of source image returned to API client. Two profiles using same photo share the same hash — leaks identity correlation. Consider omitting or returning only first 8 chars as a dedup hint.

**m-03 — `new FaceSwapEngine()` + `load()` may run twice on startup**
- File: `backend/server.py:481-512`
- Both `lifespan()` (line 497) and `@app.on_event("startup")` (line 507) call `_bootstrap_face_engine()`. The guard `if face_module._engine is not None: return` prevents double-init in practice, but `@app.on_event("startup")` is deprecated in FastAPI — the duplicate is dead code. Remove `@app.on_event("startup")` handler.

**m-04 — Electron/stealth/frontend files still missing (4 files)**
- `backend/stealth/screen_protection.py`, `electron/main/screen_protection.js`, `electron/main/share_detector.js`, `electron/renderer/overlay/FaceClone.jsx` — all absent. Checklist items 1.4 (screen protection), 6 (Electron IPC) cannot be completed. Treat as **Sprint 4 merge blocker** until delivered and audited.

---

### APPROVED (checklist items confirmed clean)

| Checklist Item | File:Line | Verdict |
|---|---|---|
| C-01 fixed: `_run_swap()` uses `self.swapper`, no `get_model()` | `face_swap_engine.py:155-165` | ✅ CONFIRMED FIXED |
| C-02 fixed: WebP check `data[:4]==b"RIFF" and data[8:12]==b"WEBP"` | `routers/face.py:44` | ✅ CONFIRMED FIXED |
| C-03 fixed: `torch.load(..., weights_only=True)` only, no fallback | `src/voice/voice_profile.py:112` | ✅ CONFIRMED FIXED |
| M-01 fixed: `re.fullmatch` in `face_profile_manager._validate_profile_id` | `face_profile_manager.py:49` | ✅ CONFIRMED FIXED |
| M-01 fixed: `re.fullmatch` in `routers/face._validate_profile_id` | `routers/face.py:33` | ✅ CONFIRMED FIXED |
| M-02 fixed: `activate_face()` calls `engine.set_target_from_embedding()` | `routers/face.py:157` | ✅ CONFIRMED FIXED |
| M-03 fixed: `CameraError` logged via `logger.error` | `virtual_cam_router.py:64-69` | ✅ CONFIRMED FIXED |
| M-04 fixed: `MaxBodySizeMiddleware` at 50MB before routers | `server.py:515-527` | ✅ CONFIRMED FIXED |
| `set_target_from_embedding()` exists and is thread-safe (`self._lock`) | `face_swap_engine.py:167-180` | ✅ CLEAN |
| `set_target_face()` — image bytes never written to disk | `face_swap_engine.py:96-124` | ✅ CLEAN |
| `process_frame()` — no frames saved to disk | `face_swap_engine.py:126-153` | ✅ CLEAN |
| `FaceProfileManager.save()` — embedding encrypted before disk write | `face_profile_manager.py:72-101` | ✅ CLEAN |
| `source_image_hash` = SHA256 only, original image never stored | `face_profile_manager.py:22` | ✅ CLEAN |
| PBKDF2 iterations = 480,000 | `face_profile_manager.py:68` | ✅ CORRECT |
| Per-profile `os.urandom(16)` salt | `face_profile_manager.py:85` | ✅ CORRECT |
| `PERSONA_MACHINE_ID` + `PERSONA_USER_SALT` → `EnvironmentError` if missing | `face_profile_manager.py:57-62` | ✅ CORRECT |
| `np.load(buffer, allow_pickle=False)` | `face_profile_manager.py:120` | ✅ CORRECT |
| MIME whitelist: jpeg/png/webp only | `routers/face.py:19` | ✅ CLEAN |
| JPEG magic `\xff\xd8\xff` | `routers/face.py:40` | ✅ CORRECT |
| PNG magic `\x89PNG` | `routers/face.py:41` | ✅ CORRECT |
| WebP magic `RIFF????WEBP` | `routers/face.py:44` | ✅ CORRECT |
| Max 5MB per image | `routers/face.py:96-98` | ✅ CORRECT |
| Max 5 images per upload | `routers/face.py:82-83` | ✅ CORRECT |
| `profile_id` `re.fullmatch([a-f0-9]{16})` in router | `routers/face.py:33` | ✅ CLEAN |
| `delete()` raises `FileNotFoundError` → API 404 | `face_profile_manager.py:151-153`, `routers/face.py:178-181` | ✅ CORRECT |
| `pyvirtualcam.Camera` used as context manager | `virtual_cam_router.py:48-63` | ✅ CORRECT |
| `CAMERA_ERROR` caught (with AttributeError fallback) | `virtual_cam_router.py:14-16, 64` | ✅ CORRECT |
| `running` flag set to `False` in `finally` | `virtual_cam_router.py:73-74` | ✅ CORRECT |
| `torch.cuda.empty_cache()` in `unload()` | `face_swap_engine.py:208-213` | ✅ CORRECT |
| `MaxBodySizeMiddleware` added before router registration | `server.py:527, 564-565` | ✅ CORRECT |

---

### SECURITY SCORE: 8 / 10

All prior CRITICALs resolved. All prior MAJORs resolved except one new MAJOR (M-01 — embedding extraction race in `upload_face`). One server-level MAJOR (M-03 — duplicate `/health` route, dead code). Four frontend/stealth files still missing — full score impossible until delivered. Score on audited files: **8/10**. Sprint 4 may proceed on audited backend files; Electron/stealth audit is a **Sprint 4 gate**, not a Sprint 3 blocker.

---

## Sprint 3 — Vision & Stealth Audit

**Timestamp:** 2026-04-21T00:00Z  
**Auditor:** Claude Sonnet 4.6 (Security Role)  
**Scope:** face_swap_engine.py · face_profile_manager.py · virtual_cam_router.py · routers/face.py  
**Missing (not yet delivered — audit blocked):**
- `backend/stealth/screen_protection.py` — does not exist
- `electron/main/screen_protection.js` — does not exist
- `electron/main/share_detector.js` — does not exist
- `electron/renderer/overlay/FaceClone.jsx` — does not exist

All four are **merge blockers** until delivered and audited. Log entries will be added when files exist.

---

### CRITICAL (block merge)

**C-01 — `_run_swap()` reloads ONNX model from disk on every frame**
- File: `backend/face/face_swap_engine.py:146-150`
- Code:
  ```python
  def _run_swap(self, frame, source_face):
      swapper = insightface.model_zoo.get_model(
          str(INSWAPPER_PATH),           # ← disk load every call
          providers=[...]
      )
      return swapper.get(frame, source_face, target, paste_back=True)
  ```
- Risk: `INSWAPPER_PATH` is a module-level `Path` constant — not user-controllable, so no injection. But `get_model()` accepts a filesystem path and re-opens the ONNX file on every frame (24-30 fps). Two consequences: (1) at 30fps this is ~30 file opens/sec, trivially exhausting file descriptors under load; (2) if an attacker can swap `inswapper_128.onnx` between the `load()` integrity check and a `_run_swap()` call (TOCTOU), they load an arbitrary ONNX model. The ONNX runtime executes graph ops — a crafted model can exfiltrate memory.
- Fix: Use `self.swapper` (the `ort.InferenceSession` already loaded in `load()`) instead of calling `get_model()` again:
  ```python
  def _run_swap(self, frame, source_face):
      try:
          with self._lock:
              target = self._target_face
          # Use pre-loaded session — do NOT call get_model() here
          return self.swapper.get(frame, source_face, target, paste_back=True)
      except Exception as exc:
          logger.error("Face swap failed for frame: %s", exc)
          return frame
  ```

**C-02 — WebP magic byte check only verifies RIFF header, not WEBP subtype**
- File: `backend/routers/face.py:21-25, 66-68`
- Code:
  ```python
  ALLOWED_MAGIC_BYTES = (
      b"\xff\xd8\xff",   # JPEG
      b"\x89PNG",        # PNG
      b"RIFF",           # WebP — INCOMPLETE
  )
  # ...
  if mime_type == "image/webp" and data[:4] == ALLOWED_MAGIC_BYTES[2]:
      return True
  ```
- Risk: Any RIFF file (WAV audio, AVI video, others) passes as `image/webp`. An attacker submits a crafted RIFF-prefixed payload — `cv2.imdecode` will likely return `None` (caught) but format-confusion vulns in OpenCV's RIFF parsing are a known class. WebP RIFF chunk must be `RIFF????WEBP`.
- Fix:
  ```python
  if mime_type == "image/webp" and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
      return True
  ```

---

### MAJOR (fix this sprint)

**M-01 — `engine._lock` and `engine._target_face` accessed directly from router**
- File: `backend/routers/face.py:167-168, 208-209, 259`
- Code:
  ```python
  with engine._lock:
      raw_embedding = engine._target_face.embedding if engine._target_face else None
  # ...
  with engine._lock:
      engine._target_face = face
  ```
- Risk: Router directly mutates private engine state, bypassing `set_target_face()` and `clear_target()` which are the intended safe interfaces. If `FaceSwapEngine` is ever refactored, router silently breaks or creates races. Also: `engine._target_face = face` at line 209 sets an `insightface.app.common.Face` object, but `process_frame()` and `_run_swap()` at line 144 read `self._target_face` and call `swapper.get(..., target, ...)` — type must match what inswapper expects. No type check here.
- Fix: Add `FaceSwapEngine.set_target_embedding(embedding: np.ndarray)` method. Router calls that instead of directly writing `_target_face`.

**M-02 — `_validate_profile_id` in `face_profile_manager.py` uses `re.match` not `re.fullmatch`**
- File: `backend/face/face_profile_manager.py:53`
- Code:
  ```python
  if not re.match(r"^[a-f0-9]{16}$", profile_id):
  ```
- `re.match` with `^...$` anchors is functionally equivalent to `re.fullmatch` here — `$` matches end of string (or before a trailing `\n`). The `\n` edge case: `"abcdef1234567890\n"` passes `re.match(r"^[a-f0-9]{16}$", ...)` because `$` matches before the newline in Python's `re`. This would construct path `./data/face_profiles/abcdef1234567890\n.json` — filesystem-dependent behavior.
- Fix: Replace with `re.fullmatch(r"[a-f0-9]{16}", profile_id)` (no anchors needed, `fullmatch` matches entire string including newlines in string):
  ```python
  if not re.fullmatch(r"[a-f0-9]{16}", profile_id):
  ```

**M-03 — `pyvirtualcam.error.CameraError` logged as `CRITICAL` — wrong severity**
- File: `backend/face/virtual_cam_router.py:56-61`
- `CRITICAL` in Python logging conventionally means the process cannot continue and should exit. A missing virtual camera is a configuration issue; the process continues fine in pass-through mode. `logger.critical(...)` triggers any `CRITICAL`-level alerting/paging. Use `logger.error(...)`.

**M-04 — `upload_face` reads full file body before size check on first loop iteration**
- File: `backend/routers/face.py:135-140`
- MIME check happens before reads (line 124-129, ✓), but size check happens *after* reading `MAX_IMAGE_SIZE + 1` bytes into RAM. With `MAX_IMAGES=5` concurrent, peak is 5 × 5MB+1 = ~25MB per request. Under concurrent load this is acceptable but should be documented. No middleware-level body size limit in the router.
- Recommendation: add `ContentSizeLimitMiddleware` at the FastAPI app level (5MB × 5 = 25MB limit).

---

### MINOR (tech debt)

**m-01 — `ONNX session` (`self.swapper`) not explicitly released in `unload()`**
- File: `backend/face/face_swap_engine.py:175-188`
- `self.swapper = None` drops the Python reference but `ort.InferenceSession` holds a native C++ ONNX runtime context. Explicit release: `del self.swapper; self.swapper = None`. Not a security issue; GPU/CPU memory may not free until GC runs.

**m-02 — `source_image_hash` returned in `ProfileResponse` API response**
- File: `backend/routers/face.py:83-97`
- SHA256 of the source image is returned to the API client. If the same person's photo is used across profiles, hashes match — leaking that two profiles use the same source image. Consider omitting from the response model or returning only first 8 chars as a dedup hint.

**m-03 — No audit trail for face activation / deactivation**
- File: `backend/routers/face.py:187-223`
- `/activate` and `/deactivate` have no logging of which profile was activated or when. For a biometric system this is a compliance gap. Add `logger.info("Face profile activated: %s", validated_profile_id)` at minimum.

**m-04 — Missing Electron/frontend files (4 of 8 audited files)**
- `backend/stealth/screen_protection.py`, `electron/main/screen_protection.js`, `electron/main/share_detector.js`, `electron/renderer/overlay/FaceClone.jsx` were not delivered for this sprint. Checklist items 1.5 (stealth), 5 (IPC security) cannot be completed. **Must be audited before Sprint 4 merge.**

---

### APPROVED (zero issues found)

| File / Function | Verdict |
|---|---|
| `set_target_face()` — image bytes never written to disk | ✅ CLEAN |
| `process_frame()` — no frames saved to disk | ✅ CLEAN |
| `FaceProfileManager.save()` — embedding encrypted before any disk write | ✅ CLEAN |
| `source_image_hash` = SHA256 only, original image never stored | ✅ CLEAN |
| `clear_target()` — `_target_face` explicitly set to `None` | ✅ CLEAN |
| PBKDF2 iterations = 480,000 | ✅ CORRECT |
| Per-profile `os.urandom(16)` salt | ✅ CORRECT |
| `PERSONA_MACHINE_ID` + `PERSONA_USER_SALT` — `EnvironmentError` if missing | ✅ CORRECT |
| `np.load(buffer, allow_pickle=False)` — no pickle execution | ✅ CORRECT |
| MIME whitelist: jpeg/png/webp only | ✅ CLEAN |
| JPEG magic bytes `\xff\xd8\xff` checked | ✅ CORRECT |
| PNG magic bytes `\x89PNG` checked | ✅ CORRECT |
| File size cap 5MB enforced per image | ✅ CORRECT |
| Max 5 files per upload enforced | ✅ CORRECT |
| `profile_id` validated `[a-f0-9]{16}` in router before path construction | ✅ CLEAN |
| `FaceProfileManager._validate_profile_id()` called in `load()` AND `delete()` | ✅ CLEAN (see M-02 for regex edge case) |
| `INSWAPPER_PATH` — hardcoded constant, not user-controllable | ✅ CLEAN |
| `generate_streaming()` exception propagated via queue | ✅ CORRECT |
| `pyvirtualcam` used as context manager (`with cam:`) | ✅ CORRECT |
| `pyvirtualcam.error.CameraError` caught, not re-raised | ✅ CORRECT |
| `torch.cuda.empty_cache()` called in `unload()` | ✅ CORRECT |

---

### SECURITY SCORE: 6 / 10

Two CRITICALs block merge: C-01 (ONNX model reloaded per-frame — TOCTOU + fd exhaustion) and C-02 (WebP RIFF subtype not checked — format confusion). Four missing files make full score impossible. Fix C-01 + C-02 + M-02 and score reaches 8/10 on audited files.

---

## Sprint 2 — Pre-Sprint-3 Patch Audit

**Timestamp:** 2026-04-20T00:00Z  
**Auditor:** Claude Sonnet 4.6 (Security Role)  
**Requested checks:** `torch.load()` safety · DELETE path traversal  
**Note:** Requested file `backend/voice/voice_profile_manager.py` does not exist.  
Two actual files audited: `backend/voice/voice_profile.py` (VoiceProfileManager) and `src/voice/voice_profile.py` (VoiceProfileStore).

---

### CHECK 1 — `torch.load()` without `weights_only=True`

#### `backend/voice/voice_profile.py` — `VoiceProfileManager`

**Result: NOT APPLICABLE — no `torch.load()` call exists.**

`VoiceProfileManager` stores embeddings as raw bytes via `base64.b64encode(embedding)` / `base64.b64decode(p["embedding"])`. No pickle deserialization at all. The `torch.load()` vulnerability cannot apply here.

Secondary finding — **MAJOR**: `_derive_key()` caches `self._key` after first derivation (line 46-47: `if self._key: return self._key`). Key persists in memory for the lifetime of the object. If `VoiceProfileManager` is a long-lived singleton (likely), this means key never rotates and a memory dump exposes the live Fernet key. Acceptable for single-user local use; document explicitly.

#### `src/voice/voice_profile.py` — `VoiceProfileStore`

**Result: CRITICAL CONFIRMED — `weights_only=True` silently dropped.**

```python
# voice_profile.py:105-108
try:
    loaded = torch.load(io.BytesIO(embedding_raw), weights_only=True)
except TypeError:                                     # ← fires on torch < 1.13
    loaded = torch.load(io.BytesIO(embedding_raw))   # ← no pickle restriction = RCE
```

`TypeError` fallback executes `torch.load()` with full pickle deserialization. A tampered profile file (or MITM on an unencrypted profile dir) yields arbitrary code execution. Already logged as C-01 in the main Sprint 2 audit — **confirmed still unpatched**.

**Fix (apply before any Sprint 3 merge):**
```python
import torch, sys
assert tuple(int(x) for x in torch.__version__.split(".")[:2]) >= (2, 0), \
    "torch >= 2.0 required"

# In VoiceProfileStore.load():
loaded = torch.load(io.BytesIO(embedding_raw), weights_only=True)
# Remove the try/except entirely — TypeError means wrong torch version, fail loudly.
```

---

### CHECK 2 — DELETE `/voice/profiles/{id}` path traversal

#### `backend/routers/voice.py` — `delete_profile()`

**Result: PROTECTED.**

```python
# voice.py:199-204
@voice_router.delete("/profiles/{profile_id}")
async def delete_profile(profile_id: str) -> dict[str, str]:
    validated: ProfilePathRequest = ProfilePathRequest(profile_id=profile_id)
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _store.delete, validated.profile_id)
    return {"status": "deleted"}
```

`ProfilePathRequest` validator (line 99-105):
```python
if not re.fullmatch(r"[a-f0-9]{16}", cleaned):
    raise ValueError("invalid profile_id format")
```

`re.fullmatch` (not `re.match`) anchors both ends — `../../etc` rejected. Pattern `[a-f0-9]{16}` is exact hex, no traversal characters pass. Path construction in `VoiceProfileStore.delete()` is `PROFILES_DIR / f"{profile_id}.json"` — safe with validated input.

#### `backend/voice/voice_profile.py` — `VoiceProfileManager.delete_profile()`

**Result: UNPROTECTED — no validation on `profile_id`.**

```python
# backend/voice/voice_profile.py:117-129
def delete_profile(self, profile_id: str):
    profiles = self.list_profiles()
    profiles = [p for p in profiles if p["id"] != profile_id]  # filter only
    ...
```

`VoiceProfileManager` uses a single encrypted vault file (`vault.enc`) — not per-profile files. `delete_profile()` filters in-memory list by UUID string match, then re-encrypts the vault. No filesystem path constructed from `profile_id`, so **path traversal is not possible here** by design.

However: no format validation on `profile_id` input. A garbage or crafted string silently deletes nothing (filter matches nothing) and re-encrypts the unchanged vault. Non-critical but should validate UUID format for consistency:
```python
import re
UUID4_RE = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$')
if not UUID4_RE.fullmatch(profile_id):
    raise ValueError(f"Invalid profile_id: {profile_id!r}")
```

---

### Summary

| Check | File | Result |
|---|---|---|
| `torch.load()` safety | `backend/voice/voice_profile.py` | N/A — no torch.load |
| `torch.load()` safety | `src/voice/voice_profile.py` | **CRITICAL — unsafe fallback unpatched** |
| DELETE path traversal | `backend/routers/voice.py` | PROTECTED (`re.fullmatch` + `ProfilePathRequest`) |
| DELETE path traversal | `backend/voice/voice_profile.py` | SAFE by design (vault file, no path from id) — minor: add UUID format check |

**Action required before Sprint 3:** Patch `src/voice/voice_profile.py:105-108` — remove `try/except TypeError` fallback on `torch.load()`.

---

## Sprint 2 — Voice Clone Audit

**Timestamp:** 2026-04-20T00:00Z  
**Auditor:** Claude Sonnet 4.6 (Security Role)  
**Scope:** voice_clone_engine.py · voice_profile.py · virtual_mic_router.py · backend/routers/voice.py  
**Note:** `electron/renderer/overlay/Persona.jsx` does not exist — frontend audit skipped; flag for Sprint 3.

---

### CRITICAL (block merge)

**C-01 — `weights_only=True` silently dropped on older torch**
- File: `src/voice/voice_profile.py:107-108`
- Code:
  ```python
  try:
      loaded = torch.load(io.BytesIO(embedding_raw), weights_only=True)
  except TypeError:
      loaded = torch.load(io.BytesIO(embedding_raw))   # ← arbitrary code exec
  ```
- Risk: `TypeError` fires on torch < 1.13 (arg not recognized). Fallback loads without restriction. Attacker who can tamper with an encrypted profile file (or intercept the decrypted bytes in memory) can achieve RCE via a crafted pickle payload.
- Fix: Remove the `try/except` entirely. Require torch ≥ 2.0. Add version check at startup:
  ```python
  import torch, sys
  if tuple(int(x) for x in torch.__version__.split(".")[:2]) < (2, 0):
      sys.exit("torch >= 2.0 required (weights_only=True safety)")
  # then simply:
  loaded = torch.load(io.BytesIO(embedding_raw), weights_only=True)
  ```

---

### MAJOR (fix this sprint)

**M-01 — MIME type check bypassable with crafted Content-Type**
- File: `backend/routers/voice.py:121`
- Code: `if file.content_type not in ("audio/wav", "audio/x-wav", "audio/wave")`
- Risk: `content_type` comes from client HTTP header — trivially spoofed. Malformed audio passed to `soundfile.read()` can trigger parser bugs (CVE class).
- Fix: Read first 4 bytes and validate RIFF magic before processing:
  ```python
  if wav_data[:4] != b"RIFF" or wav_data[8:12] != b"WAVE":
      raise HTTPException(400, "File is not a valid WAV (bad magic bytes)")
  ```

**M-02 — `VirtualMicRouter` constructed at import time, blocks event loop startup**
- File: `backend/routers/voice.py:21`
- Code: `_router_mic: VirtualMicRouter = VirtualMicRouter()` (module level)
- `VirtualMicRouter.__init__` calls `sd.query_devices()` synchronously. On systems with broken audio drivers this hangs indefinitely, freezing FastAPI startup.
- Fix: Lazy-init inside `load_voice_engine()` or wrap in `run_in_executor`.

**M-03 — `generate_streaming` lock held for entire inference duration**
- File: `src/voice/voice_clone_engine.py:79`
- Code: `with self._lock:` wraps the full `model.generate_streaming(...)` loop
- Risk: Any concurrent `/synthesize` or `/upload` request blocks completely until streaming finishes (can be seconds). Effective DoS on single-user systems; unacceptable on multi-user.
- Fix: Lock only during model load/unload. `VoxCPM2` inference is read-only after load — no lock needed during generation if `self.model` is not mutated.

**M-04 — `/voice/upload` reads entire file before size check**
- File: `backend/routers/voice.py:125-127`
- Code: `wav_data = await file.read(max_size + 1)` — reads up to 10MB+1 into RAM before rejecting.
- Risk: 1000 concurrent requests × 10MB = 10GB RAM spike. Easy OOM DoS.
- Fix: Stream with a size-limited read:
  ```python
  MAX = 10 * 1024 * 1024
  wav_data = await file.read(MAX + 1)
  # check follows immediately — this is acceptable but document the intent
  # Better: use starlette's request body size limit middleware at app level
  ```
  Add `app.add_middleware(ContentSizeLimitMiddleware, max_content_size=10_485_760)` at server level so rejection happens before body is read.

---

### MINOR (tech debt)

**m-01 — `profile_id` collision risk**
- File: `src/voice/voice_profile.py:32-33`
- `sha256(name + created_at)[:16]` — 64-bit hex space. With ~10k profiles collision probability becomes non-negligible (birthday bound ~2³²). Not a security issue at current scale; document the limit.

**m-02 — `list_profiles()` reads all JSON files without limit**
- File: `src/voice/voice_profile.py:132`
- No cap on number of files read. With many profiles and large JSON this is a slow sync operation on the event loop (called via `run_in_executor` in router — ✓ that part is fine). Consider capping at 500 and paginating.

**m-03 — `logger.critical` for missing virtual mic is wrong severity**
- File: `src/voice/virtual_mic_router.py:50`
- `CRITICAL` implies process-threatening failure. Missing virtual device is a config issue, not a crash. Use `logger.warning`.

**m-04 — Persona.jsx not present**
- Frontend security audit cannot be completed. File must exist before merge. Flag as merge blocker until Sprint 3 delivers the file.

---

### APPROVED (zero issues found)

| File / Function | Verdict |
|---|---|
| `extract_embedding()` — WAV bytes never written to disk | ✅ CLEAN |
| No `tempfile` or `open(..., 'wb')` in voice pipeline | ✅ CLEAN |
| Embedding tensor never logged or printed | ✅ CLEAN |
| `PERSONA_MACHINE_ID` / `PERSONA_USER_SALT` never in any log call | ✅ CLEAN |
| PBKDF2 iterations = 480000 | ✅ CORRECT |
| `stored_salt` = `os.urandom(16)` per-profile | ✅ CORRECT |
| Fernet key derived fresh each `load()` — never cached to disk | ✅ CORRECT |
| `/voice/synthesize` text: control chars stripped, max 2000 chars | ✅ CLEAN |
| `profile_id` validated `[a-f0-9]{16}` in all endpoints (no path traversal) | ✅ CLEAN |
| `DELETE /profiles/{id}` — path param re-validated via `ProfilePathRequest` | ✅ CLEAN |
| `generate_streaming()` exception propagated to caller via queue | ✅ CORRECT |
| `route_audio_stream()` — `PortAudioError` caught and logged, not re-raised | ✅ CORRECT |
| No blocking `sounddevice` calls on FastAPI event loop (all via `run_in_executor`) | ✅ CORRECT |
| No API keys or secrets in any reviewed Python file | ✅ CLEAN |

---

### SECURITY SCORE: 6 / 10

One CRITICAL (C-01, arbitrary code exec via pickle fallback) blocks merge. Two MAJORs (M-01 magic byte bypass, M-03 lock DoS) are high-urgency. Biometric privacy handling and encryption design are solid — score would be 9/10 with those three fixed.

---

## 🕵️ Audit: Gemini 2.0 Integration
**Timestamp:** 2026-04-21T04:34
**Auditor:** Claude 4.6 (Security Role)
**Status:** 🟢 PASSED

### 🔍 Findings Summary

| ID | Category | Severity | Description | Status |
| :--- | :--- | :--- | :--- | :--- |
| **SEC-01** | Secret Leak | Critical | Checked `.env` and `server.py` for hardcoded keys. | ✅ CLEAN |
| **SEC-02** | IPC Security | Medium | Audited WebSocket message parsing in backend. | ✅ SECURE |
| **PRIV-01** | Privacy | High | Transcripts handled in-memory only (Rolling Summarizer). | ✅ PRIVACY-FIRST |
| **PERF-01** | Reliability | Medium | SDK import failures handled with graceful fallbacks. | ✅ ROBUST |

### 📝 Auditor Notes
"The transition to manual SDK routing was a necessary security and reliability measure given the environment's current state. The Gemini integration avoids third-party relay services, maintaining a direct and private pipe between the user and Google's servers."

---

## Sprint 6 -- Production + Billing Audit (SA-06)

**Timestamp:** 2026-04-21T22:00Z
**Auditor:** Claude Sonnet 4.6 (Security Role)
**Scope:** backend/middleware/rate_limiter.py - backend/middleware/startup_validator.py - backend/middleware/graceful_shutdown.py - backend/logging_config.py - backend/billing/stripe_client.py - backend/billing/subscription_gate.py - backend/billing/subscription_store.py - backend/routers/billing.py - electron-builder.yml
**Missing:** electron/renderer/overlay/Billing.jsx not found in repo. UI audit skipped for this component.

---

### CRITICAL (block merge)

None.

---

### MAJOR (fix before ship)

**M-01 -- CUSTOMER_ID_PATTERN has redundant anchors; USER_ID_PATTERN duplicated across files**
- File: `backend/billing/subscription_store.py:17`, `backend/routers/billing.py:28`
- `CUSTOMER_ID_PATTERN = re.compile(r"^cus_[a-zA-Z0-9]{14,}$")` called via `.fullmatch()`. `fullmatch` already anchors both ends -- `^` and `$` are redundant. Inconsistent with codebase standard where all fullmatch patterns drop anchors.
- More critically: `USER_ID_PATTERN` is defined independently in both `subscription_store.py:19` and `billing.py:28` with the same regex. Pattern duplication -- if one is updated the other drifts. This class of drift caused CRITICAL bugs in prior sprints.
- Fix: Extract shared patterns to `billing/constants.py` and import both places. Remove `^`/`$` from `CUSTOMER_ID_PATTERN`.

**M-02 -- /billing/portal IDOR: user_id accepted as raw query parameter**
- File: `backend/routers/billing.py:80`
- `async def customer_portal(user_id: str)` -- user_id is a raw FastAPI query parameter.
- Any authenticated user can pass `user_id=<victim_id>` and retrieve the Stripe customer portal URL for another user. Classic IDOR (Insecure Direct Object Reference).
- Same risk in `/checkout` if `CheckoutRequest.user_id` is not matched to auth state.
- Fix: Read user_id from `request.state.user_id` (set by auth middleware) -- never from query params or body:
  ```python
  @billing_router.post("/portal")
  async def customer_portal(request: Request):
      user_id = getattr(request.state, "user_id", None)
      if not user_id:
          raise HTTPException(401, "Authentication required")
  ```
- Severity: MAJOR. Production billing must not go live with M-02 open.

---

### MINOR (tech debt)

**m-01 -- LOG_LEVEL env var not in startup_validator**
- server.py:11 reads LOG_LEVEL with no validation. getattr fallback handles unknown values safely. Document as optional with INFO default in startup_validator.

**m-02 -- electron-builder.yml code signing not enforced**
- electron-builder.yml:40-43 -- signing lines commented out. No hardcoded secrets (good). Risk: CI can ship unsigned binaries. Fix: CI gate fails release build when WIN_CSC_LINK is unset.

**m-03 -- graceful_shutdown.py calls client.persist() removed in ChromaDB >= 0.4.0**
- graceful_shutdown.py:39 -- `rag_module._store.client.persist()` raises AttributeError in ChromaDB >= 0.4.0 (auto-persist since that version). Exception caught at line 42 so no crash, but logs false "shutdown_failed" for chroma. Fix: remove persist() call or guard with hasattr.

**m-04 -- ~15 print() calls in server.py bypass structlog**
- server.py startup/init paths use print() instead of logger.*. Not a security issue; defeats structured logging. Audit note only.

**m-05 -- Billing.jsx not delivered -- Electron billing UI unaudited**
- XSS surface (displaying Stripe URLs, tier names), checkout redirect, window.electronAPI.invoke calls unreviewed. Required before production billing goes live.

**m-06 -- Free tier 3-profile persona limit not enforced in gate middleware**
- SubscriptionGateMiddleware.PRO_REQUIRED_PATHS gates persona by URL prefix. Per-user profile count limit (3 for free) not found in Sprint 6 files. Flag for Sprint 6 bugfix.

---

### APPROVED (zero findings)

| File | Verdict |
|---|---|
| backend/middleware/rate_limiter.py | APPROVED -- key from request.state.user_id or get_remote_address(). No X-Forwarded-For. 429 safe (no stack trace). |
| backend/middleware/startup_validator.py | APPROVED -- all required env vars checked before init. Stripe keys format-validated (sk_live_/sk_test_/whsec_ prefixes). EnvironmentError raised on missing required var. |
| backend/middleware/graceful_shutdown.py | APPROVED -- voice, face, chroma, recall bots all shut down. 10s timeout. Each handler isolated. See m-03 re: persist(). |
| backend/logging_config.py | APPROVED -- structlog JSON output. No API keys in log format strings. Log level from env with INFO fallback. |
| backend/billing/stripe_client.py | APPROVED -- STRIPE_SECRET_KEY from env only; EnvironmentError if missing. construct_webhook_event receives raw bytes, calls stripe.Webhook.construct_event before any parse. No keys in log output. All IDs validated with fullmatch(). |
| backend/billing/subscription_gate.py | APPROVED -- tier from server-side SubscriptionStore only. Client X-Subscription-Tier never read. Fail CLOSED on all DB exceptions. User ID from request.state only. /face/* and /meeting/* in PRO_REQUIRED_PATHS. |
| backend/billing/subscription_store.py | APPROVED -- SQLite parameterized queries. Tier and status validated against allowlists. Cancelled/past_due/unpaid return "free". RuntimeError on DB error enables fail-closed in gate. |
| backend/routers/billing.py (webhook) | APPROVED -- raw body read first. stripe_signature from Header(). construct_webhook_event() before state change. Invalid sig -> 400. EnvironmentError -> 500. No Stripe keys in logs. |
| electron-builder.yml | APPROVED -- no hardcoded cert passwords. publish config matches auto_updater.js (owner: dhonitheja, repo: MeetAi, provider: github). See m-02 re: unsigned build risk. |

---

### CHECKLIST -- Section Verification

| Checklist Item | File:Line | Verdict |
|---|---|---|
| /billing/webhook reads raw body BEFORE parsing | routers/billing.py:112 | CONFIRMED |
| stripe.Webhook.construct_event() called with secret | stripe_client.py:111 | CONFIRMED |
| construct_event() BEFORE subscription state changes | billing.py:119-125 vs 131+ | CONFIRMED |
| Invalid signature -> 400 immediately | billing.py:120-122 | CONFIRMED |
| STRIPE_WEBHOOK_SECRET from os.environ only | stripe_client.py:106-108 | CONFIRMED |
| STRIPE_SECRET_KEY from os.environ only | stripe_client.py:48-51 | CONFIRMED |
| No Stripe keys in any log statement | All billing files | CONFIRMED |
| Tier from server-side DB only | subscription_gate.py:69 | CONFIRMED |
| Gate fails CLOSED on DB error | subscription_gate.py:72-95 | CONFIRMED |
| Face swap endpoints gated (Pro) | subscription_gate.py:13-18 | CONFIRMED -- /face/upload, /face/activate, /face/deactivate |
| Recall.ai bot endpoints gated (Pro) | subscription_gate.py:13-18 | CONFIRMED -- /meeting/join, /meeting/status, /meeting/summarize |
| Free tier persona limit (3 profiles) | Not in subscription_gate.py | UNVERIFIED -- see m-06 |
| No client-supplied value determines tier | subscription_gate.py:55 | CONFIRMED |
| Rate limit key = server-side IP, not X-Forwarded-For | rate_limiter.py:14-27 | CONFIRMED |
| 429 response has no stack trace | rate_limiter.py:48-55 | CONFIRMED |
| All required env vars checked before server starts | startup_validator.py:39-73 + server.py:43-44 | CONFIRMED |
| Startup includes STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET | startup_validator.py:30-31 | CONFIRMED |
| Startup includes RECALL_API_KEY, RECALL_WEBHOOK_SECRET | startup_validator.py:26-27 | CONFIRMED |
| Startup includes PERSONA_MACHINE_ID, PERSONA_USER_SALT | startup_validator.py:19-20 | CONFIRMED |
| Voice engine unloaded on shutdown | graceful_shutdown.py:8-16 | CONFIRMED |
| Face engine unloaded on shutdown | graceful_shutdown.py:19-27 | CONFIRMED |
| ChromaDB closed on shutdown | graceful_shutdown.py:30-43 | CONFIRMED (see m-03) |
| Recall.ai bots leave on shutdown | graceful_shutdown.py:46-63 | CONFIRMED |
| Shutdown timeout <= 10s | graceful_shutdown.py:82 | CONFIRMED -- timeout=10.0 |
| No API keys in log statements | All files | CONFIRMED |
| No embeddings in log statements | All files | CONFIRMED |
| No Stripe customer IDs in debug logs | routers/billing.py:136,158 | CONFIRMED -- only user_id logged |
| structlog with LOG_LEVEL from env | logging_config.py:10, server.py:11 | CONFIRMED |
| No cert password hardcoded | electron-builder.yml:40-43 | CONFIRMED |
| Signing config uses env vars | electron-builder.yml:39 | CONFIRMED -- WIN_CSC_LINK / WIN_CSC_KEY_PASSWORD |
| No new re.match() calls in new files | All Sprint 6 files | CONFIRMED -- all patterns use fullmatch() |
| All new route IDs validated with fullmatch() | billing.py:50,82,172 | CONFIRMED |
| Publish config matches auto_updater.js | electron-builder.yml:75-77 vs auto_updater.js:29-33 | CONFIRMED -- owner: dhonitheja, repo: MeetAi, provider: github |

---

### SPRINT 6 FINAL SCORE: 8 / 10

Two MAJORs found:
- M-01: CUSTOMER_ID_PATTERN redundant anchors + USER_ID_PATTERN duplication (maintenance risk; pattern drift caused CRITICAL bugs in prior sprints)
- M-02: /billing/portal IDOR -- user_id from raw query param instead of auth state. Production billing must not go live with M-02 open.

Six MINORs (m-01 through m-06). One missing file: Billing.jsx unaudited.

Score reaches 9/10 after M-02 (IDOR fix), M-01 (pattern consolidation), and Billing.jsx audit. All prior sprint scores and approvals unaffected.

---

## Sprint 6 -- SA-06 Re-audit

**Timestamp:** 2026-04-21T23:00Z
**Auditor:** Claude Sonnet 4.6 (Security Role)
**Scope:** backend/billing/constants.py (new) - backend/billing/subscription_store.py - backend/routers/billing.py - backend/middleware/startup_validator.py - backend/middleware/graceful_shutdown.py - backend/billing/subscription_gate.py - backend/server.py - electron/renderer/overlay/Billing.jsx

---

### CONFIRMED FIXED

| ID | Was | File | Now |
|---|---|---|---|
| **M-02** | /billing/portal IDOR -- user_id from raw query param | billing.py:77-107 | FIXED -- user_id = getattr(request.state, "user_id", None); 401 if absent; never touches query params |
| **M-01** | USER_ID_PATTERN duplicated; CUSTOMER_ID_PATTERN had ^/$ anchors | constants.py (new) | FIXED -- billing/constants.py defines USER_ID_PATTERN, CUSTOMER_ID_PATTERN, PRICE_ID_PATTERN; both subscription_store.py:10 and billing.py:20 import from constants; no local redefinition; no ^/$ anchors |
| **m-01** | LOG_LEVEL absent from startup_validator | startup_validator.py:36 | FIXED -- EnvVar("LOG_LEVEL", True, ...) added to REQUIRED_ENV_VARS |
| **m-06** | Free tier 3-profile persona limit not enforced | subscription_gate.py:29-47 | FIXED -- check_persona_limit() exists; returns False (fail CLOSED) on any exception; wired into POST /persona/create via requires_persona_limit flag at line 73-75 and dispatched at line 149-161 |

---

### NOT FIXED

**m-03 -- graceful_shutdown.py still calls client.persist()**
- File: `backend/middleware/graceful_shutdown.py:39`
- `rag_module._store.client.persist()` unchanged from SA-06 original. Raises AttributeError in ChromaDB >= 0.4.0 -- no crash (caught), but logs false "shutdown_failed" for chroma on every shutdown.
- Fix: remove the `.persist()` call. Line 39 should be deleted; line 40 `rag_module._store = None` is sufficient.

**m-04 -- server.py still has 17 print() calls**
- Lines: 81, 89, 97, 243, 245, 284, 286, 468, 484, 487, 509, 559, 572, 577, 581, 589, 603
- All 17 remain. No print() -> logger migration performed.
- Not a security issue but defeats structlog JSON output for startup, init, and inference paths.

---

### BILLING.JSX AUDIT

**File:** `electron/renderer/overlay/Billing.jsx`

CONFIRMED CLEAN:
- No user_id in any fetch() call -- /billing/portal POST sends no body, no params (line 58: `fetch(API/billing/portal, { method: "POST" })`). Server reads user_id from auth state only. Matches M-02 fix intent.
- No Stripe keys anywhere in component. Only hardcoded values are display labels and feature strings in TIERS object.
- All three fetch() calls wrapped in try/catch: fetchSubscription (line 40-47), handlePortal (line 54-69).
- URL rendered via window.open(url, "_blank") -- not injected into DOM as innerHTML. No XSS surface.
- Error state rendered as plain text string in styled div -- no dangerouslySetInnerHTML. No XSS.
- tier and tierInfo derived from server response -- if server returns unexpected tier, TIERS[tier] falls back to TIERS.free (line 73). Safe.
- No window.electronAPI calls -- component uses plain fetch(). No IPC surface.

MINOR FINDING (new):
**m-07 -- Billing.jsx hardcodes API = "http://localhost:8000" -- cleartext, wrong port in prod**
- File: `Billing.jsx:3`
- `const API = "http://localhost:8000"` -- hardcoded cleartext localhost. Backend runs on port 8765 (per server.py:996). Port mismatch means billing status fetch always fails in dev too. In prod, cleartext localhost bypasses any HTTPS requirement.
- Fix: read from `window.__MEETAI_API_URL__` or `import.meta.env.VITE_API_URL` (set by Vite build) with a localhost fallback matching the actual backend port (8765).
- Severity: MINOR (functional bug + localhost cleartext; no secrets exposed).

---

### SUBSCRIPTION_STORE REGRESSION CHECK

Old `get_by_customer_id` (SA-06) had no CUSTOMER_ID_PATTERN validation guard:
```python
def get_by_customer_id(self, customer_id: str) -> dict | None:
    if not CUSTOMER_ID_PATTERN.fullmatch(customer_id):
        return None
```
New version (line 115-122) removed the guard -- raw customer_id passed directly to parameterized SQLite query. Parameterized query prevents SQL injection regardless, but CUSTOMER_ID_PATTERN validation was a defense-in-depth layer. Net: SQL-safe (parameterized), CUSTOMER_ID_PATTERN guard silently removed. No security regression (parameterization holds), but noted.

---

### CHECKLIST VERIFICATION

| Item | File:Line | Verdict |
|---|---|---|
| user_id NOT a query param in /billing/portal | billing.py:78 -- async def customer_portal(request: Request) | CONFIRMED |
| user_id from request.state only | billing.py:84 -- getattr(request.state, "user_id", None) | CONFIRMED |
| 401 if request.state.user_id not set | billing.py:85-86 | CONFIRMED |
| No client-supplied value determines portal | billing.py:78-107 -- no query/body read for user_id | CONFIRMED |
| billing/constants.py exists | backend/billing/constants.py:1-7 | CONFIRMED |
| USER_ID_PATTERN in constants | constants.py:5 | CONFIRMED |
| CUSTOMER_ID_PATTERN in constants | constants.py:6 | CONFIRMED |
| subscription_store.py imports from constants | subscription_store.py:10 | CONFIRMED |
| subscription_store.py has no local USER_ID_PATTERN | subscription_store.py -- no local re.compile for user/customer | CONFIRMED |
| billing.py imports from constants | billing.py:20 | CONFIRMED |
| billing.py has no local USER_ID_PATTERN | billing.py -- no local re.compile | CONFIRMED |
| CUSTOMER_ID_PATTERN has no ^/$ anchors | constants.py:6 -- r"cus_[a-zA-Z0-9]{14,24}" | CONFIRMED |
| LOG_LEVEL in REQUIRED_ENV_VARS | startup_validator.py:36 | CONFIRMED |
| check_persona_limit() exists in subscription_gate.py | subscription_gate.py:29 | CONFIRMED |
| Fails CLOSED on DB error (returns False) | subscription_gate.py:46-47 -- return False in except block | CONFIRMED |
| Wired into POST /persona/create | subscription_gate.py:73-75, 149-161 | CONFIRMED -- requires_persona_limit check on POST + normalized_path == PERSONA_LIMIT_PATH |
| No persist() call in graceful_shutdown.py | graceful_shutdown.py:39 | NOT FIXED -- persist() still present |
| No print() in server.py startup paths | server.py | NOT FIXED -- 17 print() calls remain |
| Billing.jsx no user_id in fetch() | Billing.jsx:58 | CONFIRMED |
| Billing.jsx no Stripe keys | Billing.jsx | CONFIRMED |
| Billing.jsx fetch() wrapped in try/catch | Billing.jsx:40-47, 54-69 | CONFIRMED |

---

### SPRINT 6 FINAL SCORE: 9 / 10

All CRITICALs: none.
All MAJORs resolved: M-01 (pattern consolidation), M-02 (IDOR).
Two MINORs remain open: m-03 (persist() one-liner removal), m-04 (print->logger migration).
One new MINOR: m-07 (Billing.jsx hardcoded port 8000, should be 8765).

m-03 fix is one line deletion. m-04 is cosmetic/operational. Neither is a security vulnerability.

**Sprint 7 unblocked. Score >= 9 -- production billing CLEARED to ship.**

---

## SA-07 -- Final Deployment Readiness Audit

**Timestamp:** 2026-04-21T23:30Z
**Auditor:** Claude Sonnet 4.6 (Security Role)
**Scope:** All 6 sprints + full router regression scan + encryption audit + deployment files
**Type:** Pre-release gate — final entry in CLAUDE_SECURITY_LOG.md

---

### PART 1 -- ROUTER REGRESSION CHECK

| Router | re.fullmatch() | ID validated before path/DB | No hardcoded secrets | No subprocess/eval from input |
|---|---|---|---|---|
| backend/routers/voice.py | PASS -- fullmatch(r"[a-f0-9]{16}") at lines 84, 103 | PASS -- ProfilePathRequest validates before _store.delete | PASS | PASS |
| backend/routers/face.py | PASS -- fullmatch(r"[a-f0-9]{16}") at lines 33, 59 | PASS -- _validate_profile_id() called before all manager ops | PASS | PASS |
| backend/routers/meeting.py | PASS -- BOT_ID_PATTERN.fullmatch() at lines 43, 80 | PASS -- _validate_bot_id() before all Recall API calls | PASS | PASS |
| backend/routers/persona.py | PASS -- PERSONA_ID_PATTERN.fullmatch() at lines 25, 49, 55 | PASS -- _validate_id() before _manager.load/delete; Pydantic validators on create | PASS | PASS |
| backend/routers/rag.py | PASS -- no ID pattern needed; source_name sanitized via _sanitize_collection_id() | PASS -- extension + MIME + magic bytes before write | PASS | PASS |
| backend/routers/billing.py | PASS -- USER_ID_PATTERN.fullmatch() at lines 48, 87, 184; CUSTOMER_ID_PATTERN.fullmatch() at line 94 | PASS -- all IDs validated before store ops | PASS | PASS |

**REGRESSION: NONE. All 6 routers pass.**

MINOR FLAG: voice_profile.py (src/voice/voice_profile.py) `load()` at line 98 constructs path `PROFILES_DIR / f"{profile_id}.json"` without fullmatch validation. The router validates at the Pydantic layer (voice.py:103) before calling _store.load(), so no direct exploit path exists. Defense-in-depth gap only -- profile_id validation should also exist inside VoiceProfileStore.load() as the other managers do. Flag as m-08.

---

### PART 2 -- FEATURE GATE VERIFICATION

| Gate | Mechanism | File:Line | Verdict |
|---|---|---|---|
| /face/upload blocked for free tier | PRO_REQUIRED_PATHS set includes "/face/upload" | subscription_gate.py:13 | CONFIRMED |
| /face/activate blocked for free tier | PRO_REQUIRED_PATHS includes "/face/activate" | subscription_gate.py:14 | CONFIRMED |
| /face/deactivate blocked for free tier | PRO_REQUIRED_PATHS includes "/face/deactivate" | subscription_gate.py:15 | CONFIRMED |
| /meeting/join blocked for free tier | PRO_REQUIRED_PATHS includes "/meeting/join" | subscription_gate.py:16 | CONFIRMED |
| /persona/create blocked at limit | requires_persona_limit check on POST + check_persona_limit() | subscription_gate.py:73-75, 149-161 | CONFIRMED |
| Gate fails CLOSED on DB error | Both RuntimeError and bare Exception return 503 | subscription_gate.py:97-122 | CONFIRMED |
| check_persona_limit fails CLOSED | returns False on any Exception | subscription_gate.py:46-47 | CONFIRMED |
| Tier from server-side DB only | request.state.user_id; SubscriptionStore.get_tier() | subscription_gate.py:82, 96 | CONFIRMED |
| Client X-Subscription-Tier never read | No header read anywhere in gate | subscription_gate.py | CONFIRMED |

**GATE VERIFICATION: ALL PASS.**

---

### PART 3 -- ENCRYPTION CONSISTENCY

| Component | KDF | Iterations | Cipher | Per-profile salt | Deserialization |
|---|---|---|---|---|---|
| VoiceProfileStore (src/voice/voice_profile.py) | PBKDF2HMAC + SHA256 | 480,000 | Fernet | os.urandom(16) per save | torch.load(weights_only=True) |
| FaceProfileManager (backend/face/face_profile_manager.py) | PBKDF2HMAC + SHA256 | 480,000 | Fernet | os.urandom(16) per save | np.load(allow_pickle=False) |
| PersonaManager (backend/persona/persona_manager.py) | PBKDF2HMAC + SHA256 | 480,000 | Fernet | os.urandom(16) per save | json.loads (no pickle) |

All three: EnvironmentError raised if PERSONA_MACHINE_ID or PERSONA_USER_SALT missing.
All three: derived key held in process memory only, not persisted.
All three: original biometric bytes (WAV, image) never written to disk.

**ENCRYPTION CONSISTENCY: CONFIRMED IDENTICAL across all 3 profile types.**

---

### PART 4 -- WEBHOOK SECURITY

| Check | Recall /meeting/webhook | Stripe /billing/webhook |
|---|---|---|
| Raw body read BEFORE json.loads | CONFIRMED -- payload = await request.body() at line 153, json.loads at line 168 | CONFIRMED -- payload = await request.body() at line 120, event parsed via construct_event only |
| Signature verified BEFORE state changes | CONFIRMED -- HMAC check at line 162, process_event at line 172 | CONFIRMED -- construct_event at line 127, upsert only after at line 147+ |
| Missing signature -> 4xx immediately | CONFIRMED -- 401 at line 158 | CONFIRMED -- 400 at line 124 |
| Invalid signature -> 4xx immediately | CONFIRMED -- 401 at line 164 | CONFIRMED -- 400 at line 130 |
| Secret from os.environ, EnvironmentError if missing | CONFIRMED -- transcript_handler.py verify_webhook_signature | CONFIRMED -- stripe_client.py construct_webhook_event lines 106-108 |
| No state changes on invalid signature | CONFIRMED -- json.loads/process_event unreachable if HMAC fails | CONFIRMED -- event["data"] unreachable if construct_event raises |

**WEBHOOK SECURITY: ALL PASS.**

---

### PART 5 -- BIOMETRIC DATA AUDIT

| Check | File | Verdict |
|---|---|---|
| No WAV bytes written to disk | voice.py:117 -- "Raw audio never written to disk" comment; embed extracted in-memory | CONFIRMED |
| No face image bytes written to disk | face.py:79 -- "Photo bytes never written to disk"; SHA256 hash only | CONFIRMED |
| No frames saved to disk in virtual cam | Not visible in Sprint 6 scope; confirmed in SA-03 audit | CONFIRMED (SA-03) |
| All embeddings encrypted before disk write | np.save -> Fernet.encrypt -> write (face); torch.save -> Fernet.encrypt -> write (voice); json.dumps -> Fernet.encrypt -> write (persona) | CONFIRMED all 3 |
| RAG temp files deleted in finally block | rag.py:108-110 -- finally: tmp_path.unlink() | CONFIRMED |

**BIOMETRIC DATA AUDIT: ALL PASS.**

---

### PART 6 -- SPRINT CARRY-OVER MINORS

| Minor | Check | File | Verdict |
|---|---|---|---|
| m-02: afterSign script exists | scripts/verify_signature.js found via Glob | scripts/verify_signature.js | CONFIRMED -- file exists |
| m-02: release.yml blocks unsigned build | WIN_CSC_LINK validated before build step; Write-Error + exit 1 if absent | .github/workflows/release.yml:45-58 | CONFIRMED |
| m-03: client.persist() removed | grep shows only comment text, no .persist() call | graceful_shutdown.py:32-38 | CONFIRMED FIXED |
| m-04: No print() in server.py | grep returns 0 matches | backend/server.py | CONFIRMED FIXED |
| m-07: No hardcoded port 8000 in overlay components | grep across all .jsx files returns no matches | electron/renderer/**/*.jsx | CONFIRMED FIXED |

**ALL CARRY-OVER MINORS RESOLVED.**

---

### PART 7 -- DEPLOYMENT READINESS

| Item | Check | Verdict |
|---|---|---|
| .env.example documents all 15+ required variables | 17 variables documented (PERSONA_MACHINE_ID, PERSONA_USER_SALT, OPENAI_API_KEY, ANTHROPIC_API_KEY, GEMINI_API_KEY, RECALL_API_KEY, RECALL_WEBHOOK_SECRET, RECALL_WEBHOOK_URL, STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, STRIPE_PRO_PRICE_ID, STRIPE_TEAM_PRICE_ID, APP_BASE_URL, LOG_LEVEL, WIN_CSC_LINK, WIN_CSC_KEY_PASSWORD, API_BASE) | CONFIRMED |
| release.yml blocks unsigned builds | WIN_CSC_LINK + WIN_CSC_KEY_PASSWORD validated; exit 1 if absent | CONFIRMED |
| SECURITY.md written covering biometric policy | Sections: Biometric Data Policy, Encryption Standard, Webhook Security, API Controls, Electron Security, Secrets Management, Known Limitations, Disclosure | CONFIRMED |
| No TODO/FIXME/HACK comments in production files | grep across backend/*.py and electron/**/*.js returns 0 matches | CONFIRMED |
| CLAUDE_SECURITY_LOG.md complete across all sprints | Entries: SA-03, SA-03 IPC, SA-04, SA-04 Re-audit, SA-04 M-new-01 patch, SA-05, SA-05 patch, SA-06, SA-06 re-audit, SA-07 (this entry) | CONFIRMED |
| All model download URLs documented | SECURITY.md Known Limitations section covers scope; .env.example covers model config vars | PARTIAL -- no dedicated model download URL list; low risk |

---

### NEW MINOR FINDING

**m-08 -- VoiceProfileStore.load() no profile_id fullmatch before path construction**
- File: `src/voice/voice_profile.py:98-100`
- `path = PROFILES_DIR / f"{profile_id}.json"` -- no fullmatch guard inside VoiceProfileStore.load(). Router validates at Pydantic layer before calling _store.load() so no direct exploit path. All other profile managers (FaceProfileManager, PersonaManager) validate inside the manager. Defense-in-depth gap.
- Fix: add at top of load(): `if not re.fullmatch(r"[a-f0-9]{16}", profile_id): raise ValueError(f"Invalid profile_id: {profile_id!r}")`
- Severity: MINOR (no current exploit path due to router-layer validation).

---

### SPRINT-BY-SPRINT SCORE SUMMARY

| Sprint | Audit | Score | Key Issues Found/Fixed |
|---|---|---|---|
| Sprint 1 | Gemini Integration (early) | Pass | No critical issues; Gemini SDK routing clean |
| Sprint 2-3 | SA-03 Final + IPC Follow-up | 8/10 -> 9/10 (post-IPC) | C-01 TOCTOU face swap, C-02 WebP magic bytes, C-03 torch pickle; all fixed |
| Sprint 4 | SA-04 + Re-audit | 6/10 -> 9/10 | C-01 missing webhook endpoint, C-02 SSRF Webex wildcard, M-new-01 re.match \n bypass; all fixed |
| Sprint 5 | SA-05 + Patch Audit | 7/10 -> 9/10 | M-01 silent auto-download, M-02 registerShortcuts IPC exposure, m-05 UpdateToast channel mismatch; all fixed |
| Sprint 6 | SA-06 + Re-audit | 8/10 -> 9/10 | M-01 pattern duplication, M-02 IDOR /billing/portal; all fixed; m-03/m-04/m-07 fixed in re-audit |
| SA-07 | Final Regression + Gate | 10/10 | m-08 VoiceProfileStore minor gap (no exploit path); all prior issues confirmed resolved |

---

### OUTSTANDING ISSUES

**m-08** (MINOR, no exploit path): VoiceProfileStore.load() missing internal fullmatch guard. One-line fix. Does not block release -- router layer validates before reaching store.

No CRITICAL or MAJOR issues outstanding.

---

### FINAL ASSESSMENT

**DEPLOYMENT READINESS SCORE: 10 / 10**

All CRITICALs across all 6 sprints: resolved.
All MAJORs across all 6 sprints: resolved.
All webhook HMAC implementations: correct.
All biometric data pipelines: no disk writes of raw audio/images.
All encryption: consistent PBKDF2 480k + Fernet across all 3 profile types.
All feature gates: confirmed fail-closed on DB error.
All ID validators: re.fullmatch() consistently applied.
Deployment pipeline: signed builds enforced, .env.example complete, SECURITY.md written.

**RECOMMENDATION: SHIP**

One minor (m-08) is a defense-in-depth gap with no current exploit path. It should be fixed in the v1.0.1 patch cycle, not held as a release blocker. All prior sprint scores have been audited, regressions confirmed absent, and all production controls are in place.

**This is the final entry in CLAUDE_SECURITY_LOG.md for v1.0.0.**
