import { useEffect, useState, useCallback } from "react";

const API = window.ENV?.API_BASE ?? "http://localhost:8765";

/**
 * FaceClone - lightweight face status panel for overlay compatibility.
 */
export default function FaceClone() {
  const [active, setActive] = useState(false);
  const [profiles, setProfiles] = useState([]);
  const [error, setError] = useState("");

  const poll = useCallback(async () => {
    try {
      const [statusRes, profilesRes] = await Promise.all([
        fetch(`${API}/face/status`).catch(() => null),
        fetch(`${API}/face/profiles`).catch(() => null),
      ]);

      if (statusRes?.ok) {
        const data = await statusRes.json().catch(() => ({}));
        setActive(Boolean(data.active));
      }

      if (profilesRes?.ok) {
        const data = await profilesRes.json().catch(() => []);
        setProfiles(Array.isArray(data) ? data : []);
      }

      setError("");
    } catch {
      setError("Face service unavailable");
    }
  }, []);

  useEffect(() => {
    poll();
    const id = setInterval(poll, 3000);
    return () => clearInterval(id);
  }, [poll]);

  return (
    <div style={{ padding: "12px 0" }}>
      <div style={{ display: "flex", alignItems: "center", marginBottom: 10 }}>
        <span
          style={{
            fontSize: 12,
            fontWeight: 700,
            color: "#dde3ee",
            fontFamily: "Unbounded, sans-serif",
            flex: 1,
          }}
        >
          Face Clone
        </span>
        <span
          style={{
            fontSize: 10,
            color: active ? "#00e5a0" : "#4a5568",
            background: active ? "rgba(0,229,160,0.12)" : "rgba(255,255,255,0.06)",
            border: `1px solid ${active ? "rgba(0,229,160,0.25)" : "rgba(255,255,255,0.1)"}`,
            borderRadius: 5,
            padding: "2px 7px",
          }}
        >
          {active ? "Active" : "Idle"}
        </span>
      </div>

      <div
        style={{
          background: "rgba(13,17,23,0.85)",
          border: "1px solid rgba(255,255,255,0.08)",
          borderRadius: 10,
          padding: "12px",
          marginBottom: 8,
        }}
      >
        <div style={{ fontSize: 11, color: "#7a8599", marginBottom: 8 }}>
          {profiles.length} face profile{profiles.length !== 1 ? "s" : ""} available
        </div>
        {profiles.length === 0 && (
          <div style={{ fontSize: 10, color: "#4a5568" }}>
            Create a face profile first, then start swap from the API.
          </div>
        )}
      </div>

      {error && (
        <div
          style={{
            fontSize: 10,
            color: "#ef4444",
            background: "rgba(239,68,68,0.08)",
            borderRadius: 6,
            padding: "6px 8px",
          }}
        >
          {error}
        </div>
      )}
    </div>
  );
}
