import { useState, useEffect, useRef, useCallback } from "react";

const API = window.ENV?.API_BASE ?? "http://localhost:8765";
const POLL_INTERVAL = 3000;

/**
 * CoPilot - real-time doc-grounded suggestion panel for the F9 overlay.
 * Polls /rag/query with the latest transcript text to surface suggestions.
 * Shows source documents used to ground each suggestion.
 * Glassmorphism card style with high contrast for readability in meetings.
 */
export default function CoPilot({ latestTranscript = "" }) {
  const [suggestion, setSuggestion] = useState(null);
  const [sources, setSources] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState("");
  const [docsCount, setDocsCount] = useState(0);
  const pollRef = useRef(null);
  const lastQueryRef = useRef("");

  // Fetch indexed doc count on mount
  const fetchDocCount = useCallback(async () => {
    try {
      const res = await fetch(`${API}/rag/files`);
      if (res.ok) {
        const files = await res.json();
        setDocsCount(files.length);
      }
    } catch {}
  }, []);

  useEffect(() => {
    fetchDocCount();
    const docPoll = setInterval(fetchDocCount, POLL_INTERVAL);
    return () => {
      clearInterval(docPoll);
      clearTimeout(pollRef.current);
    };
  }, [fetchDocCount]);

  // Poll for suggestions when transcript changes
  useEffect(() => {
    if (!latestTranscript || latestTranscript === lastQueryRef.current) return;
    if (latestTranscript.length < 10) return;

    clearTimeout(pollRef.current);
    pollRef.current = setTimeout(async () => {
      lastQueryRef.current = latestTranscript;
      setIsLoading(true);
      setError("");

      try {
        const res = await fetch(
          `${API}/rag/query?text=${encodeURIComponent(latestTranscript.slice(0, 500))}&n_results=3`
        );
        if (!res.ok) {
          setError("Query failed");
          return;
        }
        const data = await res.json();
        const results = data.results || [];

        if (results.length === 0) {
          setSuggestion(null);
          setSources([]);
          return;
        }

        // Top result as suggestion
        setSuggestion(results[0].text);
        setSources(
          results.map((r) => ({
            source: r.source,
            excerpt: `${r.text.slice(0, 100)}...`,
            distance: r.distance,
          }))
        );
      } catch {
        setError("Network error - is the backend running?");
      } finally {
        setIsLoading(false);
      }
    }, 1200); // debounce
  }, [latestTranscript]);

  const handleCopy = useCallback(() => {
    if (!suggestion) return;
    navigator.clipboard.writeText(suggestion).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }, [suggestion]);

  const glass = {
    background: "rgba(13, 17, 23, 0.85)",
    backdropFilter: "blur(12px)",
    border: "1px solid rgba(0, 229, 160, 0.15)",
    borderRadius: 10,
    padding: "14px 16px",
    marginBottom: 10,
  };

  return (
    <div style={{ padding: "12px 0", borderTop: "1px solid rgba(255,255,255,0.08)" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
        <span
          style={{
            width: 8,
            height: 8,
            borderRadius: "50%",
            background: isLoading ? "#f59e0b" : suggestion ? "#00e5a0" : "#4a5568",
            animation: isLoading ? "cpPulse 1s infinite" : "none",
            flexShrink: 0,
          }}
        />
        <span
          style={{
            fontSize: 12,
            fontWeight: 700,
            color: "#dde3ee",
            fontFamily: "Unbounded, sans-serif",
          }}
        >
          Co-Pilot
        </span>
        <span style={{ fontSize: 10, color: "#4a5568", marginLeft: "auto" }}>
          {docsCount} doc{docsCount !== 1 ? "s" : ""} indexed
        </span>
      </div>

      {/* No docs warning */}
      {docsCount === 0 && (
        <div
          style={{
            fontSize: 10,
            color: "#f59e0b",
            marginBottom: 10,
            padding: "6px 10px",
            background: "rgba(245,158,11,0.08)",
            borderRadius: 6,
          }}
        >
          No documents indexed - upload files via Settings for grounded suggestions
        </div>
      )}

      {/* Suggestion card */}
      {suggestion && (
        <div style={glass}>
          <div
            style={{
              fontSize: 10,
              fontWeight: 700,
              color: "#00e5a0",
              letterSpacing: "0.1em",
              textTransform: "uppercase",
              marginBottom: 8,
            }}
          >
            Doc-Grounded Suggestion
          </div>
          <p style={{ fontSize: 12, color: "#dde3ee", lineHeight: 1.7, marginBottom: 10 }}>
            {suggestion}
          </p>
          <button
            onClick={handleCopy}
            style={{
              padding: "4px 12px",
              fontSize: 10,
              fontWeight: 600,
              background: copied ? "rgba(0,229,160,0.15)" : "rgba(255,255,255,0.05)",
              color: copied ? "#00e5a0" : "#7a8599",
              border: `1px solid ${
                copied ? "rgba(0,229,160,0.3)" : "rgba(255,255,255,0.1)"
              }`,
              borderRadius: 5,
              cursor: "pointer",
              transition: "all 0.2s",
            }}
          >
            {copied ? "Copied" : "Copy"}
          </button>
        </div>
      )}

      {/* Source files */}
      {sources.length > 0 && (
        <div style={{ marginBottom: 10 }}>
          <div
            style={{
              fontSize: 10,
              color: "#4a5568",
              marginBottom: 6,
              textTransform: "uppercase",
              letterSpacing: "0.08em",
            }}
          >
            Source Files
          </div>
          {sources.map((s, i) => (
            <div
              key={i}
              style={{
                padding: "6px 10px",
                marginBottom: 4,
                background: "rgba(255,255,255,0.03)",
                border: "1px solid rgba(255,255,255,0.07)",
                borderRadius: 6,
              }}
            >
              <div style={{ fontSize: 11, color: "#7aa8f8", fontWeight: 600, marginBottom: 2 }}>
                {s.source}
              </div>
              <div style={{ fontSize: 10, color: "#4a5568", lineHeight: 1.5 }}>{s.excerpt}</div>
            </div>
          ))}
        </div>
      )}

      {/* Loading state */}
      {isLoading && !suggestion && (
        <div style={{ fontSize: 11, color: "#4a5568", padding: "8px 0" }}>
          Searching documents...
        </div>
      )}

      {/* Empty state */}
      {!isLoading && !suggestion && !error && docsCount > 0 && (
        <div style={{ fontSize: 11, color: "#4a5568" }}>
          Listening for questions in the meeting...
        </div>
      )}

      {/* Error */}
      {error && (
        <div
          style={{
            fontSize: 10,
            color: "#ef4444",
            padding: "6px 8px",
            background: "rgba(239,68,68,0.08)",
            borderRadius: 4,
          }}
        >
          {error}
        </div>
      )}

      <style>{`@keyframes cpPulse { 0%,100%{opacity:1} 50%{opacity:0.3} }`}</style>
    </div>
  );
}
