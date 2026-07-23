import React, { useEffect, useState } from "react";
import { CheckCircle2, XCircle, Loader2, ArrowLeft } from "lucide-react";
import { api } from "@/lib/api";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { DocBadge, DocPreviewDialog } from "@/components/admin/docpreview";

const formatDate = (iso) => (iso ? new Date(iso).toLocaleString() : "—");
const formatMoney = (n) => `PKR ${Number(n || 0).toLocaleString()}`;

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

function TournamentDetailDialog({ tournament, onClose, onPreview, onDecide, saving, rejecting, onToggleReject, reason, onReasonChange }) {
  return (
    <Dialog open={!!tournament} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{tournament?.name}</DialogTitle>
        </DialogHeader>
        {tournament && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <InfoRow label="Status" value={tournament.status} />
              <InfoRow label="Game" value={tournament.game_name} />
              <InfoRow label="Organizer" value={tournament.organizer_name} />
              <InfoRow label="Created by" value={tournament.created_by_email} />
              <InfoRow label="Mode" value={tournament.mode} />
              <InfoRow label="Bracket format" value={tournament.bracket_format} />
              <InfoRow label="Team size" value={tournament.team_size} />
              <InfoRow label="Max players" value={tournament.max_participants} />
              <InfoRow label="Registration fee" value={formatMoney(tournament.registration_fee)} />
              <InfoRow label="Prize pool" value={formatMoney(tournament.prize_pool)} />
              <InfoRow label="Registration deadline" value={formatDate(tournament.registration_deadline)} />
              <InfoRow label="Starts" value={formatDate(tournament.starts_at)} />
              <InfoRow label="Ends" value={formatDate(tournament.ends_at)} />
              <InfoRow label="Submitted" value={formatDate(tournament.created_at)} />
            </div>

            {tournament.mode !== "online" && (
              <div className="pt-2 border-t border-border/60 grid grid-cols-2 gap-3">
                <InfoRow label="Venue" value={tournament.venue_name} />
                <InfoRow label="City" value={tournament.venue_city} />
                <InfoRow label="Address" value={tournament.venue_address} />
                <InfoRow label="Province" value={tournament.venue_province} />
                <InfoRow label="Country" value={tournament.venue_country} />
                <InfoRow label="Parking" value={tournament.venue_parking_available ? "Yes" : "No"} />
                <InfoRow label="Maps link" value={tournament.venue_map_link} />
              </div>
            )}

            {tournament.mode !== "offline" && (
              <div className="pt-2 border-t border-border/60 grid grid-cols-2 gap-3">
                <InfoRow label="Platform" value={tournament.platform} />
                <InfoRow label="Discord server" value={tournament.discord_server} />
                <InfoRow label="Room ID" value={tournament.room_id} />
              </div>
            )}

            <div className="pt-2 border-t border-border/60 grid grid-cols-2 gap-3">
              <InfoRow label="Organizer name" value={tournament.contact_organizer_name} />
              <InfoRow label="Company name" value={tournament.contact_company_name} />
              <InfoRow label="Phone" value={tournament.contact_phone} />
              <InfoRow label="Email" value={tournament.contact_email} />
              <InfoRow label="Emergency contact" value={tournament.contact_emergency_phone} />
              <InfoRow label="Website" value={tournament.contact_website} />
            </div>

            <div className="pt-2 border-t border-border/60 flex flex-wrap gap-2">
              <DocBadge url={tournament.company_registration_certificate} label="Company Reg. Certificate" onPreview={onPreview} />
              <DocBadge url={tournament.business_license} label="Business License" onPreview={onPreview} />
              <DocBadge url={tournament.organizer_cnic_front} label="CNIC Front" onPreview={onPreview} />
              <DocBadge url={tournament.organizer_cnic_back} label="CNIC Back" onPreview={onPreview} />
              <DocBadge url={tournament.tax_certificate} label="Tax Certificate" onPreview={onPreview} />
              <DocBadge url={tournament.sponsor_agreement} label="Sponsor Agreement" onPreview={onPreview} />
            </div>

            {tournament.status === "rejected" && tournament.rejection_reason && (
              <p className="text-xs text-destructive">Reason: {tournament.rejection_reason}</p>
            )}

            <div className="flex items-center justify-between gap-2 pt-2 border-t border-border/60">
              <button
                onClick={onClose}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-heading font-semibold bg-muted hover:bg-muted/70 transition-colors"
              >
                <ArrowLeft className="w-4 h-4" /> Back
              </button>

              {tournament.status !== "approved" && (
                <div className="flex flex-col items-end gap-2">
                  <div className="flex gap-2">
                    <button
                      onClick={() => onDecide(tournament, "approved")}
                      disabled={saving}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-heading font-semibold bg-primary text-primary-foreground disabled:opacity-50"
                    >
                      <CheckCircle2 className="w-4 h-4" /> Approve
                    </button>
                    <button
                      onClick={() => onToggleReject(tournament.id)}
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
                        onClick={() => onDecide(tournament, "rejected", reason)}
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

export default function AdminTournaments() {
  const [tournaments, setTournaments] = useState([]);
  const [status, setStatus] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [savingId, setSavingId] = useState(null);
  const [rejectingId, setRejectingId] = useState(null);
  const [reason, setReason] = useState("");
  const [previewDoc, setPreviewDoc] = useState(null);
  const [detailTournament, setDetailTournament] = useState(null);

  const load = (s) => {
    setLoading(true);
    api
      .get("/api/admin/tournaments/", { query: { status: s } })
      .then(setTournaments)
      .catch((e) => setError(e.message || "Failed to load tournaments."))
      .finally(() => setLoading(false));
  };

  useEffect(() => load(status), [status]);

  const decide = async (tournament, newStatus, rejectionReason) => {
    setSavingId(tournament.id);
    setError("");
    try {
      const body = { status: newStatus };
      if (rejectionReason !== undefined) body.reason = rejectionReason;
      const updated = await api.patch(`/api/admin/tournaments/${tournament.id}/`, body);
      setTournaments((list) => list.map((t) => (t.id === tournament.id ? updated : t)));
      setDetailTournament((d) => (d && d.id === tournament.id ? updated : d));
      setRejectingId(null);
      setReason("");
    } catch (e) {
      setError(e.message || "Could not update tournament status.");
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
      ) : tournaments.length === 0 ? (
        <div className="text-center py-16 text-muted-foreground text-sm">No tournaments found.</div>
      ) : (
        <div className="space-y-3">
          {tournaments.map((t) => (
            <div key={t.id} className="glass rounded-xl border border-border/60 p-4 sm:p-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div
                  onClick={() => setDetailTournament(t)}
                  className="cursor-pointer rounded-lg -m-1 p-1 transition-colors hover:bg-muted/30"
                >
                  <div className="flex items-center gap-2 flex-wrap">
                    <h3 className="font-heading font-bold text-base">{t.name}</h3>
                    <span
                      className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded-full ${
                        t.status === "approved"
                          ? "bg-primary/20 text-primary"
                          : t.status === "rejected"
                          ? "bg-destructive/20 text-destructive"
                          : "bg-muted text-muted-foreground"
                      }`}
                    >
                      {t.status}
                    </span>
                  </div>
                  <p className="text-sm text-muted-foreground mt-0.5">{t.game_name} · {t.organizer_name || "No organizer"}</p>
                  <p className="text-sm text-muted-foreground">
                    {t.mode} · {formatMoney(t.prize_pool)} prize pool · starts {formatDate(t.starts_at)}
                  </p>
                  <div className="flex gap-2 mt-2 flex-wrap">
                    <DocBadge url={t.company_registration_certificate} label="Company Reg." onPreview={(url, label) => setPreviewDoc({ url, label })} />
                    <DocBadge url={t.organizer_cnic_front} label="CNIC Front" onPreview={(url, label) => setPreviewDoc({ url, label })} />
                    <DocBadge url={t.organizer_cnic_back} label="CNIC Back" onPreview={(url, label) => setPreviewDoc({ url, label })} />
                  </div>
                  {t.status === "rejected" && t.rejection_reason && (
                    <p className="text-xs text-destructive mt-2">Reason: {t.rejection_reason}</p>
                  )}
                </div>

                {t.status !== "approved" && (
                  <div className="flex flex-col items-end gap-2">
                    <div className="flex gap-2">
                      <button
                        onClick={() => decide(t, "approved")}
                        disabled={savingId === t.id}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-heading font-semibold bg-primary text-primary-foreground disabled:opacity-50"
                      >
                        <CheckCircle2 className="w-4 h-4" /> Approve
                      </button>
                      <button
                        onClick={() => setRejectingId(rejectingId === t.id ? null : t.id)}
                        disabled={savingId === t.id}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-heading font-semibold bg-destructive/10 text-destructive disabled:opacity-50"
                      >
                        <XCircle className="w-4 h-4" /> Reject
                      </button>
                    </div>
                    {rejectingId === t.id && (
                      <div className="flex gap-2 w-full sm:w-72">
                        <input
                          value={reason}
                          onChange={(e) => setReason(e.target.value)}
                          placeholder="Reason for rejection"
                          className="flex-1 px-3 py-1.5 rounded-lg bg-muted/40 border border-border text-sm outline-none focus:border-primary"
                        />
                        <button
                          onClick={() => decide(t, "rejected", reason)}
                          disabled={savingId === t.id}
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

      <TournamentDetailDialog
        tournament={detailTournament}
        onClose={() => setDetailTournament(null)}
        onPreview={(url, label) => setPreviewDoc({ url, label })}
        onDecide={decide}
        saving={detailTournament ? savingId === detailTournament.id : false}
        rejecting={detailTournament ? rejectingId === detailTournament.id : false}
        onToggleReject={(id) => setRejectingId((cur) => (cur === id ? null : id))}
        reason={reason}
        onReasonChange={setReason}
      />
      <DocPreviewDialog doc={previewDoc} onClose={() => setPreviewDoc(null)} />
    </div>
  );
}
