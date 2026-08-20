import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { CheckCircle2, XCircle, Loader2, ExternalLink, AlertTriangle } from "lucide-react";
import { api } from "@/lib/api";

const formatDate = (iso) => (iso ? new Date(iso).toLocaleString() : "—");

const STATUSES = [
  { value: "", label: "All" },
  { value: "open", label: "Open" },
  { value: "under_review", label: "Under Review" },
  { value: "resolved", label: "Resolved" },
  { value: "dismissed", label: "Dismissed" },
];

function DisputeRow({ dispute, onDecide, saving }) {
  const [notes, setNotes] = useState("");
  const [showResolve, setShowResolve] = useState(false);
  const [showDismiss, setShowDismiss] = useState(false);
  const canDecide = dispute.status === "open" || dispute.status === "under_review";

  return (
    <div className="glass rounded-xl border border-border/60 p-4 sm:p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="font-heading font-bold text-base">{dispute.target_label}</h3>
            <span
              className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded-full ${
                dispute.status === "resolved"
                  ? "bg-primary/20 text-primary"
                  : dispute.status === "dismissed"
                  ? "bg-destructive/20 text-destructive"
                  : "bg-muted text-muted-foreground"
              }`}
            >
              {dispute.status.replace("_", " ")}
            </span>
            {dispute.escalated_to_admin && (
              <span className="inline-flex items-center gap-1 text-[10px] font-bold uppercase px-2 py-0.5 rounded-full bg-destructive/10 text-destructive">
                <AlertTriangle className="w-3 h-3" /> Escalated
              </span>
            )}
          </div>
          <Link
            to={`/tournaments/${dispute.target_tournament_id}`}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 text-sm text-primary hover:underline mt-0.5"
          >
            View tournament <ExternalLink className="w-3 h-3" />
          </Link>
          <p className="text-sm text-muted-foreground mt-1">
            Filed by {dispute.filed_by_email} · {formatDate(dispute.created_at)}
          </p>
          <p className="text-sm mt-1">{dispute.description}</p>
          {dispute.evidence.length > 0 && (
            <div className="flex flex-wrap gap-2 mt-2">
              {dispute.evidence.map((e) => (
                <a
                  key={e.id}
                  href={e.file}
                  target="_blank"
                  rel="noreferrer"
                  className="text-xs text-primary hover:underline"
                >
                  Evidence #{e.id}
                </a>
              ))}
            </div>
          )}
          {!canDecide && (
            <p className="text-xs text-muted-foreground mt-2">
              {dispute.status === "resolved" ? "Resolved" : "Dismissed"} by {dispute.resolved_by_email || "—"}
              {dispute.resolution_notes ? ` — ${dispute.resolution_notes}` : ""}
            </p>
          )}
        </div>

        {canDecide && (
          <div className="flex flex-col items-end gap-2">
            <div className="flex gap-2">
              <button
                onClick={() => {
                  setShowResolve((v) => !v);
                  setShowDismiss(false);
                }}
                disabled={saving}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-heading font-semibold bg-primary text-primary-foreground disabled:opacity-50"
              >
                <CheckCircle2 className="w-4 h-4" /> Resolve
              </button>
              <button
                onClick={() => {
                  setShowDismiss((v) => !v);
                  setShowResolve(false);
                }}
                disabled={saving}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-heading font-semibold bg-destructive/10 text-destructive disabled:opacity-50"
              >
                <XCircle className="w-4 h-4" /> Dismiss
              </button>
            </div>
            {(showResolve || showDismiss) && (
              <div className="flex gap-2 w-full sm:w-72">
                <input
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  placeholder="Resolution notes (required)"
                  className="flex-1 px-3 py-1.5 rounded-lg bg-muted/40 border border-border text-sm outline-none focus:border-primary"
                />
                <button
                  onClick={() => onDecide(dispute, showResolve ? "resolved" : "dismissed", notes)}
                  disabled={saving || !notes.trim()}
                  className="px-3 py-1.5 rounded-lg text-sm font-heading font-semibold bg-primary text-primary-foreground disabled:opacity-50"
                >
                  Confirm
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default function AdminDisputes() {
  const [disputes, setDisputes] = useState([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [escalatedOnly, setEscalatedOnly] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [savingId, setSavingId] = useState(null);

  const load = () => {
    setLoading(true);
    const query = {};
    if (statusFilter) query.status = statusFilter;
    if (escalatedOnly) query.escalated = "true";
    api
      .get("/api/admin/disputes/", { query })
      .then(setDisputes)
      .catch((e) => setError(e.message || "Failed to load disputes."))
      .finally(() => setLoading(false));
  };

  useEffect(load, [statusFilter, escalatedOnly]);

  const decide = async (dispute, newStatus, resolutionNotes) => {
    setSavingId(dispute.id);
    setError("");
    try {
      const updated = await api.patch(`/api/disputes/${dispute.id}/status/`, {
        status: newStatus, resolution_notes: resolutionNotes,
      });
      setDisputes((list) => list.map((d) => (d.id === dispute.id ? updated : d)));
    } catch (e) {
      setError(e.message || "Could not decide this dispute.");
    } finally {
      setSavingId(null);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex gap-1 p-1 rounded-xl bg-muted/30 border border-border/60 w-fit">
          {STATUSES.map((s) => (
            <button
              key={s.value}
              onClick={() => setStatusFilter(s.value)}
              className={`px-3.5 py-1.5 rounded-lg text-sm font-heading font-semibold transition-colors ${
                statusFilter === s.value ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground"
              }`}
            >
              {s.label}
            </button>
          ))}
        </div>
        <label className="flex items-center gap-1.5 text-sm text-muted-foreground cursor-pointer">
          <input type="checkbox" checked={escalatedOnly} onChange={(e) => setEscalatedOnly(e.target.checked)} />
          Escalated only
        </label>
      </div>

      {error && (
        <div className="text-sm text-destructive bg-destructive/10 border border-destructive/30 rounded-lg px-3 py-2">
          {error}
        </div>
      )}

      {loading ? (
        <div className="flex justify-center py-16 text-muted-foreground">
          <Loader2 className="w-6 h-6 animate-spin" />
        </div>
      ) : disputes.length === 0 ? (
        <div className="text-center py-16 text-muted-foreground text-sm">No disputes found.</div>
      ) : (
        <div className="space-y-3">
          {disputes.map((d) => (
            <DisputeRow key={d.id} dispute={d} onDecide={decide} saving={savingId === d.id} />
          ))}
        </div>
      )}
    </div>
  );
}
