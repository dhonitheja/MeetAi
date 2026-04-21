import { useState, useEffect, useCallback } from "react";

const API = window.ENV?.API_BASE ?? "http://localhost:8765";

const TIERS = {
  free: {
    label: "Free",
    color: "#6b7280",
    features: ["3 personas", "Voice clone", "Co-Pilot"],
  },
  pro: {
    label: "Pro",
    color: "#00e5a0",
    features: [
      "Unlimited personas",
      "Face swap",
      "Meeting bot",
      "Priority support",
    ],
  },
  team: {
    label: "Team",
    color: "#7aa8f8",
    features: [
      "5 seats",
      "All Pro features",
      "Team personas",
      "Admin dashboard",
    ],
  },
};

export default function Billing() {
  const [subscription, setSubscription] = useState(null);
  const [loading, setLoading] = useState(true);
  const [portalLoading, setPortalLoading] = useState(false);
  const [error, setError] = useState("");

  const fetchSubscription = useCallback(async () => {
    try {
      const res = await fetch(`${API}/billing/status`);
      if (res.ok) setSubscription(await res.json());
    } catch {
      setError("Could not load billing status");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSubscription();
  }, [fetchSubscription]);

  const handlePortal = useCallback(async () => {
    setPortalLoading(true);
    try {
      // No user_id in request - server reads from auth state
      const res = await fetch(`${API}/billing/portal`, { method: "POST" });
      if (!res.ok) {
        setError("Could not open billing portal");
        return;
      }
      const { url } = await res.json();
      if (url) window.open(url, "_blank");
    } catch {
      setError("Network error");
    } finally {
      setPortalLoading(false);
    }
  }, []);

  const tier = subscription?.tier ?? "free";
  const tierInfo = TIERS[tier] ?? TIERS.free;

  if (loading) {
    return (
      <div
        style={{
          padding: "20px 0",
          textAlign: "center",
          fontSize: 11,
          color: "#4a5568",
        }}
      >
        Loading billing status...
      </div>
    );
  }

  return (
    <div
      style={{ padding: "12px 0", borderTop: "1px solid rgba(255,255,255,0.08)" }}
    >
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
          Subscription
        </span>
        <span
          style={{
            fontSize: 10,
            padding: "2px 10px",
            borderRadius: 12,
            background: `rgba(${tier === "pro" ? "0,229,160" : tier === "team" ? "122,168,248" : "107,114,128"},0.1)`,
            color: tierInfo.color,
            border: `1px solid ${tierInfo.color}33`,
            fontFamily: "DM Mono, monospace",
          }}
        >
          {tierInfo.label}
        </span>
      </div>

      {/* Current plan features */}
      <div
        style={{
          background: "rgba(13,17,23,0.85)",
          backdropFilter: "blur(12px)",
          border: `1px solid ${tierInfo.color}22`,
          borderRadius: 10,
          padding: "12px 14px",
          marginBottom: 10,
        }}
      >
        <div
          style={{
            fontSize: 10,
            color: "#4a5568",
            marginBottom: 8,
            textTransform: "uppercase",
            letterSpacing: "0.08em",
          }}
        >
          Current Plan Features
        </div>
        {tierInfo.features.map((f) => (
          <div
            key={f}
            style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}
          >
            <span style={{ color: tierInfo.color, fontSize: 10 }}>{"\u2713"}</span>
            <span style={{ fontSize: 11, color: "#7a8599" }}>{f}</span>
          </div>
        ))}
      </div>

      {/* Status info */}
      {subscription?.current_period_end && (
        <div
          style={{
            fontSize: 10,
            color: "#4a5568",
            marginBottom: 10,
            fontFamily: "DM Mono, monospace",
          }}
        >
          Renews: {new Date(subscription.current_period_end * 1000).toLocaleDateString()}
        </div>
      )}

      {/* Manage / Upgrade button */}
      <button
        onClick={handlePortal}
        disabled={portalLoading}
        style={{
          width: "100%",
          padding: "8px 0",
          fontSize: 11,
          fontWeight: 600,
          background: tier === "free" ? "rgba(0,229,160,0.1)" : "rgba(255,255,255,0.05)",
          color: tier === "free" ? "#00e5a0" : "#7a8599",
          border: `1px solid ${tier === "free" ? "rgba(0,229,160,0.25)" : "rgba(255,255,255,0.08)"}`,
          borderRadius: 6,
          cursor: "pointer",
          fontFamily: "Unbounded, sans-serif",
        }}
      >
        {portalLoading
          ? "Opening..."
          : tier === "free"
            ? "Upgrade to Pro"
            : "Manage Subscription"}
      </button>

      {/* Error */}
      {error && (
        <div
          style={{
            fontSize: 10,
            color: "#ef4444",
            marginTop: 8,
            padding: "6px 8px",
            background: "rgba(239,68,68,0.08)",
            borderRadius: 4,
          }}
        >
          {error}
        </div>
      )}
    </div>
  );
}
