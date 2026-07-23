import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Trophy, Gamepad2, Calendar, Users, Loader2, Plus, MapPin, Wifi } from "lucide-react";
import { api } from "@/lib/api";

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
        <div className="space-y-3">
          {visibleTournaments.map((t) => (
            <Link
              key={t.id}
              to={`/tournaments/${t.id}`}
              className="group flex flex-col sm:flex-row sm:items-center gap-4 p-4 sm:p-5 rounded-xl glass border border-border/60 hover:neon-border transition-all"
            >
              <div className="shrink-0 w-12 h-12 rounded-lg grid place-items-center bg-primary/10 text-primary">
                <Trophy className="w-6 h-6" />
              </div>
              <div className="flex-1 min-w-0">
                <h3 className="font-heading font-bold text-lg">{t.title}</h3>
                <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mt-1 text-sm text-muted-foreground">
                  <span className="flex items-center gap-1"><Gamepad2 className="w-3.5 h-3.5" /> {t.game}</span>
                  <span className="flex items-center gap-1">
                    <Calendar className="w-3.5 h-3.5" />
                    {new Date(t.start_date).toLocaleString(undefined, {
                      dateStyle: "medium", timeStyle: "short",
                    })}
                  </span>
                  {t.mode === "online" ? (
                    <span className="flex items-center gap-1"><Wifi className="w-3.5 h-3.5" /> Online{t.platform ? ` · ${t.platform}` : ""}</span>
                  ) : (
                    <span className="flex items-center gap-1">
                      <MapPin className="w-3.5 h-3.5" />
                      {[t.venue_name, t.venue_city].filter(Boolean).join(", ") || (t.mode === "hybrid" ? "Hybrid" : "Venue TBA")}
                    </span>
                  )}
                  <span className="flex items-center gap-1"><Users className="w-3.5 h-3.5" /> {t.teams} registered</span>
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
