import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Loader2, Plus } from "lucide-react";
import { api } from "@/lib/api";
import TournamentCard from "@/components/tournaments/TournamentCard";

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
            <TournamentCard key={t.id} tournament={t} />
          ))}
        </div>
      )}
    </div>
  );
}
