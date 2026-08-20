import React, { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Trophy, ArrowRight, Users, ShieldCheck, CalendarClock, Loader2 } from "lucide-react";
import { api } from "@/lib/api";

const POINTS = [
  {
    icon: Users,
    title: "Reach real players",
    desc: "Once approved, your tournament goes live on the public tournaments list where players can find and register for it.",
  },
  {
    icon: ShieldCheck,
    title: "Reviewed for quality",
    desc: "Every tournament is checked by an admin before it goes public, so players can trust what they're signing up for.",
  },
  {
    icon: CalendarClock,
    title: "Run it your way",
    desc: "Set the format, schedule, entry fee, prize pool, and venue or online details — brackets and check-in are handled for you.",
  },
];

export default function CreateHub() {
  const navigate = useNavigate();
  const [games, setGames] = useState([]);
  const [showDraftForm, setShowDraftForm] = useState(false);
  const [draftName, setDraftName] = useState("");
  const [draftGame, setDraftGame] = useState("");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (showDraftForm) api.get("/api/games/").then(setGames).catch(() => {});
  }, [showDraftForm]);

  const createDraft = async (e) => {
    e.preventDefault();
    setCreating(true);
    setError("");
    try {
      const tournament = await api.post("/api/tournaments/drafts/", { name: draftName, game: draftGame });
      navigate(`/tournaments/${tournament.id}/edit`);
    } catch (err) {
      setError(err.message || "Could not create draft.");
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="max-w-3xl mx-auto px-4 sm:px-6 py-12 sm:py-16 text-center">
      <div className="w-14 h-14 rounded-2xl mx-auto grid place-items-center mb-6 bg-gradient-to-br from-primary to-green-500 neon-border">
        <Trophy className="w-7 h-7 text-background" strokeWidth={2} />
      </div>
      <h1 className="font-display font-extrabold text-3xl sm:text-4xl gradient-text mb-3">
        Host your own tournament
      </h1>
      <p className="text-muted-foreground max-w-xl mx-auto mb-10">
        Bring your community together and run a competitive event on Esports Pakistan — from a small
        online cup to a full offline LAN. Submit the details once, and we'll take it live after a quick
        admin review.
      </p>

      <div className="grid sm:grid-cols-3 gap-4 mb-10 text-left">
        {POINTS.map((p) => (
          <div key={p.title} className="glass rounded-xl border border-border/60 p-5">
            <div className="w-9 h-9 rounded-lg bg-primary/10 grid place-items-center mb-3">
              <p.icon className="w-5 h-5 text-primary" />
            </div>
            <h3 className="font-heading font-bold text-sm mb-1">{p.title}</h3>
            <p className="text-xs text-muted-foreground leading-relaxed">{p.desc}</p>
          </div>
        ))}
      </div>

      <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
        <Link
          to="/tournaments/create"
          className="inline-flex items-center gap-2 px-6 py-3 rounded-xl font-heading font-bold text-base bg-primary text-primary-foreground hover:shadow-[0_0_28px_hsl(186_100%_50%/0.5)] transition-shadow"
        >
          Create Tournament <ArrowRight className="w-4 h-4" />
        </Link>
        {!showDraftForm && (
          <button
            type="button"
            onClick={() => setShowDraftForm(true)}
            className="text-sm text-muted-foreground hover:text-foreground underline underline-offset-4"
          >
            Not ready? Save a draft instead
          </button>
        )}
      </div>

      {showDraftForm && (
        <form onSubmit={createDraft} className="mt-8 max-w-sm mx-auto glass rounded-2xl border border-border/60 p-5 text-left space-y-4">
          <div>
            <label className="block text-xs font-heading font-bold uppercase tracking-wider text-muted-foreground mb-2">
              Tournament name
            </label>
            <input
              required
              value={draftName}
              onChange={(e) => setDraftName(e.target.value)}
              placeholder="e.g. Winter Cup 2026"
              className="w-full px-3.5 py-2.5 rounded-xl bg-muted/40 border border-border text-sm outline-none focus:border-primary"
            />
          </div>
          <div>
            <label className="block text-xs font-heading font-bold uppercase tracking-wider text-muted-foreground mb-2">
              Game
            </label>
            <select
              required
              value={draftGame}
              onChange={(e) => setDraftGame(e.target.value)}
              className="w-full px-3.5 py-2.5 rounded-xl bg-muted/40 border border-border text-sm outline-none focus:border-primary"
            >
              <option value="">Select a game</option>
              {games.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
            </select>
          </div>
          {error && (
            <div className="text-sm text-destructive bg-destructive/10 border border-destructive/30 rounded-lg px-3 py-2">
              {error}
            </div>
          )}
          <button
            type="submit"
            disabled={creating}
            className="w-full inline-flex items-center justify-center gap-2 px-5 py-2.5 rounded-xl font-heading font-bold text-sm bg-primary text-primary-foreground disabled:opacity-50"
          >
            {creating ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
            Save draft &amp; keep editing
          </button>
        </form>
      )}
    </div>
  );
}
