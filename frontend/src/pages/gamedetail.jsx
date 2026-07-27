import React, { useEffect, useRef, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { ArrowLeft, ArrowRight, Loader2, Calendar, Award, Users, Trophy } from "lucide-react";
import { api } from "@/lib/api";
import { formatMoney, formatDateRange } from "@/lib/tournamentFormat";
import TournamentCard from "@/components/tournaments/TournamentCard";

export default function GameDetail() {
  const { slug } = useParams();
  const [game, setGame] = useState(null);
  const [tournaments, setTournaments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const tournamentsRef = useRef(null);

  useEffect(() => {
    setLoading(true);
    setError("");
    Promise.all([api.get("/api/games/"), api.get("/api/tournaments/")])
      .then(([games, allTournaments]) => {
        const match = games.find((g) => g.slug === slug);
        if (!match) {
          setError("This game couldn't be found.");
          return;
        }
        setGame(match);
        setTournaments(
          allTournaments
            .filter((t) => t.game_slug === slug)
            .sort((a, b) => new Date(a.start_date) - new Date(b.start_date)),
        );
      })
      .catch((e) => setError(e.message || "Failed to load this game."))
      .finally(() => setLoading(false));
  }, [slug]);

  if (loading) {
    return (
      <div className="flex justify-center py-20 text-muted-foreground">
        <Loader2 className="w-6 h-6 animate-spin" />
      </div>
    );
  }

  if (error || !game) {
    return (
      <div className="max-w-lg mx-auto px-4 py-16 text-center">
        <p className="text-sm text-destructive bg-destructive/10 border border-destructive/30 rounded-lg px-3 py-2 inline-block">
          {error || "This game couldn't be found."}
        </p>
        <div className="mt-6">
          <Link to="/games" className="text-sm text-primary hover:underline">Back to Games</Link>
        </div>
      </div>
    );
  }

  const cover = game.logo_url || `https://placehold.co/1600x900/11131F/00F0FF?text=${encodeURIComponent(game.name)}`;
  const featured = tournaments.find((t) => t.phase === "upcoming") || tournaments.find((t) => t.phase === "live");
  const upcomingOrLive = tournaments.filter((t) => t.phase === "upcoming" || t.phase === "live");

  return (
    <div>
      <div className="relative h-64 sm:h-80 overflow-hidden">
        <img src={cover} alt="" className="absolute inset-0 w-full h-full object-cover" />
        <div className="absolute inset-0 bg-gradient-to-t from-background via-background/70 to-background/20" />
        <div className="absolute inset-0 bg-gradient-to-r from-background/80 via-transparent to-transparent" />

        <div className="relative h-full max-w-7xl mx-auto px-4 sm:px-6 flex flex-col justify-end pb-8">
          <Link
            to="/games"
            className="absolute top-6 inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-primary transition-colors"
          >
            <ArrowLeft className="w-4 h-4" /> Back to Games
          </Link>
          <div className="flex flex-wrap gap-2 mb-3">
            {game.genre && (
              <span className="text-[10px] font-heading font-bold uppercase tracking-wider text-primary px-2.5 py-1 rounded-full bg-primary/10 border border-primary/30">
                {game.genre}
              </span>
            )}
            {game.categories?.map((c) => (
              <span
                key={c.id}
                className="text-[10px] font-heading font-bold uppercase tracking-wider text-muted-foreground px-2.5 py-1 rounded-full bg-muted/40 border border-border"
              >
                {c.name}
              </span>
            ))}
          </div>
          <h1 className="font-display font-extrabold text-4xl sm:text-6xl gradient-text">{game.name}</h1>
          {(game.platform || game.description) && (
            <p className="mt-2 text-muted-foreground max-w-2xl">
              {game.platform}{game.platform && game.description ? " · " : ""}{game.description}
            </p>
          )}
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 -mt-10 relative pb-16">
        {featured ? (
          <div className="glass rounded-2xl border border-border/60 p-6 sm:p-8 flex flex-wrap items-center gap-8">
            <div className="flex items-center gap-3">
              <Calendar className="w-5 h-5 text-primary" />
              <div>
                <div className="text-xs text-muted-foreground uppercase tracking-wider font-heading font-bold">Main Event</div>
                <div className="font-heading font-bold text-lg">{formatDateRange(featured.start_date, featured.end_date)}</div>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <Users className="w-5 h-5 text-primary" />
              <div>
                <div className="text-xs text-muted-foreground uppercase tracking-wider font-heading font-bold">Competing Teams</div>
                <div className="font-heading font-bold text-lg">
                  {featured.max_participants ? `${featured.teams} / ${featured.max_participants}` : featured.teams}
                </div>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <Award className="w-5 h-5 text-primary" />
              <div>
                <div className="text-xs text-muted-foreground uppercase tracking-wider font-heading font-bold">Prize Pool</div>
                <div className="font-heading font-bold text-lg">{formatMoney(featured.prize_pool)}</div>
              </div>
            </div>
            <button
              type="button"
              onClick={() => tournamentsRef.current?.scrollIntoView({ behavior: "smooth" })}
              className="ml-auto inline-flex items-center gap-2 px-6 py-3 rounded-xl font-heading font-bold text-sm bg-primary text-primary-foreground hover:shadow-[0_0_28px_hsl(186_100%_50%/0.5)] transition-shadow"
            >
              View Tournaments <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        ) : (
          <div className="glass rounded-2xl border border-border/60 p-8 text-center text-muted-foreground">
            <Trophy className="w-8 h-8 mx-auto mb-3 text-primary" />
            No tournaments scheduled yet for {game.name}.
          </div>
        )}

        <div ref={tournamentsRef} className="mt-12 scroll-mt-20">
          <h2 className="font-display font-bold text-2xl mb-6">Tournaments</h2>
          {upcomingOrLive.length === 0 ? (
            <p className="text-sm text-muted-foreground">Check back soon for {game.name} tournaments.</p>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
              {upcomingOrLive.map((t) => (
                <TournamentCard key={t.id} tournament={t} />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
