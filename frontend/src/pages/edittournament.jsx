import React, { useEffect, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { Loader2, ArrowLeft, Save, CheckCircle2 } from "lucide-react";
import { api } from "@/lib/api";

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
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    api.get(`/api/tournaments/${id}/`)
      .then((t) => {
        if (!t.can_manage) {
          setDenied(true);
          return;
        }
        setForm({
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
        });
      })
      .catch((e) => setError(e.message || "Could not load this tournament."))
      .finally(() => setLoading(false));
    api.get("/api/games/").then(setGames).catch(() => {});
  }, [id]);

  const setField = (key, value) => setForm((f) => ({ ...f, [key]: value }));

  const isOnline = form?.mode !== "offline";
  const isOffline = form?.mode !== "online";

  const submit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setSaveError("");
    setSaved(false);
    try {
      const payload = {};
      EDITABLE_FIELDS.forEach((key) => { payload[key] = form[key]; });
      await api.patch(`/api/tournaments/${id}/`, payload);
      setSaved(true);
    } catch (err) {
      let msg = err.message || "Could not save your changes.";
      if (err.data && typeof err.data === "object") {
        msg = Object.entries(err.data).map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(" ") : v}`).join(" — ");
      }
      setSaveError(msg);
    } finally {
      setSaving(false);
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
      <p className="text-sm text-muted-foreground mb-6">Update the details below and save your changes.</p>

      <form onSubmit={submit} className="glass rounded-2xl border border-border/60 p-6 sm:p-8 space-y-6">
        <div className="space-y-4">
          <h3 className="font-heading font-bold text-sm">Tournament Details</h3>
          <Field label="Tournament name" required>
            <TextInput value={form.name} onChange={(e) => setField("name", e.target.value)} />
          </Field>
          <Field label="Game" required>
            <Select
              value={form.game}
              onChange={(e) => setField("game", e.target.value)}
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
            <Field label="Maximum players" required>
              <TextInput type="number" min="2" value={form.max_participants} onChange={(e) => setField("max_participants", e.target.value)} />
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
        </div>

        {isOffline && (
          <div className="space-y-4 pt-4 border-t border-border/60">
            <h3 className="font-heading font-bold text-sm">Venue</h3>
            <Field label="Venue name" required>
              <TextInput value={form.venue_name} onChange={(e) => setField("venue_name", e.target.value)} />
            </Field>
            <Field label="Full address" required>
              <TextInput value={form.venue_address} onChange={(e) => setField("venue_address", e.target.value)} />
            </Field>
            <Field label="Google Maps link">
              <TextInput value={form.venue_map_link} onChange={(e) => setField("venue_map_link", e.target.value)} />
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
              <input type="checkbox" checked={form.venue_parking_available} onChange={(e) => setField("venue_parking_available", e.target.checked)} />
              Parking available?
            </label>
          </div>
        )}

        {isOnline && (
          <div className="space-y-4 pt-4 border-t border-border/60">
            <h3 className="font-heading font-bold text-sm">Online details</h3>
            <Field label="Discord server">
              <TextInput value={form.discord_server} onChange={(e) => setField("discord_server", e.target.value)} />
            </Field>
            <Field label="Room ID">
              <TextInput value={form.room_id} onChange={(e) => setField("room_id", e.target.value)} />
            </Field>
            <Field label="Platform" required>
              <TextInput list="platform-suggestions" value={form.platform} onChange={(e) => setField("platform", e.target.value)} />
              <datalist id="platform-suggestions">
                {PLATFORM_SUGGESTIONS.map((p) => <option key={p} value={p} />)}
              </datalist>
            </Field>
          </div>
        )}

        <div className="space-y-4 pt-4 border-t border-border/60">
          <h3 className="font-heading font-bold text-sm">Contact Details</h3>
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
            <TextInput value={form.contact_website} onChange={(e) => setField("contact_website", e.target.value)} />
          </Field>
          <div className="grid grid-cols-2 gap-4">
            <Field label="Facebook"><TextInput value={form.social_facebook} onChange={(e) => setField("social_facebook", e.target.value)} /></Field>
            <Field label="Instagram"><TextInput value={form.social_instagram} onChange={(e) => setField("social_instagram", e.target.value)} /></Field>
            <Field label="Discord"><TextInput value={form.social_discord} onChange={(e) => setField("social_discord", e.target.value)} /></Field>
            <Field label="YouTube"><TextInput value={form.social_youtube} onChange={(e) => setField("social_youtube", e.target.value)} /></Field>
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
