import React, { useEffect, useRef, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import {
  Loader2, ArrowLeft, Save, CheckCircle2, Send, RotateCcw, Ban, CalendarClock, Copy, Eye,
  Clock, XCircle, FileEdit,
} from "lucide-react";
import { api } from "@/lib/api";
import DateTimePicker from "@/components/tournaments/DateTimePicker";

const STATUS_META = {
  draft: { label: "Draft", icon: FileEdit, className: "bg-muted text-muted-foreground" },
  pending: { label: "Pending Admin Approval", icon: Clock, className: "bg-muted text-muted-foreground" },
  approved: { label: "Approved", icon: CheckCircle2, className: "bg-primary/10 text-primary" },
  rejected: { label: "Rejected", icon: XCircle, className: "bg-destructive/10 text-destructive" },
  cancelled: { label: "Cancelled", icon: Ban, className: "bg-destructive/10 text-destructive" },
};

const MODES = [
  { value: "online", label: "Online" },
  { value: "offline", label: "Offline" },
  { value: "hybrid", label: "Hybrid" },
];

const BRACKET_FORMATS = [
  { value: "single", label: "Single Elimination" },
  { value: "double", label: "Double Elimination" },
  { value: "guarantee3", label: "3-Game Guarantee" },
  { value: "round_robin", label: "Round Robin" },
  { value: "swiss", label: "Swiss System" },
  { value: "group_playoff", label: "Group Stage + Playoff" },
];

const PLATFORM_SUGGESTIONS = ["Steam", "Riot Games", "FACEIT", "Battle.net", "PUBG Mobile", "Other"];

const MAX_LENGTHS = {
  name: 200,
  venue_name: 200,
  venue_city: 100,
  venue_province: 100,
  venue_country: 100,
  discord_server: 255,
  room_id: 100,
  platform: 100,
  contact_organizer_name: 150,
  contact_company_name: 200,
  contact_phone: 30,
  contact_emergency_phone: 30,
};

// Mirrors core.validators.PHONE_PATTERN / validate_phone_number on the backend.
const PHONE_PATTERN = /^\+?[\d\s()-]+$/;
function isValidPhone(value) {
  const digitCount = (value.match(/\d/g) || []).length;
  return digitCount >= 7 && PHONE_PATTERN.test(value);
}

// Mirrors Django's URLField (requires an http/https scheme + host).
function isValidUrl(value) {
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:";
  } catch {
    return false;
  }
}

