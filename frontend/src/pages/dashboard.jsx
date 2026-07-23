import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  Users, UserPlus, ClipboardList, CalendarClock, Loader2, Clock,
  Building2, ArrowRight, Trophy, ShieldCheck, CheckCircle2,
} from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/appauth";

const PLAYER_TILES = [
  { key: "followers_count", label: "Followers", icon: Users },
  { key: "following_count", label: "Following", icon: UserPlus },
  { key: "registrations_count", label: "Registrations", icon: ClipboardList },
  { key: "upcoming_tournaments_count", label: "Upcoming Tournaments", icon: CalendarClock },
];

const ORGANIZER_TILES = [
  { key: "tournaments_count", label: "Total Tournaments", icon: Trophy },
  { key: "pending_tournaments_count", label: "Pending Approval", icon: Clock },
  { key: "completed_tournaments_count", label: "Completed Tournaments", icon: CheckCircle2 },
];

const STATUS_LABEL = {
  pending: "Your organizer application is under review.",
  rejected: "Your organizer application was rejected.",
};

function StatTiles({ tiles, data }) {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
      {tiles.map((t) => (
        <div key={t.key} className="glass rounded-xl border border-border/60 p-5">
          <div className="w-9 h-9 rounded-lg bg-primary/10 grid place-items-center mb-3">
            <t.icon className="w-5 h-5 text-primary" />
          </div>
          <div className="font-display font-extrabold text-3xl">{data[t.key]}</div>
          <div className="text-xs text-muted-foreground mt-1">{t.label}</div>
        </div>
      ))}
    </div>
  );
}

export default function Dashboard() {
  const { user } = useAuth();
  const [player, setPlayer] = useState(null);
  const [organizer, setOrganizer] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    setLoading(true);
    api
      .get("/api/dashboard/player/")
      .then(async (data) => {
        setPlayer(data);
        if (data.is_organizer) {
          try {
            setOrganizer(await api.get("/api/dashboard/organizer/"));
          } catch {
            /* organizer overview optional */
          }
        }
      })
      .catch((e) => setError(e.message || "Could not load your dashboard."))
      .finally(() => setLoading(false));
  }, []);

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
        <p className="text-sm text-destructive bg-destructive/10 border border-destructive/30 rounded-lg px-3 py-2 inline-block">
          {error}
        </p>
      </div>
    );
  }

  const name = player.profile.first_name || user?.email;

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 py-10 sm:py-14 space-y-10">
      <div>
        <h1 className="font-display font-extrabold text-3xl gradient-text mb-1">Welcome back, {name}</h1>
        <p className="text-sm text-muted-foreground">Here's what's happening with your account.</p>
      </div>

      <StatTiles tiles={PLAYER_TILES} data={player} />

      <div>
        <h2 className="font-heading font-bold text-sm uppercase tracking-wider text-muted-foreground mb-4">
          Upcoming matches
        </h2>
        {player.upcoming_matches.length === 0 ? (
          <div className="glass rounded-xl border border-border/60 p-6 text-center text-sm text-muted-foreground">
            No upcoming matches right now.
          </div>
        ) : (
          <div className="space-y-2">
            {player.upcoming_matches.map((m) => (
              <div key={m.id} className="flex items-center justify-between gap-3 glass rounded-xl border border-border/60 px-4 py-3">
                <div className="flex items-center gap-2 text-sm">
                  <Clock className="w-4 h-4 text-primary shrink-0" />
                  <span className="font-heading font-semibold">{m.tournament}</span>
                  <span className="text-muted-foreground">· Round {m.round_number}</span>
                </div>
                <span className="text-sm text-muted-foreground truncate">vs {m.opponent_email}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      <div>
        <div className="flex items-center gap-2 mb-4">
          <Building2 className="w-5 h-5 text-primary" />
          <h2 className="font-display font-bold text-xl">Organizer</h2>
        </div>

        {!player.is_organizer && (
          <Link
            to="/organizer"
            className="flex items-center justify-between gap-3 glass rounded-xl border border-border/60 px-5 py-4 hover:border-primary/50 transition-colors"
          >
            <div>
              <p className="font-heading font-semibold text-sm mb-0.5">Want to run your own tournaments?</p>
              <p className="text-xs text-muted-foreground">Apply to become an organizer.</p>
            </div>
            <ArrowRight className="w-4 h-4 text-primary shrink-0" />
          </Link>
        )}

        {player.is_organizer && player.organizer_status !== "approved" && (
          <Link
            to="/organizer"
            className="flex items-center justify-between gap-3 glass rounded-xl border border-border/60 px-5 py-4 hover:border-primary/50 transition-colors mb-4"
          >
            <p className="text-sm">{STATUS_LABEL[player.organizer_status] || "Manage your organizer application."}</p>
            <ArrowRight className="w-4 h-4 text-primary shrink-0" />
          </Link>
        )}

        {player.is_organizer && organizer && (
          <div className="space-y-4">
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <ShieldCheck className="w-4 h-4 text-primary" /> {organizer.organizer.company_name}
            </div>
            <StatTiles tiles={ORGANIZER_TILES} data={organizer} />
            {organizer.tournaments.length > 0 && (
              <div className="space-y-2">
                {organizer.tournaments.map((t) => (
                  <Link
                    key={t.id}
                    to={`/tournaments/${t.id}`}
                    className="flex items-center justify-between gap-3 glass rounded-xl border border-border/60 px-4 py-3 hover:border-primary/50 transition-colors"
                  >
                    <span className="font-heading font-semibold text-sm truncate">{t.name}</span>
                    <span className="text-xs text-muted-foreground shrink-0">{t.registrations_count} registered</span>
                  </Link>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
