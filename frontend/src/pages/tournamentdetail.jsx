import React, { useEffect, useMemo, useState } from "react";
import { useParams, Link, useNavigate, useLocation } from "react-router-dom";
import {
  ArrowLeft, ArrowRight, Trophy, Gamepad2, Calendar, Users, Loader2, Swords, Clock, CheckCircle2, UserCheck,
  Copy, LogOut, Shield, Wallet, Award, MapPin, Globe, Phone, Mail, Link2, Upload, Trash2, Megaphone, Plus,
  Download, Ban, Flag, AlertTriangle, BookOpen,
} from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/appauth";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { DocBadge, DocPreviewDialog } from "@/components/admin/docpreview";

const PLATFORM_SUGGESTIONS = ["Steam", "PlayStation", "Xbox", "Riot Games", "FACEIT", "Battle.net", "Other"];

const inputClass = "w-full px-3.5 py-2.5 rounded-xl bg-muted/40 border border-border text-sm outline-none focus:border-primary";

function Field({ label, required = false, children }) {
  return (
    <div>
      <label className="block text-xs font-heading font-bold uppercase tracking-wider text-muted-foreground mb-2">
        {label} {required && <span className="text-destructive">*</span>}
      </label>
      {children}
    </div>
  );
}

function RegistrationDialog({ open, tournament, onClose, onSubmitted }) {
  const { user } = useAuth();
  const [form, setForm] = useState(null);
  const [paymentProof, setPaymentProof] = useState(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open) return;
    setForm({
      full_name: [user?.first_name, user?.last_name].filter(Boolean).join(" "),
      gaming_username: "",
      phone_number: "",
      contact_email: user?.email || "",
      country: "",
      city: "",
      emergency_contact_name: "",
      emergency_contact_phone: "",
      platform: "",
      platform_username: "",
      accepted_rules: false,
      accepted_code_of_conduct: false,
    });
    setPaymentProof(null);
    setError("");
  }, [open, user]);

  if (!form) return null;

  const setField = (key, value) => setForm((f) => ({ ...f, [key]: value }));
  const needsPlatform = tournament.mode !== "offline";
  const hasFee = Number(tournament.registration_fee) > 0;

  const submit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError("");
    try {
      const formData = new FormData();
      formData.append("tournament", tournament.id);
      Object.entries(form).forEach(([key, value]) => {
        if (value === "" || value === null || value === undefined) return;
        formData.append(key, value);
      });
      if (paymentProof) formData.append("payment_proof", paymentProof);
      const registration = await api.post("/api/registrations/", formData, { formData: true });
      onSubmitted(registration);
    } catch (err) {
      let msg = err.message || "Could not submit your registration.";
      if (err.data && typeof err.data === "object") {
        msg = Object.entries(err.data).map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(" ") : v}`).join(" — ");
      }
      setError(msg);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Register for {tournament.title}</DialogTitle>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-4">
          <Field label="Full Name" required>
            <input required className={inputClass} value={form.full_name} onChange={(e) => setField("full_name", e.target.value)} />
          </Field>
          <Field label="Gaming Username" required>
            <input required className={inputClass} placeholder="e.g. ALI or Knee" value={form.gaming_username} onChange={(e) => setField("gaming_username", e.target.value)} />
          </Field>
          <Field label="Phone Number" required>
            <input required className={inputClass} placeholder="+92xxxxxxxxxx" value={form.phone_number} onChange={(e) => setField("phone_number", e.target.value)} />
          </Field>
          <Field label="Email" required>
            <input required type="email" className={inputClass} value={form.contact_email} onChange={(e) => setField("contact_email", e.target.value)} />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Country" required>
              <input required className={inputClass} placeholder="Pakistan" value={form.country} onChange={(e) => setField("country", e.target.value)} />
            </Field>
            <Field label="City" required>
              <input required className={inputClass} placeholder="Lahore" value={form.city} onChange={(e) => setField("city", e.target.value)} />
            </Field>
          </div>

          <div className="pt-2 border-t border-border/60 space-y-3">
            <p className="text-xs text-muted-foreground">Emergency Contact (optional) — especially useful for LAN events.</p>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Name">
                <input className={inputClass} value={form.emergency_contact_name} onChange={(e) => setField("emergency_contact_name", e.target.value)} />
              </Field>
              <Field label="Phone Number">
                <input className={inputClass} value={form.emergency_contact_phone} onChange={(e) => setField("emergency_contact_phone", e.target.value)} />
              </Field>
            </div>
          </div>

          {needsPlatform && (
            <div className="pt-2 border-t border-border/60 space-y-3">
              <Field label="Platform" required>
                <input required list="reg-platform-suggestions" className={inputClass} value={form.platform} onChange={(e) => setField("platform", e.target.value)} />
                <datalist id="reg-platform-suggestions">
                  {PLATFORM_SUGGESTIONS.map((p) => <option key={p} value={p} />)}
                </datalist>
              </Field>
              <Field label="Platform Username" required>
                <input required className={inputClass} placeholder="Steam ID / Tekken ID / PSN / Xbox Gamertag" value={form.platform_username} onChange={(e) => setField("platform_username", e.target.value)} />
              </Field>
            </div>
          )}

          <div className="pt-2 border-t border-border/60 space-y-2">
            <label className="flex items-start gap-2 text-sm">
              <input type="checkbox" required className="mt-0.5" checked={form.accepted_rules} onChange={(e) => setField("accepted_rules", e.target.checked)} />
              I agree to follow all tournament rules.
            </label>
            <label className="flex items-start gap-2 text-sm">
              <input type="checkbox" required className="mt-0.5" checked={form.accepted_code_of_conduct} onChange={(e) => setField("accepted_code_of_conduct", e.target.checked)} />
              I agree to the code of conduct.
            </label>
          </div>

          {hasFee && (
            <div className="pt-2 border-t border-border/60 space-y-2">
              <p className="text-sm">
                Registration Fee: <span className="font-heading font-bold">{formatMoney(tournament.registration_fee)}</span>
              </p>
              <Field label="Payment Screenshot" required>
                <input
                  required
                  type="file"
                  accept="image/*"
                  onChange={(e) => setPaymentProof(e.target.files?.[0] || null)}
                  className="w-full text-xs text-muted-foreground file:mr-3 file:px-3 file:py-1.5 file:rounded-lg file:border-0 file:bg-primary file:text-primary-foreground file:text-xs file:font-heading file:font-semibold"
                />
              </Field>
              <p className="text-xs text-muted-foreground">
                Your registration will be pending until the organizer verifies your payment.
              </p>
            </div>
          )}

          {error && (
            <div className="text-sm text-destructive bg-destructive/10 border border-destructive/30 rounded-lg px-3 py-2">
              {error}
            </div>
          )}

          <div className="flex justify-between pt-2">
            <button type="button" onClick={onClose} className="px-4 py-2.5 rounded-xl text-sm font-heading font-semibold bg-muted">
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving}
              className="inline-flex items-center gap-1.5 px-5 py-2.5 rounded-xl text-sm font-heading font-bold bg-primary text-primary-foreground disabled:opacity-50"
            >
              {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
              Register
            </button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

const MODE_LABELS = { online: "Online", offline: "Offline", hybrid: "Hybrid" };
const BRACKET_FORMAT_LABELS = {
  single: "Single Elimination", double: "Double Elimination", guarantee3: "3-Game Guarantee",
  round_robin: "Round Robin", swiss: "Swiss System", group_playoff: "Group Stage + Playoff",
};
const formatMoney = (n) => `PKR ${Number(n || 0).toLocaleString()}`;
const formatDateTime = (iso) => (iso ? new Date(iso).toLocaleString() : "—");

function DetailItem({ icon: Icon = null, label, value }) {
  if (!value) return null;
  return (
    <div className="flex items-start gap-2.5">
      {Icon && <Icon className="w-4 h-4 text-primary mt-0.5 shrink-0" />}
      <div className="min-w-0">
        <p className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</p>
        <p className="text-sm break-words">{value}</p>
      </div>
    </div>
  );
}

function TeamPanel({ tournamentId, teamSize, isRegistrationOpen, onRosterChange }) {
  const { user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [team, setTeam] = useState(null);
  const [mode, setMode] = useState("create");
  const [teamName, setTeamName] = useState("");
  const [inviteCodeInput, setInviteCodeInput] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const load = () => {
    setLoading(true);
    api.get(`/api/tournaments/${tournamentId}/teams/mine/`)
      .then((t) => setTeam(t))
      .catch((e) => {
        if (e.status !== 404) setError(e.message || "Could not load your team.");
        setTeam(null);
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tournamentId]);

  const createTeam = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError("");
    try {
      const t = await api.post(`/api/tournaments/${tournamentId}/teams/`, { name: teamName });
      setTeam(t);
    } catch (err) {
      setError(err.message || "Could not create the team.");
    } finally {
      setSaving(false);
    }
  };

  const joinTeam = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError("");
    try {
      const t = await api.post(`/api/tournaments/${tournamentId}/teams/join/`, { invite_code: inviteCodeInput });
      setTeam(t);
    } catch (err) {
      setError(err.message || "Could not join that team.");
    } finally {
      setSaving(false);
    }
  };

  const leaveOrDisband = async () => {
    setSaving(true);
    setError("");
    try {
      await api.post(`/api/teams/${team.id}/leave/`, {});
      setTeam(null);
    } catch (err) {
      setError(err.message || "Could not leave the team.");
    } finally {
      setSaving(false);
    }
  };

  const registerTeam = async () => {
    setSaving(true);
    setError("");
    try {
      await api.post(`/api/teams/${team.id}/register/`, {});
      load();
      onRosterChange?.(1);
    } catch (err) {
      setError(err.message || "Could not register the team.");
    } finally {
      setSaving(false);
    }
  };

  const cancelRegistration = async () => {
    setSaving(true);
    setError("");
    try {
      await api.delete(`/api/registrations/${team.registration_id}/`);
      load();
      onRosterChange?.(-1);
    } catch (err) {
      setError(err.message || "Could not cancel the registration.");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center py-6 text-muted-foreground">
        <Loader2 className="w-5 h-5 animate-spin" />
      </div>
    );
  }

  if (!team) {
    if (!isRegistrationOpen) return null;
    return (
      <div className="mt-4 w-full sm:w-80">
        <div className="flex gap-1 p-1 rounded-xl bg-muted/30 border border-border/60 w-fit mb-3">
          <button
            onClick={() => setMode("create")}
            className={`px-3 py-1.5 rounded-lg text-xs font-heading font-semibold ${mode === "create" ? "bg-primary text-primary-foreground" : "text-muted-foreground"}`}
          >
            Create Team
          </button>
          <button
            onClick={() => setMode("join")}
            className={`px-3 py-1.5 rounded-lg text-xs font-heading font-semibold ${mode === "join" ? "bg-primary text-primary-foreground" : "text-muted-foreground"}`}
          >
            Join Team
          </button>
        </div>
        {mode === "create" ? (
          <form onSubmit={createTeam} className="flex gap-2">
            <input
              required
              value={teamName}
              onChange={(e) => setTeamName(e.target.value)}
              placeholder="Team name"
              className="flex-1 px-3 py-2 rounded-lg bg-muted/40 border border-border text-sm outline-none focus:border-primary"
            />
            <button type="submit" disabled={saving} className="px-3 py-2 rounded-lg text-sm font-heading font-semibold bg-primary text-primary-foreground disabled:opacity-50">
              {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : "Create"}
            </button>
          </form>
        ) : (
          <form onSubmit={joinTeam} className="flex gap-2">
            <input
              required
              value={inviteCodeInput}
              onChange={(e) => setInviteCodeInput(e.target.value)}
              placeholder="Invite code"
              className="flex-1 px-3 py-2 rounded-lg bg-muted/40 border border-border text-sm outline-none focus:border-primary uppercase"
            />
            <button type="submit" disabled={saving} className="px-3 py-2 rounded-lg text-sm font-heading font-semibold bg-primary text-primary-foreground disabled:opacity-50">
              {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : "Join"}
            </button>
          </form>
        )}
        {error && <p className="mt-2 text-xs text-destructive">{error}</p>}
      </div>
    );
  }

  const isCaptain = team.captain === user?.id;
  const isFull = team.members.length >= teamSize;

  return (
    <div className="mt-4 w-full sm:w-80 rounded-xl border border-border/60 glass p-4">
      <div className="flex items-center justify-between mb-2">
        <h3 className="font-heading font-bold text-sm flex items-center gap-1.5"><Shield className="w-4 h-4 text-primary" /> {team.name}</h3>
        {team.is_registered && (
          <span className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full bg-primary/10 text-primary">
            <CheckCircle2 className="w-3 h-3" /> Registered
          </span>
        )}
      </div>
      <ul className="text-sm text-muted-foreground mb-2 space-y-0.5">
        {team.members.map((m) => (
          <li key={m.player_id}>{m.name}{m.is_captain ? " (Captain)" : ""}</li>
        ))}
      </ul>
      {!team.is_registered && (
        <div className="flex items-center gap-2 mb-3 text-xs text-muted-foreground">
          <span>Invite code: <span className="font-mono font-semibold text-foreground">{team.invite_code}</span></span>
          <button onClick={() => navigator.clipboard?.writeText(team.invite_code)} className="hover:text-primary">
            <Copy className="w-3.5 h-3.5" />
          </button>
        </div>
      )}
      {error && <p className="mb-2 text-xs text-destructive">{error}</p>}
      <div className="flex flex-wrap gap-2">
        {team.is_registered ? (
          isCaptain && (
            <button onClick={cancelRegistration} disabled={saving} className="px-3 py-1.5 rounded-lg text-xs font-heading font-semibold bg-muted disabled:opacity-50">
              Cancel Registration
            </button>
          )
        ) : (
          <>
            {isCaptain && (
              <button
                onClick={registerTeam}
                disabled={saving || !isFull}
                className="px-3 py-1.5 rounded-lg text-xs font-heading font-semibold bg-primary text-primary-foreground disabled:opacity-50"
              >
                Register Team ({team.members.length}/{teamSize})
              </button>
            )}
            <button onClick={leaveOrDisband} disabled={saving} className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-heading font-semibold bg-destructive/10 text-destructive disabled:opacity-50">
              <LogOut className="w-3.5 h-3.5" /> {isCaptain ? "Disband" : "Leave"}
            </button>
          </>
        )}
      </div>
    </div>
  );
}

function RegistrationDetailDialog({ registration, tournament, onClose, onPreview, onReview, reviewing, onCheckIn, checkingIn }) {
  const [showRejectForm, setShowRejectForm] = useState(false);
  const [rejectReason, setRejectReason] = useState("");

  useEffect(() => {
    setShowRejectForm(false);
    setRejectReason("");
  }, [registration?.id]);

  const hasFee = tournament && Number(tournament.registration_fee) > 0;
  const canCheckIn = registration && !registration.checked_in
    && registration.status !== "rejected" && (!hasFee || registration.status === "approved");

  const confirmReject = () => {
    onReview(registration.id, "rejected", rejectReason.trim());
    setShowRejectForm(false);
  };

  return (
    <Dialog open={!!registration} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{registration?.team_name || registration?.full_name || registration?.player_email}</DialogTitle>
        </DialogHeader>
        {registration && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-x-4 gap-y-4">
              <DetailItem label="Full Name" value={registration.full_name} />
              <DetailItem label="Gaming Username" value={registration.gaming_username} />
              <DetailItem icon={Phone} label="Phone" value={registration.phone_number} />
              <DetailItem icon={Mail} label="Email" value={registration.contact_email || registration.player_email} />
              <DetailItem label="Country" value={registration.country} />
              <DetailItem label="City" value={registration.city} />
              <DetailItem label="Emergency Contact" value={registration.emergency_contact_name} />
              <DetailItem label="Emergency Phone" value={registration.emergency_contact_phone} />
              <DetailItem icon={Globe} label="Platform" value={registration.platform} />
              <DetailItem label="Platform Username" value={registration.platform_username} />
              <DetailItem icon={Calendar} label="Registered" value={formatDateTime(registration.registered_at)} />
            </div>

            <div className="flex gap-4 text-xs text-muted-foreground pt-3 border-t border-border/60">
              <span>{registration.accepted_rules ? "✅" : "❌"} Rules accepted</span>
              <span>{registration.accepted_code_of_conduct ? "✅" : "❌"} Code of conduct accepted</span>
            </div>

            {(hasFee || registration.status === "rejected") && (
              <div className="pt-3 border-t border-border/60 flex items-center gap-2 flex-wrap">
                <span className={`inline-flex items-center gap-1 text-[10px] font-bold uppercase px-2 py-0.5 rounded-full ${
                  registration.status === "approved" ? "bg-primary/10 text-primary"
                  : registration.status === "rejected" ? "bg-destructive/10 text-destructive"
                  : "bg-muted text-muted-foreground"
                }`}>
                  {registration.status}
                </span>
                {hasFee && <DocBadge url={registration.payment_proof} label="Payment Screenshot" onPreview={onPreview} />}
                {registration.status === "rejected" && registration.rejection_reason && (
                  <span className="text-xs text-destructive">Reason: {registration.rejection_reason}</span>
                )}
              </div>
            )}

            {showRejectForm && (
              <div className="pt-3 border-t border-border/60 space-y-2">
                <label className="block text-xs font-heading font-bold uppercase tracking-wider text-muted-foreground">
                  Reason for rejection <span className="text-destructive">*</span>
                </label>
                <textarea
                  value={rejectReason}
                  onChange={(e) => setRejectReason(e.target.value)}
                  rows={3}
                  autoFocus
                  placeholder="e.g. Payment screenshot doesn't match the entry fee — please re-upload a clear screenshot."
                  className="w-full px-3.5 py-2.5 rounded-xl bg-muted/40 border border-border text-sm outline-none focus:border-destructive"
                />
                <p className="text-[11px] text-muted-foreground">
                  The player will see this reason and can cancel and re-apply once it's fixed.
                </p>
                <div className="flex justify-end gap-2">
                  <button
                    onClick={() => setShowRejectForm(false)}
                    disabled={reviewing}
                    className="px-3 py-1.5 rounded-lg text-sm font-heading font-semibold bg-muted disabled:opacity-50"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={confirmReject}
                    disabled={reviewing || !rejectReason.trim()}
                    className="px-3 py-1.5 rounded-lg text-sm font-heading font-semibold bg-destructive text-destructive-foreground disabled:opacity-50"
                  >
                    Confirm Reject
                  </button>
                </div>
              </div>
            )}

            <div className="flex items-center justify-between gap-2 pt-3 border-t border-border/60">
              <button
                onClick={onClose}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-heading font-semibold bg-muted hover:bg-muted/70 transition-colors"
              >
                <ArrowLeft className="w-4 h-4" /> Back
              </button>
              <div className="flex gap-2">
                {hasFee && registration.status === "pending" && (
                  <button
                    onClick={() => onReview(registration.id, "approved")}
                    disabled={reviewing}
                    className="px-3 py-1.5 rounded-lg text-sm font-heading font-semibold bg-primary text-primary-foreground disabled:opacity-50"
                  >
                    Approve
                  </button>
                )}
                {registration.status !== "rejected" && !showRejectForm && (
                  <button
                    onClick={() => setShowRejectForm(true)}
                    disabled={reviewing}
                    className="px-3 py-1.5 rounded-lg text-sm font-heading font-semibold bg-destructive/10 text-destructive disabled:opacity-50"
                  >
                    Reject
                  </button>
                )}
                {registration.checked_in ? (
                  <button
                    onClick={() => onCheckIn(registration.id, false)}
                    disabled={checkingIn}
                    className="px-3 py-1.5 rounded-lg text-sm font-heading font-semibold bg-muted text-muted-foreground disabled:opacity-50"
                  >
                    Undo check-in
                  </button>
                ) : canCheckIn && (
                  <button
                    onClick={() => onCheckIn(registration.id, true)}
                    disabled={checkingIn}
                    className="px-3 py-1.5 rounded-lg text-sm font-heading font-semibold bg-primary text-primary-foreground disabled:opacity-50"
                  >
                    Check in
                  </button>
                )}
              </div>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

const REGISTRATION_STATUS_META = {
  approved: "bg-primary/10 text-primary",
  rejected: "bg-destructive/10 text-destructive",
  cancelled: "bg-destructive/10 text-destructive",
  disqualified: "bg-destructive/10 text-destructive",
  pending: "bg-muted text-muted-foreground",
};

function TeamHistoryList({ teamId }) {
  const [history, setHistory] = useState(null);
  useEffect(() => {
    api.get(`/api/teams/${teamId}/history/`).then(setHistory).catch(() => setHistory([]));
  }, [teamId]);
  if (!history) {
    return <p className="text-xs text-muted-foreground py-2"><Loader2 className="w-3.5 h-3.5 animate-spin inline" /></p>;
  }
  if (history.length === 0) return <p className="text-xs text-muted-foreground py-2">No history yet.</p>;
  return (
    <div className="space-y-1 py-2">
      {history.map((h) => (
        <div key={h.id} className="text-xs text-muted-foreground">
          <span className="font-medium text-foreground">{h.action}</span>
          {h.reason && <span> — {h.reason}</span>}
          <span className="ml-1">({new Date(h.created_at).toLocaleString()})</span>
        </div>
      ))}
    </div>
  );
}

function TeamSubstituteForm({ team, onSubbed, onCancel }) {
  const [outgoing, setOutgoing] = useState("");
  const [incomingEmail, setIncomingEmail] = useState("");
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const submit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError("");
    try {
      const matches = await api.get("/api/players/", { query: { search: incomingEmail } });
      const results = matches.results || matches;
      const incoming = results.find((p) => p.email?.toLowerCase() === incomingEmail.trim().toLowerCase());
      if (!incoming) {
        setError("No player found with that exact email.");
        return;
      }
      const updated = await api.post(`/api/teams/${team.id}/substitute/`, {
        outgoing_player_id: Number(outgoing),
        incoming_player_id: incoming.id,
        reason,
      });
      onSubbed(updated);
    } catch (err) {
      setError(err.message || "Could not substitute this player.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={submit} className="space-y-2 py-2">
      <select
        value={outgoing}
        onChange={(e) => setOutgoing(e.target.value)}
        required
        className="w-full text-xs px-2.5 py-1.5 rounded-lg bg-muted/40 border border-border outline-none focus:border-primary"
      >
        <option value="">Outgoing player…</option>
        {team.members.map((m) => (
          <option key={m.player_id} value={m.player_id}>{m.email}</option>
        ))}
      </select>
      <input
        value={incomingEmail}
        onChange={(e) => setIncomingEmail(e.target.value)}
        placeholder="Incoming player's exact email"
        required
        className="w-full text-xs px-2.5 py-1.5 rounded-lg bg-muted/40 border border-border outline-none focus:border-primary"
      />
      <textarea
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        placeholder="Reason (required)"
        required
        rows={2}
        className="w-full text-xs px-2.5 py-1.5 rounded-lg bg-muted/40 border border-border outline-none focus:border-primary"
      />
      {error && <p className="text-xs text-destructive">{error}</p>}
      <div className="flex gap-2">
        <button
          type="submit"
          disabled={saving}
          className="px-3 py-1.5 rounded-lg text-xs font-heading font-semibold bg-primary text-primary-foreground disabled:opacity-50"
        >
          {saving ? "Saving…" : "Confirm Substitution"}
        </button>
        <button type="button" onClick={onCancel} className="px-3 py-1.5 rounded-lg text-xs font-heading font-semibold text-muted-foreground hover:text-foreground">
          Cancel
        </button>
      </div>
    </form>
  );
}

function TeamRosterRow({ team, isStaff, onChange }) {
  const [locking, setLocking] = useState(false);
  const [error, setError] = useState("");
  const [expanded, setExpanded] = useState(false);
  const [showSub, setShowSub] = useState(false);

  const toggleLock = async () => {
    setLocking(true);
    setError("");
    try {
      const action = team.is_locked ? "unlock" : "lock";
      const updated = await api.post(`/api/teams/${team.id}/${action}/`, {});
      onChange(updated);
    } catch (e) {
      setError(e.message || "Could not update the roster lock.");
    } finally {
      setLocking(false);
    }
  };

  return (
    <div className="rounded-xl border border-border/60 glass p-3">
      <div className="flex items-center justify-between gap-3">
        <button type="button" onClick={() => setExpanded((v) => !v)} className="flex items-center gap-2 text-left">
          <Shield className="w-4 h-4 text-primary shrink-0" />
          <span className="font-heading font-semibold text-sm">{team.name}</span>
          <span className="text-xs text-muted-foreground">({team.members.length} members)</span>
        </button>
        <div className="flex items-center gap-2 shrink-0">
          <span className={`text-[10px] px-2 py-0.5 rounded-full font-heading font-bold uppercase ${team.is_locked ? "bg-accent/10 text-accent" : "bg-muted text-muted-foreground"}`}>
            {team.is_locked ? "Locked" : "Unlocked"}
          </span>
          {(!team.is_locked || isStaff) && (
            <button
              onClick={toggleLock}
              disabled={locking}
              className="text-xs font-heading font-semibold text-primary hover:underline disabled:opacity-50"
            >
              {locking ? "…" : team.is_locked ? "Unlock" : "Lock"}
            </button>
          )}
        </div>
      </div>
      {error && <p className="text-xs text-destructive mt-1">{error}</p>}
      {expanded && (
        <div className="mt-2 pt-2 border-t border-border/40">
          <div className="space-y-1 mb-2">
            {team.members.map((m) => (
              <div key={m.player_id} className="text-xs text-muted-foreground flex items-center gap-1.5">
                {m.email} {m.is_captain && <span className="text-primary font-medium">(Captain)</span>}
              </div>
            ))}
          </div>
          {isStaff && (
            <div className="flex gap-3 mb-1">
              <button
                type="button"
                onClick={() => setShowSub((v) => !v)}
                className="text-xs text-muted-foreground hover:text-primary"
              >
                {showSub ? "Cancel substitution" : "Substitute a player"}
              </button>
            </div>
          )}
          {showSub && (
            <TeamSubstituteForm
              team={team}
              onCancel={() => setShowSub(false)}
              onSubbed={(updated) => {
                onChange(updated);
                setShowSub(false);
              }}
            />
          )}
          <details className="mt-1">
            <summary className="text-xs text-muted-foreground hover:text-primary cursor-pointer select-none">Roster history</summary>
            <TeamHistoryList teamId={team.id} />
          </details>
        </div>
      )}
    </div>
  );
}

function TeamRosterPanel({ tournamentId, isStaff }) {
  const [teams, setTeams] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.get(`/api/tournaments/${tournamentId}/teams/`)
      .then(setTeams)
      .catch((e) => setError(e.message || "Could not load teams."));
  }, [tournamentId]);

  const updateTeam = (updated) => {
    setTeams((prev) => prev.map((t) => (t.id === updated.id ? updated : t)));
  };

  if (error) return <p className="text-sm text-destructive">{error}</p>;
  if (!teams) {
    return (
      <div className="flex justify-center py-8 text-muted-foreground">
        <Loader2 className="w-5 h-5 animate-spin" />
      </div>
    );
  }
  if (teams.length === 0) {
    return <div className="glass rounded-xl border border-border/60 p-6 text-center text-sm text-muted-foreground">No teams yet.</div>;
  }
  return (
    <div className="space-y-2">
      {teams.map((t) => (
        <TeamRosterRow key={t.id} team={t} isStaff={isStaff} onChange={updateTeam} />
      ))}
    </div>
  );
}

function DisputeFileForm({ tournamentId }) {
  const [open, setOpen] = useState(false);
  const [description, setDescription] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [submitted, setSubmitted] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError("");
    try {
      await api.post(`/api/tournaments/${tournamentId}/disputes/`, { description });
      setSubmitted(true);
      setOpen(false);
      setDescription("");
    } catch (err) {
      setError(err.message || "Could not file this dispute.");
    } finally {
      setSaving(false);
    }
  };

  if (submitted) {
    return (
      <div className="mt-3 text-sm text-primary bg-primary/10 border border-primary/30 rounded-lg px-3 py-2">
        Your dispute has been filed. The organizer (or an admin, if you escalate it) will review it.
      </div>
    );
  }

  return (
    <div className="mt-3">
      {!open ? (
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-destructive"
        >
          <Flag className="w-3.5 h-3.5" /> Report an issue
        </button>
      ) : (
        <form onSubmit={submit} className="rounded-xl border border-border/60 glass p-3 max-w-md space-y-2">
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Describe the issue you'd like to raise about this tournament…"
            rows={3}
            required
            className="w-full text-sm px-2.5 py-2 rounded-lg bg-background border border-border outline-none focus:border-primary"
          />
          {error && <p className="text-xs text-destructive">{error}</p>}
          <div className="flex gap-2">
            <button
              type="submit"
              disabled={saving || !description.trim()}
              className="px-3 py-1.5 rounded-lg text-xs font-heading font-semibold bg-primary text-primary-foreground disabled:opacity-50"
            >
              {saving ? "Filing…" : "File Dispute"}
            </button>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="px-3 py-1.5 rounded-lg text-xs font-heading font-semibold text-muted-foreground hover:text-foreground"
            >
              Cancel
            </button>
          </div>
        </form>
      )}
    </div>
  );
}

function DisputeRow({ dispute, onDecide, onEscalate, saving }) {
  const [notes, setNotes] = useState("");
  const [action, setAction] = useState(null);
  const canDecide = dispute.status === "open" || dispute.status === "under_review";

  return (
    <div className="rounded-xl border border-border/60 glass p-3">
      <div className="flex items-center gap-2 flex-wrap mb-1">
        <span
          className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded-full ${
            dispute.status === "resolved" ? "bg-primary/20 text-primary"
            : dispute.status === "dismissed" ? "bg-destructive/20 text-destructive"
            : "bg-muted text-muted-foreground"
          }`}
        >
          {dispute.status.replace("_", " ")}
        </span>
        {dispute.escalated_to_admin && (
          <span className="inline-flex items-center gap-1 text-[10px] font-bold uppercase px-2 py-0.5 rounded-full bg-destructive/10 text-destructive">
            <AlertTriangle className="w-3 h-3" /> Escalated to admin
          </span>
        )}
        <span className="text-xs text-muted-foreground">{dispute.filed_by_email}</span>
      </div>
      <p className="text-sm">{dispute.description}</p>
      {!canDecide && dispute.resolution_notes && (
        <p className="text-xs text-muted-foreground mt-1">Resolution: {dispute.resolution_notes}</p>
      )}
      {canDecide && !dispute.escalated_to_admin && (
        <div className="mt-2">
          {!action ? (
            <div className="flex gap-2">
              <button onClick={() => setAction("resolved")} className="text-xs px-2 py-1 rounded-md bg-primary/10 text-primary hover:bg-primary/20">
                Resolve
              </button>
              <button onClick={() => setAction("dismissed")} className="text-xs px-2 py-1 rounded-md bg-destructive/10 text-destructive hover:bg-destructive/20">
                Dismiss
              </button>
              <button onClick={() => onEscalate(dispute)} className="text-xs px-2 py-1 rounded-md text-muted-foreground hover:text-foreground">
                Escalate to admin
              </button>
            </div>
          ) : (
            <div className="flex gap-2">
              <input
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="Resolution notes"
                className="flex-1 text-xs px-2 py-1 rounded-md bg-muted/40 border border-border outline-none focus:border-primary"
              />
              <button
                onClick={() => onDecide(dispute, action, notes)}
                disabled={saving || !notes.trim()}
                className="text-xs px-2 py-1 rounded-md bg-primary text-primary-foreground disabled:opacity-50"
              >
                Confirm
              </button>
            </div>
          )}
        </div>
      )}
      {canDecide && dispute.escalated_to_admin && (
        <p className="text-xs text-muted-foreground mt-2">Awaiting admin review — you can no longer resolve this directly.</p>
      )}
    </div>
  );
}

