import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Loader2, ArrowRight, ArrowLeft, Clock, Upload, FileCheck2,
} from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/appauth";
import DateTimePicker from "@/components/tournaments/DateTimePicker";

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

const STEPS = ["Tournament Details", "Venue / Online", "Contact Details", "Documents", "Review & Submit"];

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

// Mirrors core.validators.validate_document_file on the backend (10MB, JPEG/PNG/PDF).
const MAX_DOCUMENT_SIZE = 10 * 1024 * 1024;
const ALLOWED_DOCUMENT_TYPES = ["image/jpeg", "image/png", "application/pdf"];
function getFileError(file) {
  if (!file) return null;
  if (file.size > MAX_DOCUMENT_SIZE) return "File must be smaller than 10MB.";
  if (!ALLOWED_DOCUMENT_TYPES.includes(file.type)) return "Only JPEG, PNG, or PDF files are allowed.";
  return null;
}

const pad2 = (n) => String(n).padStart(2, "0");

// datetime-local inputs are local-time strings (YYYY-MM-DDTHH:mm); Date's own
// toISOString() would shift by timezone offset, so build the string manually.
function toLocalDatetimeValue(date) {
  return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}T${pad2(date.getHours())}:${pad2(date.getMinutes())}`;
}

function getStepErrors(step, form, isOnline, isOffline, files) {
  const errors = {};

  if (step === 0) {
    if (!form.name.trim()) errors.name = "Tournament name is required.";
    else if (form.name.trim().length < 3) errors.name = "Must be at least 3 characters.";
    else if (form.name.length > MAX_LENGTHS.name) errors.name = `Must be ${MAX_LENGTHS.name} characters or fewer.`;

    if (!form.game) errors.game = "Select a game.";

    if (!String(form.max_participants).trim()) {
      errors.max_participants = "Maximum participants is required.";
    } else {
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

    if (!form.starts_at) {
      errors.starts_at = "Start date is required.";
    } else if (starts <= now) {
      errors.starts_at = "Start date must be in the future.";
    }

    if (ends && starts && ends < starts) {
      errors.ends_at = "End date must be on or after the start date.";
    }

    if (deadline) {
      if (deadline <= now) errors.registration_deadline = "Registration deadline must be in the future.";
      else if (starts && deadline > starts) errors.registration_deadline = "Registration deadline must be before the tournament starts.";
    }
  }

  if (step === 1) {
    if (isOffline) {
      if (!form.venue_name.trim()) errors.venue_name = "Venue name is required.";
      if (!form.venue_address.trim()) errors.venue_address = "Full address is required.";
      if (!form.venue_city.trim()) errors.venue_city = "City is required.";
      if (!form.venue_country.trim()) errors.venue_country = "Country is required.";
      if (form.venue_map_link.trim() && !isValidUrl(form.venue_map_link.trim())) {
        errors.venue_map_link = "Enter a valid URL (starting with http:// or https://).";
      }
    }
    if (isOnline && !form.platform.trim()) errors.platform = "Platform is required.";
  }

  if (step === 2) {
    if (form.contact_email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.contact_email)) {
      errors.contact_email = "Enter a valid email address.";
    }
    if (form.contact_phone.trim() && !isValidPhone(form.contact_phone.trim())) {
      errors.contact_phone = "Enter a valid phone number.";
    }
    if (form.contact_emergency_phone.trim() && !isValidPhone(form.contact_emergency_phone.trim())) {
      errors.contact_emergency_phone = "Enter a valid phone number.";
    }
    [
      ["contact_website", "Website"],
      ["social_facebook", "Facebook"],
      ["social_instagram", "Instagram"],
      ["social_discord", "Discord"],
      ["social_youtube", "YouTube"],
    ].forEach(([key]) => {
      if (form[key].trim() && !isValidUrl(form[key].trim())) {
        errors[key] = "Enter a valid URL (starting with http:// or https://).";
      }
    });
  }

  if (step === 3) {
    if (!files.company_registration_certificate) errors.company_registration_certificate = "Required.";
    if (!files.organizer_cnic_front) errors.organizer_cnic_front = "Required.";
    if (!files.organizer_cnic_back) errors.organizer_cnic_back = "Required.";
    Object.entries(files).forEach(([key, file]) => {
      const fileErr = getFileError(file);
      if (fileErr) errors[key] = fileErr;
    });
  }

  return errors;
}

const initialForm = {
  name: "", game: "", mode: "online", bracket_format: "single",
  max_participants: "", team_size: "1",
  registration_fee: "0", prize_pool: "0",
  registration_deadline: "", starts_at: "", ends_at: "",
  venue_name: "", venue_address: "", venue_map_link: "", venue_city: "", venue_province: "", venue_country: "",
  venue_parking_available: false,
  discord_server: "", room_id: "", platform: "",
  contact_organizer_name: "", contact_company_name: "", contact_phone: "", contact_email: "",
  contact_emergency_phone: "", contact_website: "",
  social_facebook: "", social_instagram: "", social_discord: "", social_youtube: "",
};

const initialFiles = {
  company_registration_certificate: null,
  business_license: null,
  organizer_cnic_front: null,
  organizer_cnic_back: null,
  tax_certificate: null,
  sponsor_agreement: null,
};

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

function TextArea(props) {
  return <textarea {...props} rows={3} className={inputClass} />;
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

function FileInput({ label, file, onChange, required = false, error = undefined }) {
  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <label className="block text-xs font-heading font-bold uppercase tracking-wider text-muted-foreground">
          {label} {required && <span className="text-destructive">*</span>}
        </label>
        {file && (
          <span className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full bg-primary/10 text-primary">
            <FileCheck2 className="w-3 h-3" /> Selected
          </span>
        )}
      </div>
      <input
        type="file"
        accept=".jpg,.jpeg,.png,.pdf,image/jpeg,image/png,application/pdf"
        onChange={(e) => onChange(e.target.files?.[0] || null)}
        className="w-full text-xs text-muted-foreground file:mr-3 file:px-3 file:py-1.5 file:rounded-lg file:border-0 file:bg-primary file:text-primary-foreground file:text-xs file:font-heading file:font-semibold"
      />
      {error && <p className="mt-1.5 text-xs text-destructive">{error}</p>}
    </div>
  );
}

export default function CreateTournament() {
  const navigate = useNavigate();
  const { user } = useAuth();

  const [games, setGames] = useState([]);
  const [step, setStep] = useState(0);
  const [form, setForm] = useState(initialForm);
  const [files, setFiles] = useState(initialFiles);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [touched, setTouched] = useState({});

  // Reaching this page at all requires an approved organizer profile — enforced
  // by the <OrganizerOrAdminRoute requireOrganizer> route guard in App.jsx.
  useEffect(() => {
    api.get("/api/games/").then(setGames).catch(() => {});
    api.get("/api/organizer/dashboard/").then((profile) => {
      setForm((f) => ({
        ...f,
        contact_organizer_name: [user?.first_name, user?.last_name].filter(Boolean).join(" "),
        contact_company_name: profile.company_name || "",
        contact_phone: profile.phone_number || "",
        contact_email: user?.email || "",
      }));
    }).catch(() => {});
  }, [user]);

  const setField = (key, value) => setForm((f) => ({ ...f, [key]: value }));
  const markTouched = (key) => setTouched((t) => ({ ...t, [key]: true }));
  const setFile = (key, value) => { setFiles((f) => ({ ...f, [key]: value })); markTouched(key); };
  const fieldError = (key) => (touched[key] ? stepErrors[key] : undefined);

  const isOnline = form.mode !== "offline";
  const isOffline = form.mode !== "online";

  const stepErrors = getStepErrors(step, form, isOnline, isOffline, files);
  const hasStepErrors = Object.keys(stepErrors).length > 0;

  // Passed to DateTimePicker as `min` so it disables past days in the calendar popup.
  const minStartValue = toLocalDatetimeValue(new Date(Date.now() + 60000));
  const minEndValue = form.starts_at || minStartValue;
  const maxDeadlineValue = form.starts_at || undefined;

  const goNext = () => {
    if (hasStepErrors) {
      setTouched((t) => ({ ...t, ...Object.fromEntries(Object.keys(stepErrors).map((k) => [k, true])) }));
      return;
    }
    setStep((s) => Math.min(STEPS.length - 1, s + 1));
  };

  const submit = async () => {
    if (hasStepErrors) {
      setTouched((t) => ({ ...t, ...Object.fromEntries(Object.keys(stepErrors).map((k) => [k, true])) }));
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      const formData = new FormData();
      Object.entries(form).forEach(([key, value]) => {
        if (value === "" || value === null || value === undefined) return;
        const stringValue = typeof value === "string" ? value.trim() : String(value);
        if (stringValue === "") return;
        formData.append(key, stringValue);
      });
      Object.entries(files).forEach(([key, file]) => {
        if (file) formData.append(key, file);
      });
      await api.post("/api/tournaments/", formData, { formData: true });
      setSubmitted(true);
    } catch (err) {
      let msg = err.message || "Could not submit your tournament.";
      if (err.data && typeof err.data === "object") {
        msg = Object.entries(err.data).map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(" ") : v}`).join(" — ");
      }
      setError(msg);
    } finally {
      setSubmitting(false);
    }
  };

  if (submitted) {
    return (
      <div className="max-w-lg mx-auto px-4 py-20 text-center">
        <div className="w-16 h-16 rounded-2xl mx-auto grid place-items-center mb-6 bg-gradient-to-br from-primary to-green-500 neon-border">
          <Clock className="w-8 h-8 text-background" strokeWidth={2} />
        </div>
        <h1 className="font-display font-extrabold text-3xl mb-3 gradient-text">Submitted!</h1>
        <p className="text-muted-foreground mb-8">
          Your tournament has been submitted and is <strong>Pending Admin Approval</strong>. Once approved, it will
          appear on the public tournaments list for players to register.
        </p>
        <button
          onClick={() => navigate("/tournaments")}
          className="inline-flex items-center gap-2 px-6 py-3 rounded-xl font-heading font-bold text-base bg-primary text-primary-foreground"
        >
          Back to tournaments <ArrowRight className="w-4 h-4" />
        </button>
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto px-4 sm:px-6 py-12 sm:py-16">
      <h1 className="font-display font-extrabold text-3xl gradient-text mb-1">Create Tournament</h1>
      <p className="text-sm text-muted-foreground mb-6">Step {step + 1} of {STEPS.length}: {STEPS[step]}</p>

      <div className="flex gap-1.5 mb-8">
        {STEPS.map((label, i) => (
          <div key={label} className={`h-1.5 flex-1 rounded-full ${i <= step ? "bg-primary" : "bg-muted"}`} />
        ))}
      </div>

      <div className="glass rounded-2xl border border-border/60 p-6 sm:p-8 space-y-4">
        {step === 0 && (
          <>
            <Field label="Tournament name" required error={fieldError("name")}>
              <TextInput
                value={form.name}
                maxLength={MAX_LENGTHS.name}
                onChange={(e) => setField("name", e.target.value)}
                onBlur={() => markTouched("name")}
                placeholder="e.g. Winter Cup 2026"
              />
            </Field>
            <Field label="Game" required error={fieldError("game")}>
              <Select
                value={form.game}
                onChange={(e) => { setField("game", e.target.value); markTouched("game"); }}
                options={[{ value: "", label: "Select a game" }, ...games.map((g) => ({ value: g.id, label: g.name }))]}
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
                  placeholder="e.g. 64"
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
                <TextInput
                  type="number"
                  min="0"
                  value={form.registration_fee}
                  onChange={(e) => setField("registration_fee", e.target.value)}
                  onBlur={() => markTouched("registration_fee")}
                />
              </Field>
              <Field label="Prize pool (PKR)" error={fieldError("prize_pool")}>
                <TextInput
                  type="number"
                  min="0"
                  value={form.prize_pool}
                  onChange={(e) => setField("prize_pool", e.target.value)}
                  onBlur={() => markTouched("prize_pool")}
                />
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
          </>
        )}

        {step === 1 && (
          <>
            {isOffline && (
              <div className="space-y-4 pb-4 border-b border-border/60">
                <h3 className="font-heading font-bold text-sm">Venue</h3>
                <Field label="Venue name" required error={fieldError("venue_name")}>
                  <TextInput maxLength={MAX_LENGTHS.venue_name} value={form.venue_name} onChange={(e) => setField("venue_name", e.target.value)} onBlur={() => markTouched("venue_name")} />
                </Field>
                <Field label="Full address" required error={fieldError("venue_address")}>
                  <TextArea value={form.venue_address} onChange={(e) => setField("venue_address", e.target.value)} onBlur={() => markTouched("venue_address")} />
                </Field>
                <Field label="Google Maps link" error={fieldError("venue_map_link")}>
                  <TextInput
                    value={form.venue_map_link}
                    onChange={(e) => setField("venue_map_link", e.target.value)}
                    onBlur={() => markTouched("venue_map_link")}
                    placeholder="https://maps.google.com/..."
                  />
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
                  <input
                    type="checkbox"
                    checked={form.venue_parking_available}
                    onChange={(e) => setField("venue_parking_available", e.target.checked)}
                  />
                  Parking available?
                </label>
              </div>
            )}
            {isOnline && (
              <div className="space-y-4">
                <h3 className="font-heading font-bold text-sm">Online details</h3>
                <Field label="Discord server">
                  <TextInput maxLength={MAX_LENGTHS.discord_server} value={form.discord_server} onChange={(e) => setField("discord_server", e.target.value)} placeholder="https://discord.gg/..." />
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
                    placeholder="e.g. Steam, Riot, FACEIT, Battle.net"
                  />
                  <datalist id="platform-suggestions">
                    {PLATFORM_SUGGESTIONS.map((p) => <option key={p} value={p} />)}
                  </datalist>
                </Field>
              </div>
            )}
          </>
        )}

        {step === 2 && (
          <>
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
              <TextInput
                value={form.contact_website}
                onChange={(e) => setField("contact_website", e.target.value)}
                onBlur={() => markTouched("contact_website")}
                placeholder="https://..."
              />
            </Field>
            <div className="pt-2 border-t border-border/60 space-y-4">
              <h3 className="font-heading font-bold text-sm">Social media (optional)</h3>
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
          </>
        )}

        {step === 3 && (
          <>
            <FileInput label="Company Registration Certificate" required file={files.company_registration_certificate} onChange={(f) => setFile("company_registration_certificate", f)} error={fieldError("company_registration_certificate")} />
            <FileInput label="Business License" file={files.business_license} onChange={(f) => setFile("business_license", f)} error={fieldError("business_license")} />
            <FileInput label="Organizer CNIC Front" required file={files.organizer_cnic_front} onChange={(f) => setFile("organizer_cnic_front", f)} error={fieldError("organizer_cnic_front")} />
            <FileInput label="Organizer CNIC Back" required file={files.organizer_cnic_back} onChange={(f) => setFile("organizer_cnic_back", f)} error={fieldError("organizer_cnic_back")} />
            <FileInput label="Tax Certificate" file={files.tax_certificate} onChange={(f) => setFile("tax_certificate", f)} error={fieldError("tax_certificate")} />
            <FileInput label="Sponsor Agreement" file={files.sponsor_agreement} onChange={(f) => setFile("sponsor_agreement", f)} error={fieldError("sponsor_agreement")} />
          </>
        )}

        {step === 4 && (
          <div className="space-y-3 text-sm">
            <p className="text-muted-foreground">
              Review your submission, then submit. Your tournament will be <strong>Pending Admin Approval</strong> until
              reviewed — it won't be visible to players until then.
            </p>
            <div className="rounded-xl bg-muted/30 border border-border/60 p-4 space-y-1">
              <p><span className="text-muted-foreground">Name:</span> {form.name || "—"}</p>
              <p><span className="text-muted-foreground">Mode:</span> {form.mode}</p>
              <p><span className="text-muted-foreground">Bracket:</span> {BRACKET_FORMATS.find((b) => b.value === form.bracket_format)?.label}</p>
              <p><span className="text-muted-foreground">Max participants:</span> {form.max_participants || "—"}</p>
              <p><span className="text-muted-foreground">Team size:</span> {form.team_size}</p>
              <p><span className="text-muted-foreground">Registration fee:</span> PKR {form.registration_fee || 0}</p>
              <p><span className="text-muted-foreground">Prize pool:</span> PKR {form.prize_pool || 0}</p>
            </div>
          </div>
        )}

        {error && (
          <div className="text-sm text-destructive bg-destructive/10 border border-destructive/30 rounded-lg px-3 py-2">
            {error}
          </div>
        )}

        <div className="flex justify-between pt-2">
          <button
            onClick={() => setStep((s) => Math.max(0, s - 1))}
            disabled={step === 0}
            className="inline-flex items-center gap-1.5 px-4 py-2.5 rounded-xl text-sm font-heading font-semibold bg-muted disabled:opacity-40"
          >
            <ArrowLeft className="w-4 h-4" /> Back
          </button>
          {step < STEPS.length - 1 ? (
            <button
              onClick={goNext}
              className="inline-flex items-center gap-1.5 px-5 py-2.5 rounded-xl text-sm font-heading font-bold bg-primary text-primary-foreground"
            >
              Next <ArrowRight className="w-4 h-4" />
            </button>
          ) : (
            <button
              onClick={submit}
              disabled={submitting}
              className="inline-flex items-center gap-1.5 px-5 py-2.5 rounded-xl text-sm font-heading font-bold bg-primary text-primary-foreground disabled:opacity-50"
            >
              {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
              Submit
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
