import { useState, useEffect, useCallback, useRef } from "react";
import PersonaManager from "./PersonaManager";
import FaceClone from "./FaceClone";
import CoPilot from "./CoPilot";
import UpdateToast from "./UpdateToast";

const API = window.ENV?.API_BASE ?? "http://localhost:8765";

const TABS = [
  { id: "persona", label: "Persona", icon: "🎭" },
  { id: "face", label: "Face", icon: "👤" },
  { id: "copilot", label: "Co-Pilot", icon: "🤖" },
  { id: "meeting", label: "Meeting", icon: "📞" },
];

/**
 * OverlayShell - root container for the F9 stealth overlay.
 *
 * Features:
 * - Tabbed navigation across all 4 panels
 * - Global status bar: voice | face | bot | docs
 * - Smooth CSS opacity+transform transitions (no libraries)
 * - Keyboard shortcut hints in header
 */
export default function OverlayShell({ latestTranscript = "" }) {
  const [activeTab, setActiveTab] = useState("persona");
  const [prevTab, setPrevTab] = useState("persona");
  const [transitioning, setTrans] = useState(false);
  const transitionTimerRef = useRef(null);

  // Global status state
  const [status, setStatus] = useState({
    voice: "idle", // idle | active
    face: "idle", // idle | active
    bot: "offline", // offline | joining | connected
    docs: 0,
  });

  const switchTab = useCallback(
    (tabId) => {
      if (tabId === activeTab) return;

      if (transitionTimerRef.current) {
        clearTimeout(transitionTimerRef.current);
      }

      setTrans(true);
      setPrevTab(activeTab);

      transitionTimerRef.current = setTimeout(() => {
        setActiveTab(tabId);
        setTrans(false);
      }, 150);
    },
    [activeTab]
  );

  useEffect(() => {
    return () => {
      if (transitionTimerRef.current) {
        clearTimeout(transitionTimerRef.current);
      }
    };
  }, []);

  // Poll global status every 3s
  useEffect(() => {
    let mounted = true;

    const poll = async () => {
      try {
        const [vRes, fRes, mRes, dRes] = await Promise.all([
          fetch(`${API}/voice/profiles`).catch(() => null),
          fetch(`${API}/face/status`).catch(() => null),
          fetch(`${API}/meeting/active`).catch(() => null),
          fetch(`${API}/rag/files`).catch(() => null),
        ]);

        if (!mounted) return;

        setStatus((prev) => ({
          voice: prev.voice, // controlled by PersonaManager callback
          face: fRes?.ok ? "active" : "idle",
          bot: mRes?.ok ? "connected" : "offline",
          docs: dRes?.ok ? 0 : prev.docs, // updated separately
        }));

        if (dRes?.ok) {
          const files = await dRes.json().catch(() => []);
          if (!mounted) return;
          setStatus((prev) => ({ ...prev, docs: Array.isArray(files) ? files.length : 0 }));
        }

        if (fRes?.ok) {
          const fData = await fRes.json().catch(() => ({}));
          if (!mounted) return;
          setStatus((prev) => ({ ...prev, face: fData.active ? "active" : "idle" }));
        }

        if (mRes?.ok) {
          const mData = await mRes.json().catch(() => ({}));
          if (!mounted) return;
          const botCount = Object.keys(mData.bots || {}).length;
          setStatus((prev) => ({ ...prev, bot: botCount > 0 ? "connected" : "offline" }));
        }

        void vRes;
      } catch {
        // Ignore polling errors to keep overlay resilient.
      }
    };

    poll();
    const id = setInterval(poll, 3000);

    return () => {
      mounted = false;
      clearInterval(id);
    };
  }, []);

  const DOT = (on, label) => (
    <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
      <span
        style={{
          width: 6,
          height: 6,
          borderRadius: "50%",
          flexShrink: 0,
          background: on ? "#00e5a0" : "#374151",
          boxShadow: on ? "0 0 6px #00e5a0" : "none",
        }}
      />
      <span
        style={{
          fontSize: 9,
          color: on ? "#00e5a0" : "#374151",
          fontFamily: "DM Mono, monospace",
          textTransform: "uppercase",
          letterSpacing: "0.06em",
        }}
      >
        {label}
      </span>
    </div>
  );

  return (
    <div
      style={{
        width: 300,
        background: "rgba(6,8,15,0.96)",
        backdropFilter: "blur(20px)",
        border: "1px solid rgba(255,255,255,0.08)",
        borderRadius: 14,
        overflow: "hidden",
        fontFamily: "DM Mono, monospace",
        boxShadow: "0 24px 64px rgba(0,0,0,0.6)",
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          padding: "8px 12px",
          borderBottom: "1px solid rgba(255,255,255,0.07)",
          background: "rgba(0,0,0,0.36)",
        }}
      >
        <span
          style={{
            fontSize: 10,
            fontWeight: 700,
            color: "#cfd8e3",
            letterSpacing: "0.08em",
            textTransform: "uppercase",
            fontFamily: "Unbounded, sans-serif",
          }}
        >
          MeetAI Overlay
        </span>
        <span
          style={{
            fontSize: 9,
            color: "#4a5568",
            letterSpacing: "0.05em",
            textTransform: "uppercase",
          }}
        >
          F9 Toggle
        </span>
      </div>

      {/* Tab Navigation */}
      <div
        style={{
          display: "flex",
          borderBottom: "1px solid rgba(255,255,255,0.07)",
          background: "rgba(0,0,0,0.3)",
        }}
      >
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => switchTab(tab.id)}
            style={{
              flex: 1,
              padding: "10px 0",
              fontSize: 9,
              fontWeight: 600,
              background: "none",
              border: "none",
              color: activeTab === tab.id ? "#00e5a0" : "#4a5568",
              borderBottom: `2px solid ${activeTab === tab.id ? "#00e5a0" : "transparent"}`,
              cursor: "pointer",
              transition: "color 0.2s, border-color 0.2s",
              letterSpacing: "0.06em",
              textTransform: "uppercase",
            }}
          >
            <div style={{ fontSize: 14, marginBottom: 2 }}>{tab.icon}</div>
            {tab.label}
          </button>
        ))}
      </div>

      {/* Panel Content with transition */}
      <div
        data-prev-tab={prevTab}
        style={{
          padding: "4px 14px 14px",
          maxHeight: 460,
          overflowY: "auto",
          opacity: transitioning ? 0 : 1,
          transform: transitioning ? "translateY(4px)" : "translateY(0)",
          transition: "opacity 0.15s ease, transform 0.15s ease",
        }}
      >
        {activeTab === "persona" && (
          <PersonaManager
            onPersonaActivated={() =>
              setStatus((prev) => ({ ...prev, voice: "active", face: "active" }))
            }
          />
        )}
        {activeTab === "face" && <FaceClone />}
        {activeTab === "copilot" && <CoPilot latestTranscript={latestTranscript} />}
        {activeTab === "meeting" && (
          <div style={{ padding: "20px 0", textAlign: "center", fontSize: 11, color: "#4a5568" }}>
            Meeting panel - connect via /meeting/join
          </div>
        )}
      </div>

      {/* Global Status Bar */}
      <div
        style={{
          display: "flex",
          gap: 12,
          padding: "8px 14px",
          borderTop: "1px solid rgba(255,255,255,0.06)",
          background: "rgba(0,0,0,0.4)",
          justifyContent: "space-between",
        }}
      >
        {DOT(status.voice === "active", "Voice")}
        {DOT(status.face === "active", "Face")}
        {DOT(status.bot === "connected", "Bot")}
        {DOT(status.docs > 0, `${status.docs} Doc${status.docs !== 1 ? "s" : ""}`)}
      </div>
      <UpdateToast />
    </div>
  );
}