function TournamentDisputesPanel({ tournamentId }) {
  const [disputes, setDisputes] = useState(null);
  const [error, setError] = useState("");
  const [savingId, setSavingId] = useState(null);

  useEffect(() => {
    api.get(`/api/tournaments/${tournamentId}/disputes/`).then(setDisputes).catch((e) => setError(e.message || "Could not load disputes."));
  }, [tournamentId]);

  const decide = async (dispute, newStatus, resolutionNotes) => {
    setSavingId(dispute.id);
    try {
      const updated = await api.patch(`/api/disputes/${dispute.id}/status/`, { status: newStatus, resolution_notes: resolutionNotes });
      setDisputes((list) => list.map((d) => (d.id === dispute.id ? updated : d)));
    } catch (e) {
      setError(e.message || "Could not update this dispute.");
    } finally {
      setSavingId(null);
    }
  };

  const escalate = async (dispute) => {
    setSavingId(dispute.id);
    try {
      const updated = await api.post(`/api/disputes/${dispute.id}/escalate/`);
      setDisputes((list) => list.map((d) => (d.id === dispute.id ? updated : d)));
    } catch (e) {
      setError(e.message || "Could not escalate this dispute.");
    } finally {
      setSavingId(null);
    }
  };

  if (error) return <p className="text-sm text-destructive">{error}</p>;
  if (!disputes) {
    return (
      <div className="flex justify-center py-6 text-muted-foreground">
        <Loader2 className="w-5 h-5 animate-spin" />
      </div>
    );
  }
  if (disputes.length === 0) {
    return <div className="glass rounded-xl border border-border/60 p-6 text-center text-sm text-muted-foreground">No disputes filed for this tournament.</div>;
  }
  return (
    <div className="space-y-2">
      {disputes.map((d) => (
        <DisputeRow key={d.id} dispute={d} onDecide={decide} onEscalate={escalate} saving={savingId === d.id} />
      ))}
    </div>
  );
}

