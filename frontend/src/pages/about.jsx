import React, { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { Trophy, Users, Gamepad2, Swords, ShieldCheck, TrendingUp, ChevronRight } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/appauth";

const PILLARS = [
  {
    icon: Swords,
    title: "Every format, one platform",
    desc: "Single elimination, double elimination, round robin, Swiss, or group stage plus playoffs — organizers pick the format that fits their event, and brackets update live as results come in.",
  },
  {
    icon: ShieldCheck,
    title: "Verified organizers, real events",
    desc: "Every organizer goes through an approval process before they can publish a tournament, so players know exactly who they're registering with.",
  },
  {
    icon: TrendingUp,
    title: "Grassroots to pro",
    desc: "From a five-team online cup to a national LAN final, the same tools power every event — registration, check-in, seeding, and standings.",
  },
];

export default function About() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [games, setGames] = useState([]);

  useEffect(() => {
    api.get("/api/games/").then(setGames).catch(() => {});
  }, []);

  // Players don't get an About page — bounce them back home. Logged-out
  // visitors and approved organizers can still reach it directly.
  useEffect(() => {
    if (!user || user.is_staff) return;
    api
      .get("/api/organizer/status/")
      .then((data) => {
        if (data.status !== "approved") navigate("/", { replace: true });
      })
      .catch(() => navigate("/", { replace: true }));
  }, [user, navigate]);

  return (
    <div className="overflow-hidden">
      {/* HERO */}
      <section className="relative py-20 sm:py-28">
        <div className="absolute inset-0 mesh-bg opacity-60" />
        <div className="absolute inset-0 grid-overlay opacity-20" />
        <div className="absolute inset-0 bg-gradient-to-b from-transparent via-transparent to-background" />

        <div className="relative mx-auto max-w-4xl px-4 sm:px-6 text-center">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full glass border border-primary/30 mb-6"
          >
            <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
            <span className="text-xs font-heading font-semibold tracking-wide text-primary">ABOUT ESPORTS PAKISTAN</span>
          </motion.div>

          <motion.h1
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
            className="font-display font-extrabold text-4xl sm:text-6xl leading-[1.05] tracking-tight"
          >
            Where Pakistan
            <br />
            <span className="gradient-text animate-gradient">Competes.</span>
          </motion.h1>

          <motion.p
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.25 }}
            className="mt-6 text-base sm:text-lg text-muted-foreground leading-relaxed max-w-2xl mx-auto"
          >
            Esports Pakistan is a home for competitive gaming — a single platform where organizers launch
            verified tournaments and players register, get seeded into brackets, and battle their way toward
            the prize pool, from the opening round to the grand final.
          </motion.p>
        </div>
      </section>

      {/* STORY */}
      <section className="relative py-16 sm:py-20">
        <div className="mx-auto max-w-3xl px-4 sm:px-6 space-y-6 text-muted-foreground leading-relaxed">
          <p>
            At the heart of the platform is the tournament itself. Organizers apply and get approved before
            they can host, then build out their event — mode, bracket format, team size, prize pool,
            registration deadlines — and publish it for players to find. Every registration, check-in, and
            match result feeds a live bracket, so there's never any doubt about who's still standing.
          </p>
          <p>
            Players earn their place the same way everywhere: register for an event, check in when it opens,
            and get seeded into the bracket alongside everyone else who showed up. What happens after that is
            up to the format — single elimination, double elimination, round robin, Swiss system, or a full
            group stage that feeds into a playoff bracket.
          </p>
          <p>
            Esports Pakistan currently hosts tournaments across PUBG Mobile, Valorant, Counter-Strike 2,
            Tekken 8, and EA Sports FC, with more titles joining as the community grows. Whether it's a
            solo Tekken run or a five-stack grinding through a Valorant bracket, there's a tournament waiting.
          </p>
        </div>
      </section>

      {/* PILLARS */}
      <section className="relative py-16 sm:py-20 border-t border-border/40">
        <div className="mx-auto max-w-6xl px-4 sm:px-6">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
            {PILLARS.map((p, i) => (
              <motion.div
                key={p.title}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: i * 0.1 }}
                className="glass rounded-2xl border border-border/60 p-6"
              >
                <div className="w-11 h-11 rounded-xl bg-gradient-to-br from-primary to-green-500 grid place-items-center neon-border mb-4">
                  <p.icon className="w-5 h-5 text-background" strokeWidth={2.5} />
                </div>
                <h3 className="font-display font-bold text-lg mb-2">{p.title}</h3>
                <p className="text-sm text-muted-foreground leading-relaxed">{p.desc}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* GAMES STRIP */}
      {games.length > 0 && (
        <section className="relative py-16 sm:py-20 border-t border-border/40">
          <div className="mx-auto max-w-6xl px-4 sm:px-6">
            <div className="flex items-center gap-2 mb-8 justify-center">
              <Gamepad2 className="w-4 h-4 text-primary" />
              <span className="text-xs font-heading font-bold uppercase tracking-[0.25em] text-primary">Supported Games</span>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-5 gap-4 sm:gap-6">
              {games.filter((g) => g.is_active).map((g) => (
                <Link
                  key={g.id}
                  to={`/games/${g.slug}`}
                  className="group relative aspect-[3/4] rounded-xl overflow-hidden glass border border-border/60 hover:neon-border transition-all"
                >
                  <img
                    src={g.logo_url || `https://placehold.co/300x400/11131F/00F0FF?text=${encodeURIComponent(g.name)}`}
                    alt={g.name}
                    className="absolute inset-0 w-full h-full object-cover opacity-70 group-hover:opacity-100 transition-opacity duration-500"
                  />
                  <div className="absolute inset-0 bg-gradient-to-t from-background via-background/30 to-transparent" />
                  <span className="absolute bottom-2 left-2 right-2 font-heading font-bold text-xs sm:text-sm text-center truncate">
                    {g.name}
                  </span>
                </Link>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* CTA — signed-in players/organizers already have an account, so this only makes sense for visitors */}
      {!user && (
      <section className="relative py-20 sm:py-28 border-t border-border/40">
        <div className="mx-auto max-w-3xl px-4 sm:px-6 text-center">
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            whileInView={{ opacity: 1, scale: 1 }}
            viewport={{ once: true }}
            className="relative rounded-3xl glass border border-primary/30 p-10 sm:p-14 overflow-hidden"
          >
            <div className="absolute inset-0 mesh-bg opacity-50" />
            <div className="relative">
              <div className="flex items-center justify-center gap-6 mb-6 text-muted-foreground">
                <div className="flex items-center gap-2">
                  <Trophy className="w-4 h-4 text-primary" /> Verified Tournaments
                </div>
                <div className="flex items-center gap-2">
                  <Users className="w-4 h-4 text-primary" /> Live Brackets
                </div>
              </div>
              <h2 className="font-display font-extrabold text-3xl sm:text-4xl">
                Ready to <span className="gradient-text">enter the arena</span>?
              </h2>
              <p className="mt-4 text-muted-foreground max-w-md mx-auto">
                Browse what's live right now, or create your account to register for your first tournament.
              </p>
              <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
                <Link
                  to="/tournaments"
                  className="inline-flex items-center gap-2 px-6 py-3 rounded-xl font-heading font-bold text-sm glass hover:neon-border transition-all"
                >
                  <Trophy className="w-4 h-4 text-primary" /> Browse Tournaments
                </Link>
                <Link
                  to="/login"
                  className="inline-flex items-center gap-2 px-6 py-3 rounded-xl font-heading font-bold text-sm bg-gradient-to-r from-primary to-green-500 text-background hover:shadow-[0_0_32px_hsl(186_100%_50%/0.4)] transition-shadow"
                >
                  Create Account <ChevronRight className="w-4 h-4" />
                </Link>
              </div>
            </div>
          </motion.div>
        </div>
      </section>
      )}
    </div>
  );
}
