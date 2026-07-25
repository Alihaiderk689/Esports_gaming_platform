import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Gamepad2, Calendar, Users, Loader2, Plus, MapPin, Wifi, Award, Swords, ArrowRight } from "lucide-react";
import { api } from "@/lib/api";

const BRACKET_FORMAT_LABELS = {
  single: "Single Elimination", double: "Double Elimination", guarantee3: "3-Game Guarantee",
  round_robin: "Round Robin", swiss: "Swiss System", group_playoff: "Group Stage + Playoff",
};

const formatMoney = (n) => `PKR ${Number(n || 0).toLocaleString()}`;

function formatDateRange(start, end) {
  if (!start) return "TBA";
  const opts = { month: "short", day: "numeric" };
  const s = new Date(start);
  if (!end) return `${s.toLocaleDateString(undefined, opts)}, ${s.getFullYear()}`;
  const e = new Date(end);
  if (s.toDateString() === e.toDateString()) return `${s.toLocaleDateString(undefined, opts)}, ${s.getFullYear()}`;
  const sameMonth = s.getMonth() === e.getMonth() && s.getFullYear() === e.getFullYear();
  const endStr = sameMonth ? `${e.getDate()}` : e.toLocaleDateString(undefined, opts);
  return `${s.toLocaleDateString(undefined, opts)} – ${endStr}, ${e.getFullYear()}`;
}

function Row({ icon: Icon, label, value }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="flex items-center gap-1.5 text-muted-foreground shrink-0">
        <Icon className="w-3.5 h-3.5" /> {label}
      </span>
      <span className="font-heading font-semibold text-right truncate">{value}</span>
    </div>
  );
}

export default function Tournaments() {
  const [tournaments, setTournaments] = useState([]);
  const [myTournamentIds, setMyTournamentIds] = useState(new Set());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [isApprovedOrganizer, setIsApprovedOrganizer] = useState(false);

  useEffect(() => {
    api
      .get("/api/tournaments/")
      .then(setTournaments)
      .catch((e) => setError(e.message || "Failed to load tournaments."))
      .finally(() => setLoading(false));
    api
      .get("/api/organizer/status/")
      .then((data) => setIsApprovedOrganizer(data.status === "approved"))
      .catch(() => setIsApprovedOrganizer(false));
  }, []);

  useEffect(() => {
    if (!isApprovedOrganizer) return;
    api.get("/api/tournaments/mine/")
      .then((mine) => setMyTournamentIds(new Set(mine.map((t) => t.id))))
      .catch(() => {});
  }, [isApprovedOrganizer]);

  // Other organizers' upcoming events only — your own live in My Tournaments.
  const visibleTournaments = tournaments.filter(
    (t) => t.phase === "upcoming" && !myTournamentIds.has(t.id),
  );

  return (
    <div className="mx-auto max-w-7xl px-4 sm:px-6 py-10 sm:py-14">
      <div className="flex flex-wrap items-start justify-between gap-4 mb-1">
        <h1 className="font-display font-extrabold text-4xl gradient-text">Tournaments</h1>
        {isApprovedOrganizer && (
          <Link
            to="/tournaments/create"
            className="inline-flex items-center gap-1.5 px-4 py-2.5 rounded-xl font-heading font-bold text-sm bg-primary text-primary-foreground hover:shadow-[0_0_28px_hsl(186_100%_50%/0.5)] transition-shadow"
          >
            <Plus className="w-4 h-4" /> Create Tournament
          </Link>
        )}
      </div>
      <p className="text-muted-foreground mb-8">Browse upcoming tournaments across every game.</p>

      {error && (
        <div className="mb-4 text-sm text-destructive bg-destructive/10 border border-destructive/30 rounded-lg px-3 py-2">
          {error}
        </div>
      )}

      {loading ? (
        <div className="flex justify-center py-20 text-muted-foreground">
          <Loader2 className="w-6 h-6 animate-spin" />
        </div>
      ) : visibleTournaments.length === 0 ? (
        <div className="text-center py-20 text-muted-foreground">No upcoming tournaments yet.</div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
          {visibleTournaments.map((t) => (
            <div
              key={t.id}
              className="group rounded-2xl overflow-hidden glass border border-border/60 hover:neon-border transition-all flex flex-col"
            >
              <Link to={`/tournaments/${t.id}`} className="block">
                <div className="relative h-44 overflow-hidden">
                  <img
                    src={t.cover_image_url || `https://placehold.co/600x400/11131F/00F0FF?text=${encodeURIComponent(t.game)}`}
                    alt=""
                    className="absolute inset-0 w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
                  />
                  <div className="absolute inset-0 bg-gradient-to-t from-background via-background/50 to-transparent" />
                  <span
                    className={`absolute top-3 left-3 text-[10px] font-heading font-bold uppercase tracking-wider px-2.5 py-1 rounded-full ${
                      t.phase === "live" ? "bg-accent/90 text-background" : "bg-primary/90 text-primary-foreground"
                    }`}
                  >
                    {t.phase}
                  </span>
                </div>
                <div className="px-5 pt-4 pb-3">
                  <h3 className="font-heading font-bold text-lg leading-tight group-hover:text-primary transition-colors">
                    {t.title}
                  </h3>
                  <div className="flex items-center gap-1.5 mt-1 text-sm text-muted-foreground">
                    <Gamepad2 className="w-3.5 h-3.5" /> {t.game}
                  </div>
                </div>
              </Link>

              <div className="px-5 pb-5 flex-1 flex flex-col">
                <div className="space-y-2.5 text-sm border-t border-border/60 pt-4">
                  <Row icon={Calendar} label="Main Event" value={formatDateRange(t.start_date, t.end_date)} />
                  <Row icon={Swords} label="Format" value={BRACKET_FORMAT_LABELS[t.bracket_format] || t.bracket_format} />
                  <Row icon={Award} label="Prize Pool" value={formatMoney(t.prize_pool)} />
                  <Row
                    icon={Users}
                    label="Registered"
                    value={t.max_participants ? `${t.teams} / ${t.max_participants}` : `${t.teams}`}
                  />
                  <Row
                    icon={t.mode === "online" ? Wifi : MapPin}
                    label={t.mode === "online" ? "Platform" : "Venue"}
                    value={
                      t.mode === "online"
                        ? t.platform || "Online"
                        : [t.venue_name, t.venue_city].filter(Boolean).join(", ") || (t.mode === "hybrid" ? "Hybrid" : "TBA")
                    }
                  />
                </div>

                <div className="mt-5 grid grid-cols-2 gap-2">
                  <Link
                    to="/games"
                    className="flex items-center justify-center px-3 py-2.5 rounded-lg text-xs font-heading font-bold uppercase tracking-wide bg-muted/40 border border-border hover:border-primary/50 transition-colors"
                  >
                    Visit Game Page
                  </Link>
                  <Link
                    to={`/tournaments/${t.id}`}
                    className="flex items-center justify-center gap-1 px-3 py-2.5 rounded-lg text-xs font-heading font-bold uppercase tracking-wide bg-primary text-primary-foreground hover:shadow-[0_0_20px_hsl(186_100%_50%/0.4)] transition-shadow"
                  >
                    View Tournament <ArrowRight className="w-3 h-3" />
                  </Link>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