const RULE_SECTIONS = [
  { key: "match_format_rules", label: "Match Format" },
  { key: "conduct_rules", label: "Conduct" },
  { key: "scoring_rules", label: "Scoring" },
  { key: "penalties_and_disqualification", label: "Penalties & Disqualification" },
  { key: "additional_notes", label: "Additional Notes" },
];

function RulesPublishForm({ tournamentId, onPublished, onCancel }) {
  const [fields, setFields] = useState({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const submit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError("");
    try {
      const rules = await api.post(`/api/tournaments/${tournamentId}/rules/`, fields);
      onPublished(rules);
    } catch (err) {
      setError(err.message || "Could not publish these rules.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={submit} className="space-y-3">
      {RULE_SECTIONS.map((s) => (
        <div key={s.key}>
          <label className="block text-xs font-heading font-bold uppercase tracking-wider text-muted-foreground mb-1">{s.label}</label>
          <textarea
            value={fields[s.key] || ""}
            onChange={(e) => setFields((f) => ({ ...f, [s.key]: e.target.value }))}
            rows={3}
            className="w-full text-sm px-3 py-2 rounded-lg bg-muted/40 border border-border outline-none focus:border-primary"
          />
        </div>
      ))}
      {error && <p className="text-sm text-destructive">{error}</p>}
      <div className="flex gap-2">
        <button
          type="submit"
          disabled={saving}
          className="px-4 py-2 rounded-lg text-sm font-heading font-semibold bg-primary text-primary-foreground disabled:opacity-50"
        >
          {saving ? "Publishing…" : "Publish New Version"}
        </button>
        <button type="button" onClick={onCancel} className="px-4 py-2 rounded-lg text-sm font-heading font-semibold text-muted-foreground hover:text-foreground">
          Cancel
        </button>
      </div>
    </form>
  );
}

function RulesHistoryList({ tournamentId }) {
  const [history, setHistory] = useState(null);
  useEffect(() => {
    api.get(`/api/tournaments/${tournamentId}/rules/history/`).then(setHistory).catch(() => setHistory([]));
  }, [tournamentId]);
  if (!history) return <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />;
  if (history.length === 0) return <p className="text-sm text-muted-foreground">No versions published yet.</p>;
  return (
    <div className="space-y-3">
      {history.map((v) => (
        <div key={v.id} className="rounded-lg border border-border/60 p-3">
          <p className="text-xs font-heading font-bold text-muted-foreground mb-1">
            Version {v.version} · {new Date(v.created_at).toLocaleString()} · {v.created_by_name}
          </p>
          {RULE_SECTIONS.map((s) => v[s.key] && (
            <p key={s.key} className="text-sm mt-1"><span className="font-semibold">{s.label}: </span>{v[s.key]}</p>
          ))}
        </div>
      ))}
    </div>
  );
}

function TournamentRulesSection({ tournamentId, canManage }) {
  const [current, setCurrent] = useState(undefined);
  const [error, setError] = useState("");
  const [showPublish, setShowPublish] = useState(false);
  const [showHistory, setShowHistory] = useState(false);

  useEffect(() => {
    api.get(`/api/tournaments/${tournamentId}/rules/`).then(setCurrent).catch((e) => setError(e.message || "Could not load rules."));
  }, [tournamentId]);

  if (error) return null;
  if (current === undefined) {
    return (
      <div className="flex justify-center py-6 text-muted-foreground">
        <Loader2 className="w-5 h-5 animate-spin" />
      </div>
    );
  }

  return (
    <div>
      {current ? (
        <div className="glass rounded-xl border border-border/60 p-5 space-y-3">
          <p className="text-xs text-muted-foreground">Version {current.version} · Published {new Date(current.created_at).toLocaleDateString()}</p>
          {RULE_SECTIONS.map((s) => current[s.key] && (
            <div key={s.key}>
              <p className="text-xs font-heading font-bold uppercase tracking-wider text-muted-foreground mb-1">{s.label}</p>
              <p className="text-sm whitespace-pre-wrap">{current[s.key]}</p>
            </div>
          ))}
        </div>
      ) : (
        !canManage && <div className="glass rounded-xl border border-border/60 p-6 text-center text-sm text-muted-foreground">No rules have been published for this tournament yet.</div>
      )}

      {canManage && (
        <div className="mt-3 flex gap-4">
          <button onClick={() => setShowPublish((v) => !v)} className="text-xs text-muted-foreground hover:text-primary">
            {showPublish ? "Cancel" : current ? "Publish New Version" : "Publish Rules"}
          </button>
          <button onClick={() => setShowHistory((v) => !v)} className="text-xs text-muted-foreground hover:text-primary">
            {showHistory ? "Hide history" : "View history"}
          </button>
        </div>
      )}

      {canManage && showPublish && (
        <div className="mt-3">
          <RulesPublishForm
            tournamentId={tournamentId}
            onCancel={() => setShowPublish(false)}
            onPublished={(rules) => {
              setCurrent(rules);
              setShowPublish(false);
            }}
          />
        </div>
      )}

      {canManage && showHistory && (
        <div className="mt-3">
          <RulesHistoryList tournamentId={tournamentId} />
        </div>
      )}
    </div>
  );
}

function RegistrationRow({ registration: r, tournament, onOpenDetail, onCheckIn, checkingIn, onCancel, cancelling }) {
  const [showCancelForm, setShowCancelForm] = useState(false);
  const [cancelReason, setCancelReason] = useState("");
  const canCancel = r.status !== "cancelled" && r.status !== "disqualified";

  const confirmCancel = () => {
    onCancel(r.id, cancelReason.trim());
    setShowCancelForm(false);
    setCancelReason("");
  };

  return (
    <>
      <tr className="border-t border-border/30">
        <td
          onClick={onOpenDetail}
          className="py-2.5 pl-4 pr-2 font-medium cursor-pointer hover:text-primary transition-colors"
          title="View full registration details"
        >
          {tournament.team_size > 1 ? (r.team_name || "—") : r.player_email}
        </td>
        {tournament.team_size > 1 && <td className="py-2.5 pr-2 text-muted-foreground">{r.player_email}</td>}
        <td className="py-2.5 pr-2 text-muted-foreground">{new Date(r.registered_at).toLocaleString()}</td>
        <td className="py-2.5 pr-2">
          <span className={`inline-flex items-center gap-1 text-[10px] font-bold uppercase px-2 py-0.5 rounded-full ${REGISTRATION_STATUS_META[r.status] || REGISTRATION_STATUS_META.pending}`}>
            {r.status}
          </span>
          {r.is_no_show && (
            <span className="ml-1 inline-flex items-center text-[10px] font-bold uppercase px-2 py-0.5 rounded-full bg-accent/10 text-accent">
              No-show
            </span>
          )}
        </td>
        <td className="py-2.5 pr-2">
          {r.checked_in ? (
            <div className="flex items-center gap-2">
              <span className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full bg-primary/10 text-primary">
                <CheckCircle2 className="w-3 h-3" /> Checked in
              </span>
              <button
                onClick={() => onCheckIn(r.id, false)}
                disabled={checkingIn}
                className="text-[11px] text-muted-foreground hover:text-destructive underline decoration-dotted disabled:opacity-50"
              >
                {checkingIn ? <Loader2 className="w-3 h-3 animate-spin" /> : "Undo"}
              </button>
            </div>
          ) : r.status === "rejected" || r.status === "cancelled" || r.status === "disqualified" ? (
            <span className="text-[11px] text-muted-foreground capitalize">{r.status}</span>
          ) : tournament.registration_fee > 0 && r.status !== "approved" ? (
            <span
              className="text-[11px] text-muted-foreground"
              title="Payment must be approved before this player can be checked in."
            >
              Awaiting payment approval
            </span>
          ) : (
            <button
              onClick={() => onCheckIn(r.id, true)}
              disabled={checkingIn}
              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-heading font-semibold bg-primary text-primary-foreground disabled:opacity-50"
            >
              {checkingIn ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : "Check in"}
            </button>
          )}
        </td>
        <td className="py-2.5 pr-4">
          {canCancel && (
            <button
              onClick={() => setShowCancelForm((s) => !s)}
              disabled={cancelling}
              className="inline-flex items-center gap-1 text-[11px] text-destructive/80 hover:text-destructive disabled:opacity-50"
            >
              <Ban className="w-3 h-3" /> Cancel
            </button>
          )}
        </td>
      </tr>
      {showCancelForm && (
        <tr className="border-t border-border/30 bg-destructive/5">
          <td colSpan={6} className="py-3 px-4">
            <div className="flex flex-wrap items-center gap-2">
              <input
                value={cancelReason}
                onChange={(e) => setCancelReason(e.target.value)}
                placeholder="Reason for cancelling this registration"
                className="flex-1 min-w-[200px] px-3 py-1.5 rounded-lg bg-muted/40 border border-border text-sm outline-none focus:border-destructive"
              />
              <button
                onClick={confirmCancel}
                disabled={cancelling || !cancelReason.trim()}
                className="px-3 py-1.5 rounded-lg text-xs font-heading font-semibold bg-destructive text-destructive-foreground disabled:opacity-50"
              >
                {cancelling ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : "Confirm Cancel"}
              </button>
              <button
                onClick={() => setShowCancelForm(false)}
                disabled={cancelling}
                className="px-3 py-1.5 rounded-lg text-xs font-heading font-semibold bg-muted disabled:opacity-50"
              >
                Back
              </button>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

const ANNOUNCEMENT_CATEGORY_META = {
  match_timing: { label: "Match Timing" },
  delay: { label: "Delay" },
  rule_change: { label: "Rule Change" },
  venue_update: { label: "Venue Update" },
  general: { label: "General" },
};

function AnnouncementsSection({ tournamentId, canManage }) {
  const [announcements, setAnnouncements] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [category, setCategory] = useState("general");
  const [title, setTitle] = useState("");
  const [message, setMessage] = useState("");
  const [posting, setPosting] = useState(false);
  const [postError, setPostError] = useState("");
  const [deletingId, setDeletingId] = useState(null);

  const load = () => {
    api.get(`/api/tournaments/${tournamentId}/announcements/`).then(setAnnouncements).catch(() => setAnnouncements([]));
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tournamentId]);

  const submit = async (e) => {
    e.preventDefault();
    setPosting(true);
    setPostError("");
    try {
      await api.post(`/api/tournaments/${tournamentId}/announcements/`, { category, title, message });
      setTitle("");
      setMessage("");
      setCategory("general");
      setShowForm(false);
      load();
    } catch (err) {
      setPostError(err.message || "Could not post announcement.");
    } finally {
      setPosting(false);
    }
  };

  const remove = async (announcementId) => {
    setDeletingId(announcementId);
    try {
      await api.delete(`/api/announcements/${announcementId}/`);
      setAnnouncements((list) => list.filter((a) => a.id !== announcementId));
    } catch {
      /* best effort */
    } finally {
      setDeletingId(null);
    }
  };

  if (announcements === null) {
    return (
      <div className="mt-8 flex justify-center py-6 text-muted-foreground">
        <Loader2 className="w-5 h-5 animate-spin" />
      </div>
    );
  }

  if (announcements.length === 0 && !canManage) return null;

  return (
    <div className="mt-8">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Megaphone className="w-5 h-5 text-primary" />
          <h2 className="font-display font-bold text-xl">Announcements</h2>
        </div>
        {canManage && (
          <button
            onClick={() => setShowForm((v) => !v)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-heading font-semibold bg-primary text-primary-foreground"
          >
            <Plus className="w-4 h-4" /> Post Announcement
          </button>
        )}
      </div>

      {showForm && (
        <form onSubmit={submit} className="glass rounded-xl border border-border/60 p-5 mb-4 space-y-3">
          <select value={category} onChange={(e) => setCategory(e.target.value)} className={inputClass}>
            {Object.entries(ANNOUNCEMENT_CATEGORY_META).map(([value, meta]) => (
              <option key={value} value={value}>{meta.label}</option>
            ))}
          </select>
          <input required value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Title" className={inputClass} />
          <textarea
            required
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            placeholder="Details"
            rows={3}
            className={inputClass}
          />
          {postError && <p className="text-sm text-destructive">{postError}</p>}
          <button
            type="submit"
            disabled={posting}
            className="px-4 py-2 rounded-lg text-sm font-heading font-semibold bg-primary text-primary-foreground disabled:opacity-50"
          >
            {posting ? <Loader2 className="w-4 h-4 animate-spin" /> : "Post"}
          </button>
        </form>
      )}

      {announcements.length === 0 ? (
        <div className="glass rounded-xl border border-border/60 p-6 text-center text-sm text-muted-foreground">
          No announcements yet.
        </div>
      ) : (
        <div className="space-y-3">
          {announcements.map((a) => (
            <div key={a.id} className="glass rounded-xl border border-border/60 p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap mb-1">
                    <span className="text-[10px] font-bold uppercase px-2 py-0.5 rounded-full bg-primary/10 text-primary">
                      {a.category_display}
                    </span>
                    <h3 className="font-heading font-semibold text-sm">{a.title}</h3>
                  </div>
                  <p className="text-sm text-muted-foreground whitespace-pre-wrap">{a.message}</p>
                  <p className="text-xs text-muted-foreground mt-2">
                    {a.author_name ? `${a.author_name} · ` : ""}{formatDateTime(a.created_at)}
                  </p>
                </div>
                {canManage && (
                  <button
                    onClick={() => remove(a.id)}
                    disabled={deletingId === a.id}
                    className="shrink-0 text-muted-foreground hover:text-destructive transition-colors"
                  >
                    {deletingId === a.id ? <Loader2 className="w-4 h-4 animate-spin" /> : <Trash2 className="w-4 h-4" />}
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function TournamentDetail() {
  const { id } = useParams();
  const { user } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const cameFromMyTournaments = location.state?.from === "my-tournaments";
  const [tournament, setTournament] = useState(null);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState("");
  const [publishSaving, setPublishSaving] = useState(false);
  const [publishError, setPublishError] = useState("");
  const [myRegistration, setMyRegistration] = useState(null);
  const [bracketExists, setBracketExists] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [regSaving, setRegSaving] = useState(false);
  const [registrations, setRegistrations] = useState(null); // null = hidden (no permission or not loaded)
  const [checkingInId, setCheckingInId] = useState(null);
  const [checkInError, setCheckInError] = useState("");
  const [showRegisterDialog, setShowRegisterDialog] = useState(false);
  const [reviewingId, setReviewingId] = useState(null);
  const [reviewError, setReviewError] = useState("");
  const [previewDoc, setPreviewDoc] = useState(null);
  const [detailReg, setDetailReg] = useState(null);
  const [regSearch, setRegSearch] = useState("");
  const [regStatusFilter, setRegStatusFilter] = useState("");
  const [cancelNotice, setCancelNotice] = useState("");
  const [exportingCsv, setExportingCsv] = useState(false);
  const [exportError, setExportError] = useState("");

  useEffect(() => {
    setLoading(true);
    Promise.all([
      api.get(`/api/tournaments/${id}/`),
      api.get("/api/registrations/me/").catch(() => []),
      api.get(`/api/tournaments/${id}/registrations/`).catch(() => null),
    ])
      .then(([t, myRegs, regs]) => {
        setTournament(t);
        setMyRegistration(myRegs.find((r) => r.tournament === Number(id)) || null);
        setRegistrations(regs);
      })
      .catch((e) => setError(e.message || "Could not load this tournament."))
      .finally(() => setLoading(false));
    // Cheap existence check only — the full bracket (rounds, matches, standings) is
    // managed on its own dedicated page now.
    api.get(`/api/tournaments/${id}/brackets/`)
      .then(() => setBracketExists(true))
      .catch(() => setBracketExists(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const handleRegistered = (reg) => {
    setMyRegistration(reg);
    setTournament((t) => ({ ...t, teams: t.teams + 1 }));
    setShowRegisterDialog(false);
  };

  const deleteTournament = async () => {
    setDeleting(true);
    setDeleteError("");
    try {
      await api.delete(`/api/tournaments/${id}/`);
      navigate("/tournaments");
    } catch (e) {
      setDeleteError(e.message || "Could not delete this tournament.");
      setDeleting(false);
    }
  };

  const setPublished = async (publish) => {
    setPublishSaving(true);
    setPublishError("");
    try {
      const updated = await api.post(`/api/tournaments/${id}/publish/`, { publish });
      setTournament(updated);
    } catch (e) {
      setPublishError(e.message || "Could not update publish status.");
    } finally {
      setPublishSaving(false);
    }
  };

  const cancelRegistration = async () => {
    setRegSaving(true);
    setError("");
    try {
      await api.delete(`/api/registrations/${myRegistration.id}/`);
      setMyRegistration(null);
      setTournament((t) => ({ ...t, teams: t.teams - 1 }));
    } catch (e) {
      setError(e.message || "Could not cancel your registration.");
    } finally {
      setRegSaving(false);
    }
  };

  const checkIn = async (regId, checkedIn = true) => {
    setCheckingInId(regId);
    setCheckInError("");
    try {
      const updated = await api.patch(`/api/registrations/${regId}/check-in/`, { checked_in: checkedIn });
      setRegistrations((list) => list.map((r) => (r.id === regId ? updated : r)));
      setDetailReg((d) => (d && d.id === regId ? updated : d));
    } catch (e) {
      setCheckInError(e.message || "Could not update this player's check-in status.");
    } finally {
      setCheckingInId(null);
    }
  };

  const reviewRegistration = async (regId, newStatus, reason = "") => {
    setReviewingId(regId);
    setReviewError("");
    try {
      const payload = { status: newStatus };
      if (newStatus === "rejected") payload.reason = reason;
      const updated = await api.patch(`/api/registrations/${regId}/review/`, payload);
      setRegistrations((list) => list.map((r) => (r.id === regId ? updated : r)));
      setDetailReg((d) => (d && d.id === regId ? updated : d));
    } catch (e) {
      setReviewError(e.message || "Could not update this registration.");
    } finally {
      setReviewingId(null);
    }
  };

  const organizerCancelRegistration = async (regId, reason) => {
    setReviewingId(regId);
    setReviewError("");
    setCancelNotice("");
    try {
      const resp = await api.post(`/api/registrations/${regId}/cancel/`, { reason });
      if (resp.status === "cancelled") {
        setRegistrations((list) => list.map((r) => (r.id === regId ? resp : r)));
        setDetailReg((d) => (d && d.id === regId ? resp : d));
      } else {
        setCancelNotice(resp.detail);
      }
    } catch (e) {
      setReviewError(e.message || "Could not cancel this registration.");
    } finally {
      setReviewingId(null);
    }
  };

  const exportRegistrationsCsv = async () => {
    setExportingCsv(true);
    setExportError("");
    try {
      const blob = await api.getBlob(`/api/tournaments/${id}/registrations/export/`);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${tournament.title}-registrations.csv`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      setExportError(e.message || "Could not export registrations.");
    } finally {
      setExportingCsv(false);
    }
  };

  const registrationSearchResults = useMemo(() => {
    if (!registrations) return registrations;
    let list = registrations;
    if (regStatusFilter) list = list.filter((r) => r.status === regStatusFilter);
    if (regSearch.trim()) {
      const q = regSearch.trim().toLowerCase();
      list = list.filter((r) => [r.full_name, r.gaming_username, r.contact_email, r.player_email, r.team_name]
        .filter(Boolean).some((v) => v.toLowerCase().includes(q)));
    }
    return list;
  }, [registrations, regSearch, regStatusFilter]);

  if (loading) {
    return (
      <div className="flex justify-center py-20 text-muted-foreground">
        <Loader2 className="w-6 h-6 animate-spin" />
      </div>
    );
  }

  if (error && !tournament) {
    return (
      <div className="max-w-lg mx-auto px-4 py-16 text-center">
        <p className="text-sm text-destructive bg-destructive/10 border border-destructive/30 rounded-lg px-3 py-2 inline-block">
          {error}
        </p>
      </div>
    );
  }

  const live = tournament.phase === "live";

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 py-10 sm:py-14">
      <Link
        to={cameFromMyTournaments ? "/my-tournaments" : "/tournaments"}
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-primary mb-6"
      >
        <ArrowLeft className="w-4 h-4" /> {cameFromMyTournaments ? "Back to my tournaments" : "Back to tournaments"}
      </Link>

      <div className="glass rounded-2xl border border-border/60 p-6 sm:p-8">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <h1 className="font-display font-extrabold text-2xl">{tournament.title}</h1>
              <span className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded-full ${live ? "bg-accent/20 text-accent" : "bg-muted text-muted-foreground"}`}>
                {tournament.phase}
              </span>
            </div>
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mt-2 text-sm text-muted-foreground">
              <span className="flex items-center gap-1"><Gamepad2 className="w-3.5 h-3.5" /> {tournament.game}</span>
              <span className="flex items-center gap-1"><Calendar className="w-3.5 h-3.5" /> {new Date(tournament.start_date).toLocaleString()}</span>
              <span className="flex items-center gap-1"><Users className="w-3.5 h-3.5" /> {tournament.teams} registered</span>
              <span className="flex items-center gap-1"><Trophy className="w-3.5 h-3.5" /> Organized by {tournament.organizer}</span>
            </div>
          </div>

          {tournament.team_size <= 1 ? (
            tournament.is_registration_open && (
              myRegistration ? (
                <div className="flex flex-col items-end gap-2">
                  <span className={`inline-flex items-center gap-1 text-[10px] font-bold uppercase px-2 py-0.5 rounded-full ${
                    myRegistration.status === "approved" ? "bg-primary/10 text-primary"
                    : myRegistration.status === "rejected" ? "bg-destructive/10 text-destructive"
                    : "bg-muted text-muted-foreground"
                  }`}>
                    {myRegistration.status === "approved" ? <CheckCircle2 className="w-3 h-3" /> : <Clock className="w-3 h-3" />}
                    {myRegistration.status === "pending" ? "Pending Payment Review" : myRegistration.status}
                  </span>
                  {myRegistration.status === "rejected" && myRegistration.rejection_reason && (
                    <span className="text-xs text-destructive">Reason: {myRegistration.rejection_reason}</span>
                  )}
                  <button
                    onClick={cancelRegistration}
                    disabled={regSaving}
                    className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-heading font-semibold bg-muted text-muted-foreground disabled:opacity-50"
                  >
                    Cancel Registration
                  </button>
                </div>
              ) : (
                <button
                  onClick={() => setShowRegisterDialog(true)}
                  className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-heading font-semibold bg-primary text-primary-foreground disabled:opacity-50"
                >
                  Register
                </button>
              )
            )
          ) : (
            <TeamPanel
              tournamentId={id}
              teamSize={tournament.team_size}
              isRegistrationOpen={tournament.is_registration_open}
              onRosterChange={(delta) => setTournament((t) => ({ ...t, teams: t.teams + delta }))}
            />
          )}
        </div>

        {tournament.can_manage && tournament.status === "approved" && (
          <div className={`mt-4 p-4 rounded-xl border flex flex-wrap items-center justify-between gap-3 ${
            tournament.is_published ? "border-primary/30 bg-primary/5" : "border-accent/30 bg-accent/5"
          }`}>
            <div>
              <p className="text-sm font-heading font-semibold">
                {tournament.is_published ? "Published — visible to players" : "Not published yet"}
              </p>
              <p className="text-xs text-muted-foreground mt-0.5">
                {tournament.is_published
                  ? "Players can find and register for this tournament."
                  : "Approved by the admin, but hidden from players until you publish it."}
              </p>
            </div>
            <div className="flex items-center gap-2">
              {publishError && <span className="text-xs text-destructive">{publishError}</span>}
              <button
                onClick={() => setPublished(!tournament.is_published)}
                disabled={publishSaving}
                className={`inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-heading font-semibold disabled:opacity-50 ${
                  tournament.is_published ? "bg-muted text-muted-foreground" : "bg-primary text-primary-foreground"
                }`}
              >
                {publishSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : tournament.is_published ? "Unpublish" : "Publish"}
              </button>
            </div>
          </div>
        )}

        {error && (
          <div className="mt-4 text-sm text-destructive bg-destructive/10 border border-destructive/30 rounded-lg px-3 py-2">
            {error}
          </div>
        )}

        {!tournament.can_manage && myRegistration && <DisputeFileForm tournamentId={id} />}

        {tournament.can_manage && (
          <div className="mt-4 pt-4 border-t border-border/60">
            {!confirmingDelete ? (
              <button
                onClick={() => setConfirmingDelete(true)}
                className="inline-flex items-center gap-1.5 text-xs text-destructive/80 hover:text-destructive transition-colors"
              >
                <Trash2 className="w-3.5 h-3.5" /> Delete tournament
              </button>
            ) : (
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-xs text-destructive">
                  Permanently delete this tournament, including all registrations and matches?
                </span>
                <button
                  onClick={deleteTournament}
                  disabled={deleting}
                  className="px-3 py-1.5 rounded-lg text-xs font-heading font-semibold bg-destructive text-destructive-foreground disabled:opacity-50"
                >
                  {deleting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : "Confirm Delete"}
                </button>
                <button
                  onClick={() => setConfirmingDelete(false)}
                  disabled={deleting}
                  className="px-3 py-1.5 rounded-lg text-xs font-heading font-semibold bg-muted disabled:opacity-50"
                >
                  Cancel
                </button>
              </div>
            )}
            {deleteError && <p className="mt-2 text-xs text-destructive">{deleteError}</p>}
          </div>
        )}
      </div>

      {/* Tournament details — visible to everyone, this is what a player needs before registering */}
      <div className="mt-8 glass rounded-2xl border border-border/60 p-6 sm:p-8">
        <h2 className="font-display font-bold text-xl mb-5">Tournament Details</h2>

        <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-4 gap-y-5">
          <DetailItem icon={Wallet} label="Entry Fee" value={formatMoney(tournament.registration_fee)} />
          <DetailItem icon={Award} label="Prize Pool" value={formatMoney(tournament.prize_pool)} />
          <DetailItem label="Mode" value={MODE_LABELS[tournament.mode] || tournament.mode} />
          <DetailItem label="Bracket Format" value={BRACKET_FORMAT_LABELS[tournament.bracket_format] || tournament.bracket_format} />
          <DetailItem label="Team Size" value={tournament.team_size > 1 ? `${tournament.team_size} players/team` : "Solo"} />
          <DetailItem label="Max Participants" value={tournament.max_participants} />
          <DetailItem icon={Clock} label="Registration Deadline" value={tournament.registration_deadline && formatDateTime(tournament.registration_deadline)} />
          <DetailItem icon={Calendar} label="Starts" value={formatDateTime(tournament.start_date)} />
          <DetailItem icon={Calendar} label="Ends" value={tournament.end_date && formatDateTime(tournament.end_date)} />
        </div>

        {tournament.mode !== "online" && (tournament.venue_name || tournament.venue_address || tournament.venue_city) && (
          <div className="mt-6 pt-6 border-t border-border/60">
            <h3 className="text-xs font-heading font-bold uppercase tracking-wider text-muted-foreground mb-3">Venue</h3>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-4 gap-y-5">
              <DetailItem icon={MapPin} label="Venue" value={tournament.venue_name} />
              <DetailItem label="Address" value={tournament.venue_address} />
              <DetailItem label="City" value={[tournament.venue_city, tournament.venue_province, tournament.venue_country].filter(Boolean).join(", ")} />
              <DetailItem label="Parking" value={tournament.venue_parking_available ? "Available" : null} />
              {tournament.venue_map_link && (
                <div className="flex items-start gap-2.5">
                  <Link2 className="w-4 h-4 text-primary mt-0.5 shrink-0" />
                  <div>
                    <p className="text-[11px] uppercase tracking-wide text-muted-foreground">Map</p>
                    <a href={tournament.venue_map_link} target="_blank" rel="noopener noreferrer" className="text-sm text-primary hover:underline">
                      Open in Google Maps
                    </a>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {tournament.mode !== "offline" && (tournament.platform || tournament.discord_server || tournament.room_id) && (
          <div className="mt-6 pt-6 border-t border-border/60">
            <h3 className="text-xs font-heading font-bold uppercase tracking-wider text-muted-foreground mb-3">Online Details</h3>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-4 gap-y-5">
              <DetailItem icon={Globe} label="Platform" value={tournament.platform} />
              <DetailItem label="Room ID" value={tournament.room_id} />
              {tournament.discord_server && (
                <div className="flex items-start gap-2.5">
                  <Link2 className="w-4 h-4 text-primary mt-0.5 shrink-0" />
                  <div>
                    <p className="text-[11px] uppercase tracking-wide text-muted-foreground">Discord</p>
                    <a href={tournament.discord_server} target="_blank" rel="noopener noreferrer" className="text-sm text-primary hover:underline">
                      Join server
                    </a>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {(tournament.contact_organizer_name || tournament.contact_phone || tournament.contact_email || tournament.contact_website) && (
          <div className="mt-6 pt-6 border-t border-border/60">
            <h3 className="text-xs font-heading font-bold uppercase tracking-wider text-muted-foreground mb-3">Contact</h3>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-4 gap-y-5">
              <DetailItem label="Organizer" value={tournament.contact_organizer_name} />
              <DetailItem label="Company" value={tournament.contact_company_name} />
              <DetailItem icon={Phone} label="Phone" value={tournament.contact_phone} />
              <DetailItem icon={Mail} label="Email" value={tournament.contact_email} />
              <DetailItem label="Emergency Contact" value={tournament.contact_emergency_phone} />
              {tournament.contact_website && (
                <div className="flex items-start gap-2.5">
                  <Link2 className="w-4 h-4 text-primary mt-0.5 shrink-0" />
                  <div>
                    <p className="text-[11px] uppercase tracking-wide text-muted-foreground">Website</p>
                    <a href={tournament.contact_website} target="_blank" rel="noopener noreferrer" className="text-sm text-primary hover:underline">
                      {tournament.contact_website}
                    </a>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      <div className="mt-8">
        <div className="flex items-center gap-2 mb-4">
          <BookOpen className="w-5 h-5 text-primary" />
          <h2 className="font-display font-bold text-xl">Rules</h2>
        </div>
        <TournamentRulesSection tournamentId={id} canManage={tournament.can_manage} />
      </div>

      {myRegistration && myRegistration.rules_outdated && (
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 p-4 rounded-xl border border-accent/30 bg-accent/5">
          <p className="text-sm">The rules for this tournament have been updated since you registered. Please review them above.</p>
          <button
            onClick={async () => {
              const updated = await api.post(`/api/registrations/${myRegistration.id}/acknowledge-rules/`);
              setMyRegistration(updated);
            }}
            className="px-3 py-1.5 rounded-lg text-xs font-heading font-semibold bg-primary text-primary-foreground shrink-0"
          >
            I've read the updated rules
          </button>
        </div>
      )}

      <AnnouncementsSection tournamentId={id} canManage={tournament.can_manage} />

      {/* Registrations (organizer/staff only — hidden entirely if the API denies access) */}
      {registrations && (
        <div className="mt-8">
          <div className="flex items-center justify-between gap-3 mb-4 flex-wrap">
            <div className="flex items-center gap-2">
              <UserCheck className="w-5 h-5 text-primary" />
              <h2 className="font-display font-bold text-xl">Registrations ({registrations.length})</h2>
            </div>
            <button
              type="button"
              onClick={exportRegistrationsCsv}
              disabled={exportingCsv}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-heading font-semibold bg-muted hover:bg-muted/70 disabled:opacity-50"
            >
              {exportingCsv ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Download className="w-3.5 h-3.5" />}
              Export CSV
            </button>
          </div>
          {exportError && (
            <div className="mb-3 text-sm text-destructive bg-destructive/10 border border-destructive/30 rounded-lg px-3 py-2">
              {exportError}
            </div>
          )}

          {registrations.length > 0 && (
            <div className="flex flex-wrap items-center gap-2 mb-3">
              <input
                value={regSearch}
                onChange={(e) => setRegSearch(e.target.value)}
                placeholder="Search name, username, email…"
                className="px-3 py-1.5 rounded-lg bg-muted/40 border border-border text-sm outline-none focus:border-primary w-56"
              />
              <select
                value={regStatusFilter}
                onChange={(e) => setRegStatusFilter(e.target.value)}
                className="px-3 py-1.5 rounded-lg bg-muted/40 border border-border text-sm outline-none focus:border-primary"
              >
                <option value="">All statuses</option>
                <option value="pending">Pending</option>
                <option value="approved">Approved</option>
                <option value="rejected">Rejected</option>
                <option value="cancelled">Cancelled</option>
                <option value="disqualified">Disqualified</option>
              </select>
            </div>
          )}

          {checkInError && (
            <div className="mb-3 text-sm text-destructive bg-destructive/10 border border-destructive/30 rounded-lg px-3 py-2">
              {checkInError}
            </div>
          )}
          {reviewError && (
            <div className="mb-3 text-sm text-destructive bg-destructive/10 border border-destructive/30 rounded-lg px-3 py-2">
              {reviewError}
            </div>
          )}
          {cancelNotice && (
            <div className="mb-3 text-sm text-accent bg-accent/10 border border-accent/30 rounded-lg px-3 py-2">
              {cancelNotice}
            </div>
          )}

          {registrations.length === 0 ? (
            <div className="glass rounded-xl border border-border/60 p-6 text-center text-sm text-muted-foreground">
              No one has registered yet.
            </div>
          ) : registrationSearchResults.length === 0 ? (
            <div className="glass rounded-xl border border-border/60 p-6 text-center text-sm text-muted-foreground">
              No registrations match your search.
            </div>
          ) : (
            <div className="overflow-x-auto rounded-xl border border-border/60 glass">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-[10px] font-heading font-bold uppercase tracking-wider text-muted-foreground">
                    <th className="py-2 pl-4 pr-2">{tournament.team_size > 1 ? "Team" : "Player"}</th>
                    {tournament.team_size > 1 && <th className="py-2 pr-2">Captain</th>}
                    <th className="py-2 pr-2">Registered</th>
                    <th className="py-2 pr-2">Status</th>
                    <th className="py-2 pr-2">Check-in</th>
                    <th className="py-2 pr-4">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {registrationSearchResults.map((r) => (
                    <RegistrationRow
                      key={r.id}
                      registration={r}
                      tournament={tournament}
                      onOpenDetail={() => setDetailReg(r)}
                      onCheckIn={checkIn}
                      checkingIn={checkingInId === r.id}
                      onCancel={organizerCancelRegistration}
                      cancelling={reviewingId === r.id}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Disputes (organizer/staff only) */}
      {tournament.can_manage && (
        <div className="mt-8">
          <div className="flex items-center gap-2 mb-4">
            <Flag className="w-5 h-5 text-primary" />
            <h2 className="font-display font-bold text-xl">Disputes</h2>
          </div>
          <TournamentDisputesPanel tournamentId={id} />
        </div>
      )}

      {/* Team rosters (organizer/staff only, team-based tournaments only) */}
      {tournament.can_manage && tournament.team_size > 1 && (
        <div className="mt-8">
          <div className="flex items-center gap-2 mb-4">
            <Shield className="w-5 h-5 text-primary" />
            <h2 className="font-display font-bold text-xl">Team Rosters</h2>
          </div>
          <TeamRosterPanel tournamentId={id} isStaff={!!user?.is_staff} />
        </div>
      )}

      {/* Bracket — its own dedicated page now, so managing it isn't cluttered by
          everything else on this tournament page */}
      {(tournament.can_manage || bracketExists) && (
        <div className="mt-8">
          <div className="flex items-center justify-between gap-3 mb-1">
            <div className="flex items-center gap-2">
              <Swords className="w-5 h-5 text-primary" />
              <h2 className="font-display font-bold text-xl">Bracket</h2>
            </div>
            <Link
              to={`/tournaments/${id}/bracket`}
              state={{ from: location.state?.from }}
              className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-heading font-semibold bg-primary text-primary-foreground hover:shadow-[0_0_20px_hsl(186_100%_50%/0.4)] transition-shadow"
            >
              {bracketExists ? "View Bracket" : "Generate Bracket"} <ArrowRight className="w-4 h-4" />
            </Link>
          </div>
          <p className="text-sm text-muted-foreground">
            {bracketExists
              ? "Matches, standings, and results are managed on a dedicated bracket page."
              : "No bracket yet — only checked-in players get seeded in. Head to the bracket page to generate one."}
          </p>
        </div>
      )}

      <RegistrationDialog
        open={showRegisterDialog}
        tournament={tournament}
        onClose={() => setShowRegisterDialog(false)}
        onSubmitted={handleRegistered}
      />
      <RegistrationDetailDialog
        registration={detailReg}
        tournament={tournament}
        onClose={() => setDetailReg(null)}
        onPreview={(url, label) => setPreviewDoc({ url, label })}
        onReview={reviewRegistration}
        reviewing={detailReg ? reviewingId === detailReg.id : false}
        onCheckIn={checkIn}
        checkingIn={detailReg ? checkingInId === detailReg.id : false}
      />
      <DocPreviewDialog doc={previewDoc} onClose={() => setPreviewDoc(null)} />
    </div>
  );
}