// Mirrors TournamentUpdateSerializer.validate on the backend. `initialForm` is
// the snapshot loaded from the API — a date is only required to be in the
// future if the organizer is actually changing it; an already-started
// tournament must stay editable for its other fields. A still-incomplete
// DRAFT skips the "required" checks entirely (mirrors require_mode_fields on
// the backend) — those are only enforced once the organizer hits Submit.
function getFormErrors(form, initialForm, isOnline, isOffline) {
  const errors = {};
  const isDraft = form.status === "draft";

  if (!form.name.trim()) errors.name = "Tournament name is required.";
  else if (form.name.trim().length < 3) errors.name = "Must be at least 3 characters.";
  else if (form.name.length > MAX_LENGTHS.name) errors.name = `Must be ${MAX_LENGTHS.name} characters or fewer.`;

  if (!form.game) errors.game = "Select a game.";

  if (!isDraft && !String(form.max_participants).trim()) {
    errors.max_participants = "Maximum participants is required.";
  } else if (String(form.max_participants).trim()) {
    const maxP = Number(form.max_participants);
    if (!Number.isInteger(maxP) || maxP < 2) errors.max_participants = "Must be a whole number of at least 2.";
  }

  if (form.registration_fee !== "" && (Number.isNaN(Number(form.registration_fee)) || Number(form.registration_fee) < 0)) {
    errors.registration_fee = "Cannot be negative.";
  }
  if (form.prize_pool !== "" && (Number.isNaN(Number(form.prize_pool)) || Number(form.prize_pool) < 0)) {
    errors.prize_pool = "Cannot be negative.";
  }

  const now = new Date();
  const starts = form.starts_at ? new Date(form.starts_at) : null;
  const ends = form.ends_at ? new Date(form.ends_at) : null;
  const deadline = form.registration_deadline ? new Date(form.registration_deadline) : null;

  if (!isDraft && !form.starts_at) {
    errors.starts_at = "Start date is required.";
  } else if (form.starts_at && form.starts_at !== initialForm.starts_at && starts <= now) {
    errors.starts_at = "Start date must be in the future.";
  }

  if (ends && starts && ends < starts) {
    errors.ends_at = "End date must be on or after the start date.";
  }

  if (deadline) {
    if (form.registration_deadline !== initialForm.registration_deadline && deadline <= now) {
      errors.registration_deadline = "Registration deadline must be in the future.";
    } else if (starts && deadline > starts) {
      errors.registration_deadline = "Registration deadline must be before the tournament starts.";
    }
  }

  if (!isDraft) {
    if (isOffline) {
      if (!form.venue_name.trim()) errors.venue_name = "Venue name is required.";
      if (!form.venue_address.trim()) errors.venue_address = "Full address is required.";
      if (!form.venue_city.trim()) errors.venue_city = "City is required.";
      if (!form.venue_country.trim()) errors.venue_country = "Country is required.";
    }
    if (isOnline && !form.platform.trim()) errors.platform = "Platform is required.";
  }
  if (isOffline && form.venue_map_link.trim() && !isValidUrl(form.venue_map_link.trim())) {
    errors.venue_map_link = "Enter a valid URL (starting with http:// or https://).";
  }

  if (form.contact_email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.contact_email)) {
    errors.contact_email = "Enter a valid email address.";
  }
  if (form.contact_phone.trim() && !isValidPhone(form.contact_phone.trim())) {
    errors.contact_phone = "Enter a valid phone number.";
  }
  if (form.contact_emergency_phone.trim() && !isValidPhone(form.contact_emergency_phone.trim())) {
    errors.contact_emergency_phone = "Enter a valid phone number.";
  }
  ["contact_website", "social_facebook", "social_instagram", "social_discord", "social_youtube"].forEach((key) => {
    if (form[key].trim() && !isValidUrl(form[key].trim())) {
      errors[key] = "Enter a valid URL (starting with http:// or https://).";
    }
  });

  return errors;
}

const EDITABLE_FIELDS = [
  "name", "game", "mode", "bracket_format", "team_size",
  "registration_fee", "prize_pool", "registration_deadline", "starts_at", "ends_at", "max_participants",
  "venue_name", "venue_address", "venue_map_link", "venue_city", "venue_province", "venue_country",
  "venue_parking_available",
  "discord_server", "room_id", "platform",
  "contact_organizer_name", "contact_company_name", "contact_phone", "contact_email",
  "contact_emergency_phone", "contact_website",
  "social_facebook", "social_instagram", "social_discord", "social_youtube",
];

