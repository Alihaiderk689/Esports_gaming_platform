import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { CheckCircle2, XCircle, Loader2, ExternalLink } from "lucide-react";
import { api } from "@/lib/api";

const formatDate = (iso) => (iso ? new Date(iso).toLocaleString() : "—");

const STATUSES = [
  { value: "", label: "All" },
  { value: "pending", label: "Pending" },
  { value: "approved", label: "Approved" },
  { value: "rejected", label: "Rejected" },
];

const REQUEST_TYPE_LABELS = {
  tournament_cancellation: "Tournament Cancellation",
};

export default function AdminReviewRequests() {
  const [requests, setRequests] = useState([]);
  const [status, setStatus] = useState("pending");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [savingId, setSavingId] = useState(null);
  const [rejectingId, setRejectingId] = useState(null);
  const [reason, setReason] = useState("");

  const load = (s) => {
    setLoading(true);
    api
      .get("/api/admin/review-requests/", { query: { status: s } })
      .then(setRequests)
      .catch((e) => setError(e.message || "Failed to load review requests."))
      .finally(() => setLoading(false));
  };

  useEffect(() => load(status), [status]);

  const decide = async (request, newStatus, decisionReason) => {
    setSavingId(request.id);
    setError("");
    try {
      const body = { status: newStatus };
      if (decisionReason !== undefined) body.reason = decisionReason;
      const updated = await api.post(`/api/admin/review-requests/${request.id}/decide/`, body);
      setRequests((list) => list.map((r) => (r.id === request.id ? updated : r)));
      setRejectingId(null);
      setReason("");
    } catch (e) {
      setError(e.message || "Could not decide this request.");
    } finally {
      setSavingId(null);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex gap-1 p-1 rounded-xl bg-muted/30 border border-border/60 w-fit">
        {STATUSES.map((s) => (
          <button
            key={s.value}
            onClick={() => setStatus(s.value)}
            className={`px-3.5 py-1.5 rounded-lg text-sm font-heading font-semibold transition-colors ${
              status === s.value ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground"
            }`}
          >
            {s.label}
          </button>
        ))}
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
      ) : requests.length === 0 ? (
        <div className="text-center py-16 text-muted-foreground text-sm">No review requests found.</div>
      ) : (
        <div className="space-y-3">
          {requests.map((r) => (
            <div key={r.id} className="glass rounded-xl border border-border/60 p-4 sm:p-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="flex items-center gap-2 flex-wrap">
                    <h3 className="font-heading font-bold text-base">
                      {REQUEST_TYPE_LABELS[r.request_type] || r.request_type}
                    </h3>
                    <span
                      className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded-full ${
                        r.status === "approved"
                          ? "bg-primary/20 text-primary"
                          : r.status === "rejected"
                          ? "bg-destructive/20 text-destructive"
                          : "bg-muted text-muted-foreground"
                      }`}
                    >
                      {r.status}
                    </span>
                  </div>
                  {r.target_tournament_name && (
                    <Link
                      to={`/tournaments/${r.object_id}`}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1 text-sm text-primary hover:underline mt-0.5"
                    >
                      {r.target_tournament_name} <ExternalLink className="w-3 h-3" />
                    </Link>
                  )}
                  <p className="text-sm text-muted-foreground mt-1">
                    Requested by {r.requested_by_email} · {formatDate(r.created_at)}
                  </p>
                  <p className="text-sm mt-1">{r.reason}</p>
                  {r.status !== "pending" && (
                    <p className="text-xs text-muted-foreground mt-2">
                      {r.status === "approved" ? "Approved" : "Rejected"} by {r.decided_by_email || "—"}
                      {r.decision_reason ? ` — ${r.decision_reason}` : ""}
                    </p>
                  )}
                </div>

                {r.status === "pending" && (
                  <div className="flex flex-col items-end gap-2">
                    <div className="flex gap-2">
                      <button
                        onClick={() => decide(r, "approved")}
                        disabled={savingId === r.id}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-heading font-semibold bg-primary text-primary-foreground disabled:opacity-50"
                      >
                        <CheckCircle2 className="w-4 h-4" /> Approve
                      </button>
                      <button
                        onClick={() => setRejectingId(rejectingId === r.id ? null : r.id)}
                        disabled={savingId === r.id}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-heading font-semibold bg-destructive/10 text-destructive disabled:opacity-50"
                      >
                        <XCircle className="w-4 h-4" /> Reject
                      </button>
                    </div>
                    {rejectingId === r.id && (
                      <div className="flex gap-2 w-full sm:w-72">
                        <input
                          value={reason}
                          onChange={(e) => setReason(e.target.value)}
                          placeholder="Reason for rejecting this request"
                          className="flex-1 px-3 py-1.5 rounded-lg bg-muted/40 border border-border text-sm outline-none focus:border-primary"
                        />
                        <button
                          onClick={() => decide(r, "rejected", reason)}
                          disabled={savingId === r.id}
                          className="px-3 py-1.5 rounded-lg text-sm font-heading font-semibold bg-destructive text-destructive-foreground disabled:opacity-50"
                        >
                          Confirm
                        </button>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
