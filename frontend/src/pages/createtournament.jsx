import React, { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import {
  Loader2, ArrowRight, ArrowLeft, Trophy, CheckCircle2, Clock, XCircle, Upload, FileCheck2,
} from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/appauth";

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

function Field({ label, required, children }) {
  return (
    <div>
      <label className="block text-xs font-heading font-bold uppercase tracking-wider text-muted-foreground mb-2">
        {label} {required && <span className="text-destructive">*</span>}
      </label>
      {children}
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

function FileInput({ label, file, onChange, required }) {
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
        onChange={(e) => onChange(e.target.files?.[0] || null)}
        className="w-full text-xs text-muted-foreground file:mr-3 file:px-3 file:py-1.5 file:rounded-lg file:border-0 file:bg-primary file:text-primary-foreground file:text-xs file:font-heading file:font-semibold"
      />
    </div>
  );
}

function OrganizerGate({ status }) {
  const copy = {
    null: "You need to become an approved organizer before you can create a tournament.",
    pending: "Your organizer application is still under review. You'll be able to create tournaments once it's approved.",
    rejected: "Your organizer application was rejected, so you can't create tournaments right now.",
    error: "Could not check your organizer status. Please try again shortly.",
  }[status ?? "null"];

  return (
    <div className="max-w-lg mx-auto px-4 py-16 text-center">
      <Trophy className="w-10 h-10 text-muted-foreground mx-auto mb-4" />
      <h1 className="font-display font-bold text-2xl mb-2">Organizer approval required</h1>
      <p className="text-sm text-muted-foreground mb-6">{copy}</p>
      {status === null && (
        <Link
          to="/organizer"
          className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl font-heading font-bold text-sm bg-primary text-primary-foreground"
        >
          Apply as an organizer <ArrowRight className="w-4 h-4" />
        </Link>
      )}
    </div>
  );
}

export default function CreateTournament() {
  const navigate = useNavigate();
  const { user } = useAuth();

  const [gate, setGate] = useState({ loading: true, allowed: false, status: null });
  const [games, setGames] = useState([]);
  const [step, setStep] = useState(0);
  const [form, setForm] = useState(initialForm);
  const [files, setFiles] = useState(initialFiles);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [submitted, setSubmitted] = useState(false);

  useEffect(() => {
    api.get("/api/organizer/status/")
      .then((data) => setGate({ loading: false, allowed: data.status === "approved", status: data.status }))
      .catch((e) => setGate({ loading: false, allowed: false, status: e.status === 404 ? null : "error" }));
  }, []);

  useEffect(() => {
    if (!gate.allowed) return;
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
  }, [gate.allowed]);

  const setField = (key, value) => setForm((f) => ({ ...f, [key]: value }));
  const setFile = (key, value) => setFiles((f) => ({ ...f, [key]: value }));

  const isOnline = form.mode !== "offline";
  const isOffline = form.mode !== "online";

  const canProceed = () => {
    if (step === 0) return form.name.trim() && form.game && form.starts_at;
    if (step === 1) {
      if (isOffline && !(form.venue_name.trim() && form.venue_address.trim() && form.venue_city.trim() && form.venue_country.trim())) return false;
      if (isOnline && !form.platform.trim()) return false;
      return true;
    }
    if (step === 3) {
      return files.company_registration_certificate && files.organizer_cnic_front && files.organizer_cnic_back;
    }
    return true;
  };

  const submit = async () => {
    setSubmitting(true);
    setError("");
    try {
      const formData = new FormData();
      Object.entries(form).forEach(([key, value]) => {
        if (value === "" || value === null || value === undefined) return;
        formData.append(key, value);
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

  if (gate.loading) {
    return (
      <div className="flex justify-center py-20 text-muted-foreground">
        <Loader2 className="w-6 h-6 animate-spin" />
      </div>
    );
  }

  if (!gate.allowed) {
    return <OrganizerGate status={gate.status} />;
  }

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
            <Field label="Tournament name" required>
              <TextInput value={form.name} onChange={(e) => setField("name", e.target.value)} placeholder="e.g. Winter Cup 2026" />
            </Field>
            <Field label="Game" required>
              <Select
                value={form.game}
                onChange={(e) => setField("game", e.target.value)}
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
              <Field label="Maximum players" required>
                <TextInput type="number" min="2" value={form.max_participants} onChange={(e) => setField("max_participants", e.target.value)} placeholder="e.g. 64" />
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
              <Field label="Registration fee (PKR)">
                <TextInput type="number" min="0" value={form.registration_fee} onChange={(e) => setField("registration_fee", e.target.value)} />
              </Field>
              <Field label="Prize pool (PKR)">
                <TextInput type="number" min="0" value={form.prize_pool} onChange={(e) => setField("prize_pool", e.target.value)} />
              </Field>
            </div>
            <Field label="Registration deadline">
              <TextInput type="datetime-local" value={form.registration_deadline} onChange={(e) => setField("registration_deadline", e.target.value)} />
            </Field>
            <div className="grid grid-cols-2 gap-4">
              <Field label="Tournament start date" required>
                <TextInput type="datetime-local" value={form.starts_at} onChange={(e) => setField("starts_at", e.target.value)} />
              </Field>
              <Field label="Tournament end date">
                <TextInput type="datetime-local" value={form.ends_at} onChange={(e) => setField("ends_at", e.target.value)} />
              </Field>
            </div>
          </>
        )}

        {step === 1 && (
          <>
            {isOffline && (
              <div className="space-y-4 pb-4 border-b border-border/60">
                <h3 className="font-heading font-bold text-sm">Venue</h3>
                <Field label="Venue name" required>
                  <TextInput value={form.venue_name} onChange={(e) => setField("venue_name", e.target.value)} />
                </Field>
                <Field label="Full address" required>
                  <TextArea value={form.venue_address} onChange={(e) => setField("venue_address", e.target.value)} />
                </Field>
                <Field label="Google Maps link">
                  <TextInput value={form.venue_map_link} onChange={(e) => setField("venue_map_link", e.target.value)} placeholder="https://maps.google.com/..." />
                </Field>
                <div className="grid grid-cols-2 gap-4">
                  <Field label="City" required>
                    <TextInput value={form.venue_city} onChange={(e) => setField("venue_city", e.target.value)} />
                  </Field>
                  <Field label="Province">
                    <TextInput value={form.venue_province} onChange={(e) => setField("venue_province", e.target.value)} />
                  </Field>
                </div>
                <Field label="Country" required>
                  <TextInput value={form.venue_country} onChange={(e) => setField("venue_country", e.target.value)} />
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
                  <TextInput value={form.discord_server} onChange={(e) => setField("discord_server", e.target.value)} placeholder="https://discord.gg/..." />
                </Field>
                <Field label="Room ID">
                  <TextInput value={form.room_id} onChange={(e) => setField("room_id", e.target.value)} />
                </Field>
                <Field label="Platform" required>
                  <TextInput
                    list="platform-suggestions"
                    value={form.platform}
                    onChange={(e) => setField("platform", e.target.value)}
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
              <TextInput value={form.contact_organizer_name} onChange={(e) => setField("contact_organizer_name", e.target.value)} />
            </Field>
            <Field label="Company name">
              <TextInput value={form.contact_company_name} onChange={(e) => setField("contact_company_name", e.target.value)} />
            </Field>
            <div className="grid grid-cols-2 gap-4">
              <Field label="Phone number">
                <TextInput value={form.contact_phone} onChange={(e) => setField("contact_phone", e.target.value)} />
              </Field>
              <Field label="Email">
                <TextInput type="email" value={form.contact_email} onChange={(e) => setField("contact_email", e.target.value)} />
              </Field>
            </div>
            <Field label="Emergency contact">
              <TextInput value={form.contact_emergency_phone} onChange={(e) => setField("contact_emergency_phone", e.target.value)} />
            </Field>
            <Field label="Website (optional)">
              <TextInput value={form.contact_website} onChange={(e) => setField("contact_website", e.target.value)} placeholder="https://..." />
            </Field>
            <div className="pt-2 border-t border-border/60 space-y-4">
              <h3 className="font-heading font-bold text-sm">Social media (optional)</h3>
              <div className="grid grid-cols-2 gap-4">
                <Field label="Facebook"><TextInput value={form.social_facebook} onChange={(e) => setField("social_facebook", e.target.value)} /></Field>
                <Field label="Instagram"><TextInput value={form.social_instagram} onChange={(e) => setField("social_instagram", e.target.value)} /></Field>
                <Field label="Discord"><TextInput value={form.social_discord} onChange={(e) => setField("social_discord", e.target.value)} /></Field>
                <Field label="YouTube"><TextInput value={form.social_youtube} onChange={(e) => setField("social_youtube", e.target.value)} /></Field>
              </div>
            </div>
          </>
        )}

        {step === 3 && (
          <>
            <FileInput label="Company Registration Certificate" required file={files.company_registration_certificate} onChange={(f) => setFile("company_registration_certificate", f)} />
            <FileInput label="Business License" file={files.business_license} onChange={(f) => setFile("business_license", f)} />
            <FileInput label="Organizer CNIC Front" required file={files.organizer_cnic_front} onChange={(f) => setFile("organizer_cnic_front", f)} />
            <FileInput label="Organizer CNIC Back" required file={files.organizer_cnic_back} onChange={(f) => setFile("organizer_cnic_back", f)} />
            <FileInput label="Tax Certificate" file={files.tax_certificate} onChange={(f) => setFile("tax_certificate", f)} />
            <FileInput label="Sponsor Agreement" file={files.sponsor_agreement} onChange={(f) => setFile("sponsor_agreement", f)} />
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
              <p><span className="text-muted-foreground">Max players:</span> {form.max_participants || "—"}</p>
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
              onClick={() => setStep((s) => Math.min(STEPS.length - 1, s + 1))}
              disabled={!canProceed()}
              className="inline-flex items-center gap-1.5 px-5 py-2.5 rounded-xl text-sm font-heading font-bold bg-primary text-primary-foreground disabled:opacity-50"
            >
              Next <ArrowRight className="w-4 h-4" />
            </button>
          ) : (
            <button
              onClick={submit}
              disabled={submitting || !canProceed()}
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