function toLocalInput(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function Field({ label, required = false, error = undefined, children }) {
  return (
    <div>
      <label className="block text-xs font-heading font-bold uppercase tracking-wider text-muted-foreground mb-2">
        {label} {required && <span className="text-destructive">*</span>}
      </label>
      {children}
      {error && <p className="mt-1.5 text-xs text-destructive">{error}</p>}
    </div>
  );
}

const inputClass = "w-full px-3.5 py-2.5 rounded-xl bg-muted/40 border border-border text-sm outline-none focus:border-primary";

function TextInput(props) {
  return <input {...props} className={inputClass} />;
}

function Select({ options, ...props }) {
  return (
    <select {...props} className={inputClass}>
      {options.map((o) => (
        <option key={o.value} value={o.value}>{o.label}</option>
      ))}
    </select>
  );
}

export default function EditTournament() {
  const { id } = useParams();
  const navigate = useNavigate();

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [denied, setDenied] = useState(false);
  const [games, setGames] = useState([]);
  const [form, setForm] = useState(null);
  const [touched, setTouched] = useState({});
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [saved, setSaved] = useState(false);
  const initialFormRef = useRef(null);

  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const [resubmitting, setResubmitting] = useState(false);
  const [resubmitError, setResubmitError] = useState("");
  const [duplicating, setDuplicating] = useState(false);
  const [duplicateError, setDuplicateError] = useState("");

  const [showCancelForm, setShowCancelForm] = useState(false);
  const [cancelReason, setCancelReason] = useState("");
  const [cancelling, setCancelling] = useState(false);
  const [cancelError, setCancelError] = useState("");
  const [cancelNotice, setCancelNotice] = useState("");

  const [showRescheduleForm, setShowRescheduleForm] = useState(false);
  const [rescheduleReason, setRescheduleReason] = useState("");
  const [rescheduleStartsAt, setRescheduleStartsAt] = useState("");
  const [rescheduleEndsAt, setRescheduleEndsAt] = useState("");
  const [rescheduling, setRescheduling] = useState(false);
  const [rescheduleError, setRescheduleError] = useState("");

  useEffect(() => {
    // The component doesn't remount on a client-side navigation between two
    // edit pages (e.g. Duplicate redirecting from one tournament's id to
    // another's) — reset transient per-tournament UI state explicitly so it
    // doesn't leak across that navigation.
    setLoading(true);
    setError("");
    setDenied(false);
    setTouched({});
    setSaved(false);
    setSaveError("");
    setSubmitError("");
    setResubmitError("");
    setDuplicateError("");
    setShowCancelForm(false);
    setCancelReason("");
    setCancelError("");
    setCancelNotice("");
    setShowRescheduleForm(false);
    setRescheduleReason("");
    setRescheduleStartsAt("");
    setRescheduleEndsAt("");
    setRescheduleError("");

    api.get(`/api/tournaments/${id}/`)
      .then((t) => {
        if (!t.can_manage) {
          setDenied(true);
          return;
        }
        const loaded = {
          status: t.status, rejection_reason: t.rejection_reason || "", cancellation_reason: t.cancellation_reason || "",
          name: t.title, game: String(t.game_id), mode: t.mode, bracket_format: t.bracket_format,
          team_size: String(t.team_size),
          registration_fee: String(t.registration_fee ?? "0"), prize_pool: String(t.prize_pool ?? "0"),
          registration_deadline: toLocalInput(t.registration_deadline),
          starts_at: toLocalInput(t.start_date), ends_at: toLocalInput(t.end_date),
          max_participants: String(t.max_participants ?? ""),
          venue_name: t.venue_name || "", venue_address: t.venue_address || "", venue_map_link: t.venue_map_link || "",
          venue_city: t.venue_city || "", venue_province: t.venue_province || "", venue_country: t.venue_country || "",
          venue_parking_available: !!t.venue_parking_available,
          discord_server: t.discord_server || "", room_id: t.room_id || "", platform: t.platform || "",
          contact_organizer_name: t.contact_organizer_name || "", contact_company_name: t.contact_company_name || "",
          contact_phone: t.contact_phone || "", contact_email: t.contact_email || "",
          contact_emergency_phone: t.contact_emergency_phone || "", contact_website: t.contact_website || "",
          social_facebook: t.social_facebook || "", social_instagram: t.social_instagram || "",
          social_discord: t.social_discord || "", social_youtube: t.social_youtube || "",
        };
        setForm(loaded);
        initialFormRef.current = loaded;
      })
      .catch((e) => setError(e.message || "Could not load this tournament."))
      .finally(() => setLoading(false));
    api.get("/api/games/").then(setGames).catch(() => {});
  }, [id]);

  const setField = (key, value) => setForm((f) => ({ ...f, [key]: value }));
  const markTouched = (key) => setTouched((t) => ({ ...t, [key]: true }));

  const isOnline = form?.mode !== "offline";
  const isOffline = form?.mode !== "online";

  const formErrors = form ? getFormErrors(form, initialFormRef.current, isOnline, isOffline) : {};
  const hasFormErrors = Object.keys(formErrors).length > 0;
  const fieldError = (key) => (touched[key] ? formErrors[key] : undefined);

  // Nudge toward valid dates in the picker UI; the actual "already-past-and-
  // unchanged is fine" rule lives in getFormErrors and stays authoritative.
  const minStartValue = toLocalInput(new Date(Date.now() + 60000));
  const minEndValue = form?.starts_at || minStartValue;
  const maxDeadlineValue = form?.starts_at || undefined;

  const submit = async (e) => {
    e.preventDefault();
    if (hasFormErrors) {
      setTouched((t) => ({ ...t, ...Object.fromEntries(Object.keys(formErrors).map((k) => [k, true])) }));
      return;
    }
    setSaving(true);
    setSaveError("");
    setSaved(false);
    try {
      const payload = {};
      EDITABLE_FIELDS.forEach((key) => {
        const value = form[key];
        payload[key] = typeof value === "string" ? value.trim() : value;
      });
      await api.patch(`/api/tournaments/${id}/`, payload);
      setSaved(true);
    } catch (err) {
      setSaveError(flattenApiError(err, "Could not save your changes."));
    } finally {
      setSaving(false);
    }
  };

  const flattenApiError = (err, fallback) => {
    if (err.data && typeof err.data === "object") {
      return Object.entries(err.data).map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(" ") : v}`).join(" — ");
    }
    return err.message || fallback;
  };

  const submitForApproval = async () => {
    setSubmitting(true);
    setSubmitError("");
    try {
      const updated = await api.post(`/api/tournaments/${id}/submit/`);
      setForm((f) => ({ ...f, status: updated.status }));
    } catch (err) {
      setSubmitError(flattenApiError(err, "Could not submit for approval."));
    } finally {
      setSubmitting(false);
    }
  };

  const resubmit = async () => {
    setResubmitting(true);
    setResubmitError("");
    try {
      const updated = await api.post(`/api/tournaments/${id}/resubmit/`);
      setForm((f) => ({ ...f, status: updated.status, rejection_reason: "" }));
    } catch (err) {
      setResubmitError(flattenApiError(err, "Could not resubmit."));
    } finally {
      setResubmitting(false);
    }
  };

  const duplicate = async () => {
    setDuplicating(true);
    setDuplicateError("");
    try {
      const copy = await api.post(`/api/tournaments/${id}/duplicate/`);
      navigate(`/tournaments/${copy.id}/edit`);
    } catch (err) {
      setDuplicateError(flattenApiError(err, "Could not duplicate this tournament."));
      setDuplicating(false);
    }
  };

  const cancelTournament = async () => {
    setCancelling(true);
    setCancelError("");
    setCancelNotice("");
    try {
      const resp = await api.post(`/api/tournaments/${id}/cancel/`, { reason: cancelReason });
      if (resp.status === "cancelled") {
        setForm((f) => ({ ...f, status: resp.status, cancellation_reason: resp.cancellation_reason || cancelReason }));
        setShowCancelForm(false);
      } else {
        // Has existing registrations/a bracket — the backend filed an
        // AdminReviewRequest instead of cancelling immediately.
        setCancelNotice(resp.detail);
        setShowCancelForm(false);
      }
    } catch (err) {
      setCancelError(flattenApiError(err, "Could not cancel this tournament."));
    } finally {
      setCancelling(false);
    }
  };

  const rescheduleTournament = async () => {
    setRescheduling(true);
    setRescheduleError("");
    try {
      const updated = await api.post(`/api/tournaments/${id}/reschedule/`, {
        reason: rescheduleReason,
        starts_at: rescheduleStartsAt,
        ends_at: rescheduleEndsAt || undefined,
      });
      setForm((f) => ({ ...f, starts_at: toLocalInput(updated.start_date), ends_at: toLocalInput(updated.end_date) }));
      initialFormRef.current = { ...initialFormRef.current, starts_at: toLocalInput(updated.start_date), ends_at: toLocalInput(updated.end_date) };
      setShowRescheduleForm(false);
      setRescheduleReason("");
      setRescheduleStartsAt("");
      setRescheduleEndsAt("");
    } catch (err) {
      setRescheduleError(flattenApiError(err, "Could not reschedule this tournament."));
    } finally {
      setRescheduling(false);
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center py-20 text-muted-foreground">
        <Loader2 className="w-6 h-6 animate-spin" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-lg mx-auto px-4 py-16 text-center">
        <p className="text-sm text-destructive bg-destructive/10 border border-destructive/30 rounded-lg px-3 py-2 inline-block">{error}</p>
      </div>
    );
  }

  if (denied) {
    return (
      <div className="max-w-lg mx-auto px-4 py-16 text-center">
        <h1 className="font-display font-bold text-2xl mb-2">Not allowed</h1>
        <p className="text-sm text-muted-foreground mb-6">You can only amend tournaments you organize.</p>
        <Link to="/my-tournaments" className="text-primary hover:underline text-sm">Back to My Tournaments</Link>
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto px-4 sm:px-6 py-12 sm:py-16">
      <Link to="/my-tournaments" className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground mb-4">
        <ArrowLeft className="w-3.5 h-3.5" /> Back to My Tournaments
      </Link>
      <h1 className="font-display font-extrabold text-3xl gradient-text mb-1">Amend Tournament</h1>
      <p className="text-sm text-muted-foreground mb-4">Update the details below and save your changes.</p>

      {(() => {
        const meta = STATUS_META[form.status] || STATUS_META.draft;
        return (
          <span className={`inline-flex items-center gap-1.5 text-xs font-heading font-bold uppercase tracking-wider px-2.5 py-1 rounded-full ${meta.className}`}>
            <meta.icon className="w-3.5 h-3.5" /> {meta.label}
          </span>
        );
      })()}
      {form.status === "rejected" && form.rejection_reason && (
        <p className="text-xs text-destructive mt-2">Reason: {form.rejection_reason}</p>
      )}
      {form.status === "cancelled" && form.cancellation_reason && (
        <p className="text-xs text-destructive mt-2">Reason: {form.cancellation_reason}</p>
      )}

      <div className="flex flex-wrap items-center gap-2 mt-4 mb-6">
        <Link
          to={`/tournaments/${id}`}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-heading font-semibold bg-muted hover:bg-muted/70"
        >
          <Eye className="w-3.5 h-3.5" /> Preview
        </Link>
        {form.status === "draft" && (
          <button
            type="button" onClick={submitForApproval} disabled={submitting}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-heading font-semibold bg-primary text-primary-foreground disabled:opacity-50"
          >
            {submitting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Send className="w-3.5 h-3.5" />}
            Submit for Approval
          </button>
        )}
        {form.status === "rejected" && (
          <button
            type="button" onClick={resubmit} disabled={resubmitting}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-heading font-semibold bg-primary text-primary-foreground disabled:opacity-50"
          >
            {resubmitting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RotateCcw className="w-3.5 h-3.5" />}
            Resubmit
          </button>
        )}
        {["pending", "approved"].includes(form.status) && (
          <button
            type="button" onClick={() => setShowRescheduleForm((s) => !s)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-heading font-semibold bg-muted hover:bg-muted/70"
          >
            <CalendarClock className="w-3.5 h-3.5" /> Reschedule
          </button>
        )}
        {form.status !== "cancelled" && (
          <button
            type="button" onClick={duplicate} disabled={duplicating}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-heading font-semibold bg-muted hover:bg-muted/70 disabled:opacity-50"
          >
            {duplicating ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Copy className="w-3.5 h-3.5" />}
            Duplicate
          </button>
        )}
        {["draft", "pending", "approved"].includes(form.status) && (
          <button
            type="button" onClick={() => setShowCancelForm((s) => !s)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-heading font-semibold text-destructive/80 hover:text-destructive"
          >
            <Ban className="w-3.5 h-3.5" /> Cancel Tournament
          </button>
        )}
      </div>

      {submitError && <p className="text-xs text-destructive mb-4">{submitError}</p>}
      {resubmitError && <p className="text-xs text-destructive mb-4">{resubmitError}</p>}
      {duplicateError && <p className="text-xs text-destructive mb-4">{duplicateError}</p>}
      {cancelNotice && (
        <div className="mb-6 text-sm text-accent bg-accent/10 border border-accent/30 rounded-lg px-3 py-2">{cancelNotice}</div>
      )}

      {showCancelForm && (
        <div className="mb-6 glass rounded-xl border border-destructive/30 p-4 space-y-3">
          <p className="text-sm font-heading font-bold text-destructive">Cancel this tournament</p>
          <textarea
            required
            value={cancelReason}
            onChange={(e) => setCancelReason(e.target.value)}
            placeholder="Why are you cancelling this tournament?"
            rows={3}
            className="w-full px-3.5 py-2.5 rounded-xl bg-muted/40 border border-border text-sm outline-none focus:border-destructive"
          />
          {cancelError && <p className="text-xs text-destructive">{cancelError}</p>}
          <div className="flex gap-2">
            <button
              type="button" onClick={cancelTournament} disabled={cancelling || !cancelReason.trim()}
              className="px-3 py-1.5 rounded-lg text-xs font-heading font-semibold bg-destructive text-destructive-foreground disabled:opacity-50"
            >
              {cancelling ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : "Confirm Cancellation"}
            </button>
            <button
              type="button"
              onClick={() => { setShowCancelForm(false); setCancelError(""); }}
              disabled={cancelling}
              className="px-3 py-1.5 rounded-lg text-xs font-heading font-semibold bg-muted disabled:opacity-50"
            >
              Back
            </button>
          </div>
        </div>
      )}

      {showRescheduleForm && (
        <div className="mb-6 glass rounded-xl border border-border/60 p-4 space-y-3">
          <p className="text-sm font-heading font-bold">Reschedule this tournament</p>
          <div className="grid grid-cols-2 gap-3">
            <DateTimePicker
              min={minStartValue}
              value={rescheduleStartsAt}
              onChange={setRescheduleStartsAt}
              placeholder="New start date"
            />
            <DateTimePicker
              min={rescheduleStartsAt || minStartValue}
              value={rescheduleEndsAt}
              onChange={setRescheduleEndsAt}
              placeholder="New end date (optional)"
            />
          </div>
          <textarea
            required
            value={rescheduleReason}
            onChange={(e) => setRescheduleReason(e.target.value)}
            placeholder="Reason for rescheduling — registered players will be emailed this."
            rows={2}
            className="w-full px-3.5 py-2.5 rounded-xl bg-muted/40 border border-border text-sm outline-none focus:border-primary"
          />
          {rescheduleError && <p className="text-xs text-destructive">{rescheduleError}</p>}
          <div className="flex gap-2">
            <button
              type="button" onClick={rescheduleTournament}
              disabled={rescheduling || !rescheduleStartsAt || !rescheduleReason.trim()}
              className="px-3 py-1.5 rounded-lg text-xs font-heading font-semibold bg-primary text-primary-foreground disabled:opacity-50"
            >
              {rescheduling ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : "Confirm Reschedule"}
            </button>
            <button
              type="button" onClick={() => setShowRescheduleForm(false)} disabled={rescheduling}
              className="px-3 py-1.5 rounded-lg text-xs font-heading font-semibold bg-muted disabled:opacity-50"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      <form onSubmit={submit} className="glass rounded-2xl border border-border/60 p-6 sm:p-8 space-y-6">
        <div className="space-y-4">
          <h3 className="font-heading font-bold text-sm">Tournament Details</h3>
          <Field label="Tournament name" required error={fieldError("name")}>
            <TextInput maxLength={MAX_LENGTHS.name} value={form.name} onChange={(e) => setField("name", e.target.value)} onBlur={() => markTouched("name")} />
          </Field>
          <Field label="Game" required error={fieldError("game")}>
            <Select
              value={form.game}
              onChange={(e) => { setField("game", e.target.value); markTouched("game"); }}
              options={games.map((g) => ({ value: String(g.id), label: g.name }))}
            />
          </Field>
          <div className="grid grid-cols-2 gap-4">
            <Field label="Mode" required>
              <Select value={form.mode} onChange={(e) => setField("mode", e.target.value)} options={MODES} />
            </Field>
            <Field label="Bracket type" required>
              <Select value={form.bracket_format} onChange={(e) => setField("bracket_format", e.target.value)} options={BRACKET_FORMATS} />
            </Field>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <Field label="Maximum participants" required error={fieldError("max_participants")}>
              <TextInput
                type="number"
                min="2"
                step="1"
                value={form.max_participants}
                onChange={(e) => setField("max_participants", e.target.value)}
                onBlur={() => markTouched("max_participants")}
              />
              <p className="mt-1.5 text-[11px] text-muted-foreground">
                Registration slots — one per {form.team_size === "1" ? "player" : "team"}, not raw player count.
              </p>
            </Field>
            <Field label="Team size" required>
              <Select
                value={form.team_size}
                onChange={(e) => setField("team_size", e.target.value)}
                options={[1, 2, 3, 4, 5].map((n) => ({ value: String(n), label: String(n) }))}
              />
            </Field>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <Field label="Registration fee (PKR)" error={fieldError("registration_fee")}>
              <TextInput type="number" min="0" value={form.registration_fee} onChange={(e) => setField("registration_fee", e.target.value)} onBlur={() => markTouched("registration_fee")} />
            </Field>
            <Field label="Prize pool (PKR)" error={fieldError("prize_pool")}>
              <TextInput type="number" min="0" value={form.prize_pool} onChange={(e) => setField("prize_pool", e.target.value)} onBlur={() => markTouched("prize_pool")} />
            </Field>
          </div>
          <Field label="Registration deadline" error={fieldError("registration_deadline")}>
            <DateTimePicker
              min={minStartValue}
              max={maxDeadlineValue}
              value={form.registration_deadline}
              onChange={(v) => setField("registration_deadline", v)}
              onBlur={() => markTouched("registration_deadline")}
            />
          </Field>
          <div className="grid grid-cols-2 gap-4">
            <Field label="Tournament start date" required error={fieldError("starts_at")}>
              <DateTimePicker
                min={minStartValue}
                value={form.starts_at}
                onChange={(v) => setField("starts_at", v)}
                onBlur={() => markTouched("starts_at")}
              />
            </Field>
            <Field label="Tournament end date" error={fieldError("ends_at")}>
              <DateTimePicker
                min={minEndValue}
                value={form.ends_at}
                onChange={(v) => setField("ends_at", v)}
                onBlur={() => markTouched("ends_at")}
              />
            </Field>
          </div>
        </div>

        {isOffline && (
          <div className="space-y-4 pt-4 border-t border-border/60">
            <h3 className="font-heading font-bold text-sm">Venue</h3>
            <Field label="Venue name" required error={fieldError("venue_name")}>
              <TextInput maxLength={MAX_LENGTHS.venue_name} value={form.venue_name} onChange={(e) => setField("venue_name", e.target.value)} onBlur={() => markTouched("venue_name")} />
            </Field>
            <Field label="Full address" required error={fieldError("venue_address")}>
              <TextInput value={form.venue_address} onChange={(e) => setField("venue_address", e.target.value)} onBlur={() => markTouched("venue_address")} />
            </Field>
            <Field label="Google Maps link" error={fieldError("venue_map_link")}>
              <TextInput value={form.venue_map_link} onChange={(e) => setField("venue_map_link", e.target.value)} onBlur={() => markTouched("venue_map_link")} />
            </Field>
            <div className="grid grid-cols-2 gap-4">
              <Field label="City" required error={fieldError("venue_city")}>
                <TextInput maxLength={MAX_LENGTHS.venue_city} value={form.venue_city} onChange={(e) => setField("venue_city", e.target.value)} onBlur={() => markTouched("venue_city")} />
              </Field>
              <Field label="Province">
                <TextInput maxLength={MAX_LENGTHS.venue_province} value={form.venue_province} onChange={(e) => setField("venue_province", e.target.value)} />
              </Field>
            </div>
            <Field label="Country" required error={fieldError("venue_country")}>
              <TextInput maxLength={MAX_LENGTHS.venue_country} value={form.venue_country} onChange={(e) => setField("venue_country", e.target.value)} onBlur={() => markTouched("venue_country")} />
            </Field>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={form.venue_parking_available} onChange={(e) => setField("venue_parking_available", e.target.checked)} />
              Parking available?
            </label>
          </div>
        )}

        {isOnline && (
          <div className="space-y-4 pt-4 border-t border-border/60">
            <h3 className="font-heading font-bold text-sm">Online details</h3>
            <Field label="Discord server">
              <TextInput maxLength={MAX_LENGTHS.discord_server} value={form.discord_server} onChange={(e) => setField("discord_server", e.target.value)} />
            </Field>
            <Field label="Room ID">
              <TextInput maxLength={MAX_LENGTHS.room_id} value={form.room_id} onChange={(e) => setField("room_id", e.target.value)} />
            </Field>
            <Field label="Platform" required error={fieldError("platform")}>
              <TextInput
                list="platform-suggestions"
                maxLength={MAX_LENGTHS.platform}
                value={form.platform}
                onChange={(e) => setField("platform", e.target.value)}
                onBlur={() => markTouched("platform")}
              />
              <datalist id="platform-suggestions">
                {PLATFORM_SUGGESTIONS.map((p) => <option key={p} value={p} />)}
              </datalist>
            </Field>
          </div>
        )}

        <div className="space-y-4 pt-4 border-t border-border/60">
          <h3 className="font-heading font-bold text-sm">Contact Details</h3>
          <Field label="Organizer name">
            <TextInput maxLength={MAX_LENGTHS.contact_organizer_name} value={form.contact_organizer_name} onChange={(e) => setField("contact_organizer_name", e.target.value)} />
          </Field>
          <Field label="Company name">
            <TextInput maxLength={MAX_LENGTHS.contact_company_name} value={form.contact_company_name} onChange={(e) => setField("contact_company_name", e.target.value)} />
          </Field>
          <div className="grid grid-cols-2 gap-4">
            <Field label="Phone number" error={fieldError("contact_phone")}>
              <TextInput
                type="tel"
                maxLength={MAX_LENGTHS.contact_phone}
                value={form.contact_phone}
                onChange={(e) => setField("contact_phone", e.target.value)}
                onBlur={() => markTouched("contact_phone")}
              />
            </Field>
            <Field label="Email" error={fieldError("contact_email")}>
              <TextInput type="email" value={form.contact_email} onChange={(e) => setField("contact_email", e.target.value)} onBlur={() => markTouched("contact_email")} />
            </Field>
          </div>
          <Field label="Emergency contact" error={fieldError("contact_emergency_phone")}>
            <TextInput
              type="tel"
              maxLength={MAX_LENGTHS.contact_emergency_phone}
              value={form.contact_emergency_phone}
              onChange={(e) => setField("contact_emergency_phone", e.target.value)}
              onBlur={() => markTouched("contact_emergency_phone")}
            />
          </Field>
          <Field label="Website (optional)" error={fieldError("contact_website")}>
            <TextInput value={form.contact_website} onChange={(e) => setField("contact_website", e.target.value)} onBlur={() => markTouched("contact_website")} />
          </Field>
          <div className="grid grid-cols-2 gap-4">
            <Field label="Facebook" error={fieldError("social_facebook")}>
              <TextInput value={form.social_facebook} onChange={(e) => setField("social_facebook", e.target.value)} onBlur={() => markTouched("social_facebook")} />
            </Field>
            <Field label="Instagram" error={fieldError("social_instagram")}>
              <TextInput value={form.social_instagram} onChange={(e) => setField("social_instagram", e.target.value)} onBlur={() => markTouched("social_instagram")} />
            </Field>
            <Field label="Discord" error={fieldError("social_discord")}>
              <TextInput value={form.social_discord} onChange={(e) => setField("social_discord", e.target.value)} onBlur={() => markTouched("social_discord")} />
            </Field>
            <Field label="YouTube" error={fieldError("social_youtube")}>
              <TextInput value={form.social_youtube} onChange={(e) => setField("social_youtube", e.target.value)} onBlur={() => markTouched("social_youtube")} />
            </Field>
          </div>
        </div>

        {saveError && (
          <div className="text-sm text-destructive bg-destructive/10 border border-destructive/30 rounded-lg px-3 py-2">{saveError}</div>
        )}
        {saved && (
          <div className="flex items-center gap-2 text-sm text-primary bg-primary/10 border border-primary/30 rounded-lg px-3 py-2">
            <CheckCircle2 className="w-4 h-4" /> Changes saved.
          </div>
        )}

        <div className="flex justify-end pt-2">
          <button
            type="submit"
            disabled={saving}
            className="inline-flex items-center gap-2 px-6 py-3 rounded-xl font-heading font-bold text-sm bg-primary text-primary-foreground hover:shadow-[0_0_28px_hsl(186_100%_50%/0.5)] transition-shadow disabled:opacity-50"
          >
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
            Save Changes
          </button>
        </div>
      </form>
    </div>
  );
}
