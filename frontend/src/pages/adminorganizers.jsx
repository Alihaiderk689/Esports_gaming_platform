import React, { useEffect, useState } from "react";
import { CheckCircle2, XCircle, Loader2, ArrowLeft } from "lucide-react";
import { api } from "@/lib/api";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { DocBadge, DocPreviewDialog } from "@/components/admin/docpreview";

const formatDate = (iso) => (iso ? new Date(iso).toLocaleString() : "—");

const STATUSES = [
  { value: "", label: "All" },
  { value: "pending", label: "Pending" },
  { value: "approved", label: "Approved" },
  { value: "rejected", label: "Rejected" },
];

function InfoRow({ label, value }) {
  return (
    <div>
      <p className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="text-sm">{value || "—"}</p>
    </div>
  );
}

function OrganizerDetailDialog({ org, onClose, onPreview, onDecide, saving, rejecting, onToggleReject, reason, onReasonChange }) {
  return (
    <Dialog open={!!org} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>{org?.company_name}</DialogTitle>
        </DialogHeader>
        {org && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <InfoRow label="Status" value={org.status} />
              <InfoRow label="Email" value={org.user_email} />
              <InfoRow label="Phone" value={org.phone_number} />
              <InfoRow label="Address" value={org.address} />
              <InfoRow label="Company registration #" value={org.company_registration_number} />
              <InfoRow label="CNIC number" value={org.cnic_number} />
              <InfoRow label="Submitted" value={formatDate(org.created_at)} />
              <InfoRow label="Last updated" value={formatDate(org.updated_at)} />
            </div>

            <div className="pt-2 border-t border-border/60 grid grid-cols-2 gap-3">
              <InfoRow label="Payout method" value={org.payout_method === "bank" ? "Bank Account" : org.payout_method === "jazzcash" ? "JazzCash" : null} />
              {org.payout_method === "jazzcash" && <InfoRow label="JazzCash number" value={org.jazzcash_number} />}
              {org.payout_method === "bank" && (
                <>
                  <InfoRow label="Bank name" value={org.bank_name} />
                  <InfoRow label="Account title" value={org.bank_account_title} />
                  <InfoRow label="Account number" value={org.bank_account_number} />
                </>
              )}
            </div>

            <div className="flex gap-2">
              <DocBadge url={org.cnic_document} label="CNIC" onPreview={onPreview} />
              <DocBadge url={org.company_document} label="Company doc" onPreview={onPreview} />
            </div>

            {org.status === "rejected" && org.rejection_reason && (
              <p className="text-xs text-destructive">Reason: {org.rejection_reason}</p>
            )}

            <div className="flex items-center justify-between gap-2 pt-2 border-t border-border/60">
              <button
                onClick={onClose}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-heading font-semibold bg-muted hover:bg-muted/70 transition-colors"
              >
                <ArrowLeft className="w-4 h-4" /> Back
              </button>

              {org.status !== "approved" && (
                <div className="flex flex-col items-end gap-2">
                  <div className="flex gap-2">
                    <button
                      onClick={() => onDecide(org, "approved")}
                      disabled={saving}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-heading font-semibold bg-primary text-primary-foreground disabled:opacity-50"
                    >
                      <CheckCircle2 className="w-4 h-4" /> Approve
                    </button>
                    <button
                      onClick={() => onToggleReject(org.id)}
                      disabled={saving}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-heading font-semibold bg-destructive/10 text-destructive disabled:opacity-50"
                    >
                      <XCircle className="w-4 h-4" /> Reject
                    </button>
                  </div>
                  {rejecting && (
                    <div className="flex gap-2 w-72">
                      <input
                        value={reason}
                        onChange={(e) => onReasonChange(e.target.value)}
                        placeholder="Reason for rejection"
                        className="flex-1 px-3 py-1.5 rounded-lg bg-muted/40 border border-border text-sm outline-none focus:border-primary"
                      />
                      <button
                        onClick={() => onDecide(org, "rejected", reason)}
                        disabled={saving}
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
        )}
      </DialogContent>
    </Dialog>
  );
}

export default function AdminOrganizers() {
  const [organizers, setOrganizers] = useState([]);
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const [hasNext, setHasNext] = useState(false);
  const [hasPrevious, setHasPrevious] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [savingId, setSavingId] = useState(null);
  const [rejectingId, setRejectingId] = useState(null);
  const [reason, setReason] = useState("");
  const [previewDoc, setPreviewDoc] = useState(null);
  const [detailOrg, setDetailOrg] = useState(null);

  const load = (s, p) => {
    setLoading(true);
    api
      .get("/api/admin/organizers/", { query: { status: s, page: p } })
      .then((data) => {
        const results = Array.isArray(data) ? data : data.results;
        setOrganizers(results);
        setHasNext(Boolean(data && !Array.isArray(data) && data.next));
        setHasPrevious(Boolean(data && !Array.isArray(data) && data.previous));
      })
      .catch((e) => setError(e.message || "Failed to load organizers."))
      .finally(() => setLoading(false));
  };

  useEffect(() => load(status, page), [status, page]);

  const decide = async (org, newStatus, rejectionReason) => {
    setSavingId(org.id);
    setError("");
    try {
      const body = { status: newStatus };
      if (rejectionReason !== undefined) body.reason = rejectionReason;
      const updated = await api.patch(`/api/admin/organizers/${org.id}/`, body);
      setOrganizers((list) => list.map((o) => (o.id === org.id ? updated : o)));
      setDetailOrg((d) => (d && d.id === org.id ? updated : d));
      setRejectingId(null);
      setReason("");
    } catch (e) {
      setError(e.message || "Could not update organizer status.");
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
            onClick={() => { setStatus(s.value); setPage(1); }}
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
      ) : organizers.length === 0 ? (
        <div className="text-center py-16 text-muted-foreground text-sm">No organizers found.</div>
      ) : (
        <div className="space-y-3">
          {organizers.map((org) => (
            <div key={org.id} className="glass rounded-xl border border-border/60 p-4 sm:p-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div
                  onClick={() => setDetailOrg(org)}
                  className="cursor-pointer rounded-lg -m-1 p-1 transition-colors hover:bg-muted/30"
                >
                  <div className="flex items-center gap-2 flex-wrap">
                    <h3 className="font-heading font-bold text-base">{org.company_name}</h3>
                    <span
                      className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded-full ${
                        org.status === "approved"
                          ? "bg-primary/20 text-primary"
                          : org.status === "rejected"
                          ? "bg-destructive/20 text-destructive"
                          : "bg-muted text-muted-foreground"
                      }`}
                    >
                      {org.status}
                    </span>
                  </div>
                  <p className="text-sm text-muted-foreground mt-0.5">{org.user_email}</p>
                  <p className="text-sm text-muted-foreground">{org.phone_number || "No phone"} · {org.address || "No address"}</p>
                  <div className="flex gap-2 mt-2">
                    <DocBadge
                      url={org.cnic_document}
                      label="CNIC"
                      onPreview={(url, label) => setPreviewDoc({ url, label })}
                    />
                    <DocBadge
                      url={org.company_document}
                      label="Company doc"
                      onPreview={(url, label) => setPreviewDoc({ url, label })}
                    />
                  </div>
                  {org.status === "rejected" && org.rejection_reason && (
                    <p className="text-xs text-destructive mt-2">Reason: {org.rejection_reason}</p>
                  )}
                </div>

                {org.status !== "approved" && (
                  <div className="flex flex-col items-end gap-2">
                    <div className="flex gap-2">
                      <button
                        onClick={() => decide(org, "approved")}
                        disabled={savingId === org.id}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-heading font-semibold bg-primary text-primary-foreground disabled:opacity-50"
                      >
                        <CheckCircle2 className="w-4 h-4" /> Approve
                      </button>
                      <button
                        onClick={() => setRejectingId(rejectingId === org.id ? null : org.id)}
                        disabled={savingId === org.id}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-heading font-semibold bg-destructive/10 text-destructive disabled:opacity-50"
                      >
                        <XCircle className="w-4 h-4" /> Reject
                      </button>
                    </div>
                    {rejectingId === org.id && (
                      <div className="flex gap-2 w-full sm:w-72">
                        <input
                          value={reason}
                          onChange={(e) => setReason(e.target.value)}
                          placeholder="Reason for rejection"
                          className="flex-1 px-3 py-1.5 rounded-lg bg-muted/40 border border-border text-sm outline-none focus:border-primary"
                        />
                        <button
                          onClick={() => decide(org, "rejected", reason)}
                          disabled={savingId === org.id}
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

      {!loading && (hasNext || hasPrevious) && (
        <div className="flex items-center justify-center gap-3 pt-2">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={!hasPrevious}
            className="px-3 py-1.5 rounded-lg text-sm font-heading font-semibold bg-muted/40 border border-border/60 disabled:opacity-40"
          >
            Previous
          </button>
          <span className="text-sm text-muted-foreground">Page {page}</span>
          <button
            onClick={() => setPage((p) => p + 1)}
            disabled={!hasNext}
            className="px-3 py-1.5 rounded-lg text-sm font-heading font-semibold bg-muted/40 border border-border/60 disabled:opacity-40"
          >
            Next
          </button>
        </div>
      )}

      <OrganizerDetailDialog
        org={detailOrg}
        onClose={() => setDetailOrg(null)}
        onPreview={(url, label) => setPreviewDoc({ url, label })}
        onDecide={decide}
        saving={detailOrg ? savingId === detailOrg.id : false}
        rejecting={detailOrg ? rejectingId === detailOrg.id : false}
        onToggleReject={(id) => setRejectingId((cur) => (cur === id ? null : id))}
        reason={reason}
        onReasonChange={setReason}
      />
      <DocPreviewDialog doc={previewDoc} onClose={() => setPreviewDoc(null)} />
    </div>
  );
}
