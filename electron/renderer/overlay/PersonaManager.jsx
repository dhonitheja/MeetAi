import { useState, useEffect, useCallback } from "react";

const API = window.ENV?.API_BASE ?? "http://localhost:8765";

/**
 * PersonaManager - identity switcher panel for the F9 overlay.
 * Lists saved personas, activates with one click.
 * Create view lets user combine existing voice + face profiles.
 * Glassmorphism card style matching Sprint 3/4 panel aesthetic.
 */
export default function PersonaManager({ onPersonaActivated }) {
  const [personas, setPersonas] = useState([]);
  const [voiceProfiles, setVoiceProfiles] = useState([]);
  const [faceProfiles, setFaceProfiles] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [view, setView] = useState("list"); // list | create
  const [status, setStatus] = useState("idle"); // idle|loading|error
  const [errorMsg, setErrorMsg] = useState("");

  // Create form state
  const [form, setForm] = useState({
    display_name: "",
    voice_id: "",
    face_id: "",
    system_prompt: "Be concise and accurate.",
  });

  const showError = useCallback((msg) => {
    setStatus("error");
    setErrorMsg(msg);
    setTimeout(() => {
      setStatus("idle");
      setErrorMsg("");
    }, 4000);
  }, []);

  const fetchAll = useCallback(async () => {
    try {
      const [pRes, vRes, fRes, aRes] = await Promise.all([
        fetch(`${API}/persona/list`),
        fetch(`${API}/voice/profiles`),
        fetch(`${API}/face/profiles`),
        fetch(`${API}/persona/active`),
      ]);
      if (pRes.ok) setPersonas(await pRes.json());
      if (vRes.ok) setVoiceProfiles(await vRes.json());
      if (fRes.ok) setFaceProfiles(await fRes.json());
      if (aRes.ok) {
        const active = await aRes.json();
        if (active.active) setActiveId(active.persona_id);
      }
    } catch (e) {
      console.warn("[PersonaManager] fetchAll failed:", e.message);
    }
  }, []);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  const handleActivate = useCallback(
    async (personaId) => {
      setStatus("loading");
      try {
        const res = await fetch(`${API}/persona/activate/${personaId}`, { method: "POST" });
        if (!res.ok) {
          const err = await res.json().catch(() => ({ detail: "Activation failed" }));
          showError(err.detail ?? "Activation failed");
          return;
        }
        const data = await res.json();
        setActiveId(personaId);
        setStatus("idle");
        onPersonaActivated?.(data);
      } catch {
        showError("Network error during activation");
      }
    },
    [showError, onPersonaActivated]
  );

  const handleCreate = useCallback(async () => {
    if (!form.display_name || !form.voice_id || !form.face_id) {
      showError("Name, voice, and face are required");
      return;
    }
    setStatus("loading");
    try {
      const res = await fetch(`${API}/persona/create`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Create failed" }));
        showError(err.detail ?? "Create failed");
        return;
      }
      await fetchAll();
      setView("list");
      setForm({
        display_name: "",
        voice_id: "",
        face_id: "",
        system_prompt: "Be concise and accurate.",
      });
      setStatus("idle");
    } catch {
      showError("Network error during creation");
    }
  }, [form, showError, fetchAll]);

  const handleDelete = useCallback(
    async (personaId) => {
      if (!confirm("Delete this persona?")) return;
      try {
        await fetch(`${API}/persona/delete/${personaId}`, { method: "DELETE" });
        setPersonas((prev) => prev.filter((p) => p.persona_id !== personaId));
        if (activeId === personaId) setActiveId(null);
      } catch {
        showError("Failed to delete");
      }
    },
    [activeId, showError]
  );

  const glass = {
    background: "rgba(13,17,23,0.85)",
    backdropFilter: "blur(12px)",
    border: "1px solid rgba(0,229,160,0.15)",
    borderRadius: 10,
    padding: "14px 16px",
    marginBottom: 8,
  };

  const inputStyle = {
    width: "100%",
    background: "#0c1018",
    color: "#dde3ee",
    border: "1px solid rgba(255,255,255,0.1)",
    borderRadius: 6,
    padding: "6px 10px",
    fontSize: 12,
    marginBottom: 8,
    fontFamily: "DM Mono, monospace",
  };

  return (
    <div style={{ padding: "12px 0" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", marginBottom: 12 }}>
        <span
          style={{
            fontSize: 12,
            fontWeight: 700,
            color: "#dde3ee",
            fontFamily: "Unbounded, sans-serif",
            flex: 1,
          }}
        >
          Personas
        </span>
        <button
          onClick={() => setView(view === "list" ? "create" : "list")}
          style={{
            fontSize: 10,
            padding: "3px 10px",
            background: "rgba(79,142,247,0.1)",
            color: "#7aa8f8",
            border: "1px solid rgba(79,142,247,0.2)",
            borderRadius: 5,
            cursor: "pointer",
          }}
        >
          {view === "list" ? "+ New" : "<- Back"}
        </button>
      </div>

      {/* Error */}
      {errorMsg && (
        <div
          style={{
            fontSize: 10,
            color: "#ef4444",
            padding: "6px 8px",
            background: "rgba(239,68,68,0.08)",
            borderRadius: 4,
            marginBottom: 8,
          }}
        >
          {errorMsg}
        </div>
      )}

      {/* LIST VIEW */}
      {view === "list" && (
        <>
          {personas.length === 0 && (
            <div style={{ fontSize: 11, color: "#4a5568", textAlign: "center", padding: "16px 0" }}>
              No personas yet - create one to get started
            </div>
          )}
          {personas.map((p) => (
            <div
              key={p.persona_id}
              style={{
                ...glass,
                border:
                  activeId === p.persona_id
                    ? "1px solid rgba(0,229,160,0.4)"
                    : "1px solid rgba(255,255,255,0.07)",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <div
                  style={{
                    width: 32,
                    height: 32,
                    borderRadius: 8,
                    background: `hsl(${parseInt(p.persona_id.slice(0, 4), 16) % 360},40%,30%)`,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontSize: 14,
                    flexShrink: 0,
                  }}
                >
                  {p.display_name[0]?.toUpperCase()}
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 12, fontWeight: 700, color: "#dde3ee" }}>{p.display_name}</div>
                  {activeId === p.persona_id && (
                    <div style={{ fontSize: 10, color: "#00e5a0" }}>Active</div>
                  )}
                </div>
                <button
                  onClick={() => handleActivate(p.persona_id)}
                  disabled={activeId === p.persona_id || status === "loading"}
                  style={{
                    fontSize: 10,
                    padding: "3px 10px",
                    background:
                      activeId === p.persona_id ? "rgba(0,229,160,0.1)" : "rgba(255,255,255,0.05)",
                    color: activeId === p.persona_id ? "#00e5a0" : "#7a8599",
                    border: `1px solid ${
                      activeId === p.persona_id ? "rgba(0,229,160,0.2)" : "rgba(255,255,255,0.08)"
                    }`,
                    borderRadius: 5,
                    cursor: activeId === p.persona_id ? "default" : "pointer",
                  }}
                >
                  {activeId === p.persona_id ? "Active" : "Use"}
                </button>
                <button
                  onClick={() => handleDelete(p.persona_id)}
                  style={{
                    background: "none",
                    border: "none",
                    color: "#4a5568",
                    fontSize: 11,
                    cursor: "pointer",
                    padding: "2px 4px",
                  }}
                >
                  x
                </button>
              </div>
            </div>
          ))}
        </>
      )}

      {/* CREATE VIEW */}
      {view === "create" && (
        <div style={glass}>
          <div
            style={{
              fontSize: 11,
              fontWeight: 700,
              color: "#dde3ee",
              marginBottom: 12,
              fontFamily: "Unbounded, sans-serif",
            }}
          >
            Create Identity
          </div>
          <input
            placeholder="Display name"
            value={form.display_name}
            onChange={(e) => setForm((f) => ({ ...f, display_name: e.target.value }))}
            style={inputStyle}
          />
          <select
            value={form.voice_id}
            onChange={(e) => setForm((f) => ({ ...f, voice_id: e.target.value }))}
            style={inputStyle}
          >
            <option value="">- Select voice -</option>
            {voiceProfiles.map((v) => (
              <option key={v.profile_id} value={v.profile_id}>
                {v.name}
              </option>
            ))}
          </select>
          <select
            value={form.face_id}
            onChange={(e) => setForm((f) => ({ ...f, face_id: e.target.value }))}
            style={inputStyle}
          >
            <option value="">- Select face -</option>
            {faceProfiles.map((f) => (
              <option key={f.profile_id} value={f.profile_id}>
                {f.name}
              </option>
            ))}
          </select>
          <textarea
            placeholder="AI behavior prompt (optional)"
            value={form.system_prompt}
            onChange={(e) => setForm((f) => ({ ...f, system_prompt: e.target.value }))}
            rows={3}
            style={{ ...inputStyle, resize: "vertical", fontFamily: "DM Mono, monospace" }}
          />
          <button
            onClick={handleCreate}
            disabled={status === "loading" || !form.display_name || !form.voice_id || !form.face_id}
            style={{
              width: "100%",
              padding: "8px 0",
              fontSize: 12,
              fontWeight: 700,
              background: "rgba(0,229,160,0.1)",
              color: "#00e5a0",
              border: "1px solid rgba(0,229,160,0.25)",
              borderRadius: 6,
              cursor: "pointer",
              fontFamily: "Unbounded, sans-serif",
            }}
          >
            {status === "loading" ? "Creating..." : "Create Persona"}
          </button>
        </div>
      )}
    </div>
  );
}
