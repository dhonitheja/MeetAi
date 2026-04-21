import { useState, useEffect } from "react";

export default function UpdateToast() {
  const [update, setUpdate] = useState(null);
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    if (!window.electronAPI) return undefined;

    window.electronAPI.on("update:status", (_, data) => {
      switch (data.type) {
        case "available":
          setUpdate({ version: data.version, downloading: false, downloaded: false });
          break;
        case "progress":
          setProgress(data.percent);
          setUpdate((prev) => (prev ? { ...prev, downloading: true } : prev));
          break;
        case "downloaded":
          setUpdate((prev) => (prev ? { ...prev, downloading: false, downloaded: true } : prev));
          break;
        case "error":
          setUpdate(null);
          break;
        case "not-available":
          setUpdate(null);
          break;
        default:
          break;
      }
    });

    return () => {
      window.electronAPI?.removeAllListeners?.("update:status");
    };
  }, []);

  if (!update) return null;

  return (
    <div
      style={{
        position: "fixed",
        bottom: 52,
        left: 14,
        right: 14,
        background: "rgba(13,17,23,0.95)",
        backdropFilter: "blur(12px)",
        border: "1px solid rgba(0,229,160,0.3)",
        borderRadius: 8,
        padding: "10px 14px",
        zIndex: 999,
      }}
    >
      <div
        style={{
          fontSize: 11,
          fontWeight: 700,
          color: "#00e5a0",
          marginBottom: 6,
          fontFamily: "Unbounded, sans-serif",
        }}
      >
        Update Available - v{update.version}
      </div>
      {update.downloading && (
        <div
          style={{
            height: 3,
            background: "rgba(255,255,255,0.1)",
            borderRadius: 2,
            marginBottom: 8,
          }}
        >
          <div
            style={{
              height: "100%",
              width: `${progress}%`,
              background: "#00e5a0",
              borderRadius: 2,
              transition: "width 0.3s",
            }}
          />
        </div>
      )}
      <div style={{ display: "flex", gap: 6 }}>
        {!update.downloading && !update.downloaded && (
          <button
            onClick={() => window.electronAPI?.invoke("download-update")}
            style={{
              fontSize: 10,
              padding: "4px 12px",
              background: "rgba(0,229,160,0.1)",
              color: "#00e5a0",
              border: "1px solid rgba(0,229,160,0.25)",
              borderRadius: 5,
              cursor: "pointer",
            }}
          >
            Download
          </button>
        )}
        {update.downloaded && (
          <button
            onClick={() => window.electronAPI?.send("install-now")}
            style={{
              fontSize: 10,
              padding: "4px 12px",
              background: "rgba(0,229,160,0.15)",
              color: "#00e5a0",
              border: "1px solid rgba(0,229,160,0.3)",
              borderRadius: 5,
              cursor: "pointer",
            }}
          >
            Install & Restart
          </button>
        )}
        <button
          onClick={() => setUpdate(null)}
          style={{
            fontSize: 10,
            padding: "4px 10px",
            background: "none",
            color: "#4a5568",
            border: "1px solid rgba(255,255,255,0.07)",
            borderRadius: 5,
            cursor: "pointer",
          }}
        >
          Later
        </button>
      </div>
    </div>
  );
}
