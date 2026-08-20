import React, { useState, useRef } from "react";
import { Link } from "react-router-dom";
import { motion, useScroll, useTransform } from "framer-motion";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/appauth";
import { Trophy, Users, Gamepad2, Calendar, Play, ChevronRight, Flame, Zap, Crown, Star } from "lucide-react";
import Logo from "@/components/Logo";
import HeroBackground from "@/components/landing/herobackground";
import ScrollProgress from "@/components/landing/ScrollProgress";
import StatsBand from "@/components/landing/StatsBand";
import HowItWorks from "@/components/landing/howitworks";

const FALLBACK_GAMES = [
  { id: 1, name: "Valorant", slug: "valorant", image: "/games/valorant.jpg", tagline: "5v5 tactical shooter", players: "2.4M" },
  { id: 2, name: "Tekken 8", slug: "tekken", image: "/games/tekken8.jpg", tagline: "King of the Iron Fist", players: "1.1M" },
  { id: 3, name: "CS2", slug: "cs2", image: "https://images.unsplash.com/photo-1538481199705-c710c4e965fc?w=800&q=80", tagline: "Counter-Strike", players: "3.2M" },
  { id: 4, name: "Dota 2", slug: "dota2", image: "https://images.unsplash.com/photo-1551103782-8ab07afd45c1?w=800&q=80", tagline: "MOBA legend", players: "1.8M" },
  { id: 5, name: "EA FC 25", slug: "ea-fc", image: "/games/ea-fc25.jpg", tagline: "Virtual football", players: "2.0M" },
];

const FALLBACK_TOURNAMENTS = [
  { id: 1, title: "Valorant Champions PK", game: "Valorant", prize: "Rs. 500,000", date: "Aug 12, 2026", status: "upcoming", teams: 32 },
  { id: 2, title: "Tekken Showdown Karachi", game: "Tekken 8", prize: "Rs. 250,000", date: "Aug 20, 2026", status: "live", teams: 64 },
  { id: 3, title: "CS2 Lahore League", game: "CS2", prize: "Rs. 300,000", date: "Sep 05, 2026", status: "upcoming", teams: 16 },
];

const PARTNERS = [
  { name: "Twitch", color: "#9146FF" },
  { name: "Discord", color: "#5865F2" },
  { name: "Steam", color: "#66c0f4" },
  { name: "YouTube Gaming", color: "#FF0000" },
  { name: "Riot Games", color: "#D13639" },
  { name: "Bandai Namco", color: "#FF6B00" },
];

export default function Landing() {
  const { user } = useAuth();
  const [games, setGames] = useState(FALLBACK_GAMES);
  const [tournaments, setTournaments] = useState(FALLBACK_TOURNAMENTS);
  const [loadingGames, setLoadingGames] = useState(true);

  const heroRef = useRef(null);
  const { scrollYProgress } = useScroll({ target: heroRef, offset: ["start start", "end start"] });
  const yText = useTransform(scrollYProgress, [0, 1], [0, 140]);
  const yOrb1 = useTransform(scrollYProgress, [0, 1], [0, -90]);
  const yOrb2 = useTransform(scrollYProgress, [0, 1], [0, 70]);

  React.useEffect(() => {
    let active = true;
    Promise.allSettled([
      api.get("/api/games/"),
      api.get("/api/tournaments/"),
      api.get("/api/partners/"),
    ]).then(([g, t]) => {
      if (!active) return;
      if (g.status === "fulfilled" && Array.isArray(g.value) && g.value.length) setGames(g.value);
      if (t.status === "fulfilled" && Array.isArray(t.value) && t.value.length) setTournaments(t.value);
      setLoadingGames(false);
    });
    return () => { active = false; };
  }, []);

  return (
    <div className="overflow-hidden">
      <ScrollProgress />
      {/* HERO */}
      <section ref={heroRef} className="relative min-h-[92vh] flex items-center pt-10 overflow-hidden">
        <HeroBackground />
        <div className="absolute inset-0 bg-gradient-to-b from-transparent via-transparent to-background" />

        {/* floating orbs */}
        <motion.div style={{ y: yOrb1 }} className="absolute top-1/4 left-10">
          <motion.div
            className="w-72 h-72 rounded-full bg-secondary/20 blur-3xl"
            animate={{ y: [0, -30, 0] }}
            transition={{ duration: 8, repeat: Infinity }}
          />
        </motion.div>
        <motion.div style={{ y: yOrb2 }} className="absolute bottom-1/4 right-10">
          <motion.div
            className="w-96 h-96 rounded-full bg-primary/15 blur-3xl"
            animate={{ y: [0, 40, 0] }}
            transition={{ duration: 10, repeat: Infinity }}
          />
        </motion.div>

        <div className="relative mx-auto max-w-7xl px-4 sm:px-6 w-full">
          <motion.div style={{ y: yText }} className="max-w-3xl">
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full glass border border-primary/30 mb-6"
            >
              <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
              <span className="text-xs font-heading font-semibold tracking-wide text-primary">SEASON 1 · NOW LIVE</span>
            </motion.div>

            <motion.h1
              initial={{ opacity: 0, y: 30 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.1 }}
              className="font-display font-extrabold text-5xl sm:text-7xl lg:text-8xl leading-[0.95] tracking-tight"
            >
              COMPETE.
              <br />
              <span className="gradient-text animate-gradient">CONQUER.</span>
              <br />
              CONNECT.
            </motion.h1>

            <motion.p
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.25 }}
              className="mt-6 text-base sm:text-lg text-muted-foreground max-w-xl leading-relaxed"
            >
              Pakistan's premier esports arena. Join tournaments, climb the rankings, build brackets and connect with the nation's top players — all in one platform.
            </motion.p>

            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.4 }}
              className="mt-8 flex flex-wrap items-center gap-3"
            >
              <Link
                to="/login"
                className="group inline-flex items-center gap-2 px-6 py-3.5 rounded-xl font-heading font-bold text-base bg-primary text-primary-foreground hover:shadow-[0_0_32px_hsl(186_100%_50%/0.5)] transition-shadow"
              >
                <Zap className="w-5 h-5" />
                Get Started
                <ChevronRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
              </Link>
              <Link
                to="/tournaments"
                className="inline-flex items-center gap-2 px-6 py-3.5 rounded-xl font-heading font-bold text-base glass hover:neon-border transition-all"
              >
                <Trophy className="w-5 h-5 text-primary" />
                Browse Tournaments
              </Link>
            </motion.div>

            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.6 }}
              className="mt-12 flex flex-wrap gap-8"
            >
              {[
                { icon: Trophy, label: "Tournaments", value: "120+" },
                { icon: Users, label: "Active Players", value: "15K+" },
                { icon: Gamepad2, label: "Games", value: "12" },
                { icon: Crown, label: "Prize Pool", value: "Rs. 5M" },
              ].map((s) => (
                <div key={s.label} className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-lg glass grid place-items-center">
                    <s.icon className="w-5 h-5 text-primary" />
                  </div>
                  <div>
                    <div className="font-display font-bold text-xl">{s.value}</div>
                    <div className="text-xs text-muted-foreground uppercase tracking-wider">{s.label}</div>
                  </div>
                </div>
              ))}
            </motion.div>
          </motion.div>
        </div>
      </section>

      {/* STATS */}
      <StatsBand />

      {/* FEATURED GAMES */}
      <section className="relative py-20 sm:py-28">
        <div className="mx-auto max-w-7xl px-4 sm:px-6">
          <SectionHeader
            eyebrow="Featured Games"
            title="Pick Your Arena"
            icon={Gamepad2}
          />
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 sm:gap-6">
            {games.map((g, i) => (
              <Link key={g.id} to={`/games/${g.slug}`}>
                <motion.div
                  initial={{ opacity: 0, y: 30 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true }}
                  transition={{ delay: i * 0.08 }}
                  className="group relative aspect-[3/4] rounded-2xl overflow-hidden glass border border-border/60 cursor-pointer"
                >
                  <img
                    src={g.image || g.logo_url || g.cover_image_url || g.banner || `https://placehold.co/600x800/11131F/00F0FF?text=${encodeURIComponent(g.name)}`}
                    alt={g.name}
                    className="absolute inset-0 w-full h-full object-cover opacity-60 group-hover:opacity-80 group-hover:scale-110 transition-all duration-700"
                  />
                  <div className="absolute inset-0 bg-gradient-to-t from-background via-background/40 to-transparent" />
                  <div className="absolute inset-0 grid-overlay opacity-0 group-hover:opacity-30 transition-opacity" />
                  <div className="relative h-full flex flex-col justify-end p-4 sm:p-5">
                    <div className="flex items-center gap-1.5 mb-2">
                      <span className="text-[10px] font-heading font-bold uppercase tracking-wider text-primary px-2 py-0.5 rounded-full bg-primary/10 border border-primary/30">
                        {g.players || (g.active_players ? `${g.active_players}` : "Live")}
                      </span>
                    </div>
                    <h3 className="font-display font-bold text-lg sm:text-xl group-hover:text-primary transition-colors">
                      {g.name}
                    </h3>
                    <p className="text-xs text-muted-foreground mt-0.5">{g.tagline || g.description || "Compete now"}</p>
                    <div className="mt-3 flex items-center gap-1 text-xs font-heading font-semibold text-primary opacity-0 group-hover:opacity-100 transition-opacity">
                      <Play className="w-3 h-3" /> Enter Arena
                    </div>
                  </div>
                  <div className="absolute top-3 right-3 w-2 h-2 rounded-full bg-green-400 animate-pulse" />
                </motion.div>
              </Link>
            ))}
          </div>
        </div>
      </section>

      {/* HOW IT WORKS */}
      <HowItWorks />

      {/* UPCOMING TOURNAMENTS */}
      <section className="relative py-20 sm:py-28">
        <div className="mx-auto max-w-7xl px-4 sm:px-6">
          <SectionHeader eyebrow="Tournaments" title="Upcoming & Live" icon={Trophy} />
          <div className="space-y-3">
            {tournaments.map((t, i) => {
              const live = (t.phase || "").toLowerCase() === "live";
              return (
                <motion.div
                  key={t.id}
                  initial={{ opacity: 0, x: -20 }}
                  whileInView={{ opacity: 1, x: 0 }}
                  viewport={{ once: true }}
                  transition={{ delay: i * 0.06 }}
                  className="group flex flex-col sm:flex-row sm:items-center gap-4 p-4 sm:p-5 rounded-xl glass border border-border/60 hover:neon-border transition-all"
                >
                  <div className={`shrink-0 w-12 h-12 rounded-lg grid place-items-center ${live ? "bg-accent/20 text-accent" : "bg-primary/10 text-primary"}`}>
                    {live ? <Flame className="w-6 h-6" /> : <Trophy className="w-6 h-6" />}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <h3 className="font-heading font-bold text-lg">{t.title}</h3>
                      {live ? (
                        <span className="inline-flex items-center gap-1 text-[10px] font-bold uppercase px-2 py-0.5 rounded-full bg-accent/20 text-accent animate-pulse">
                          <span className="w-1.5 h-1.5 rounded-full bg-accent" /> Live
                        </span>
                      ) : (
                        <span className="text-[10px] font-bold uppercase px-2 py-0.5 rounded-full bg-muted text-muted-foreground">
                          Upcoming
                        </span>
                      )}
                    </div>
                    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mt-1 text-sm text-muted-foreground">
                      <span className="flex items-center gap-1"><Gamepad2 className="w-3.5 h-3.5" /> {t.game}</span>
                      <span className="flex items-center gap-1"><Calendar className="w-3.5 h-3.5" /> {t.date || (t.start_date ? new Date(t.start_date).toLocaleDateString() : "TBA")}</span>
                      <span className="flex items-center gap-1"><Users className="w-3.5 h-3.5" /> {t.teams || t.max_teams || "—"} teams</span>
                    </div>
                  </div>
                  <div className="flex items-center justify-between sm:flex-col sm:items-end gap-2">
                    <div className="text-right">
                      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Prize Pool</div>
                      <div className="font-display font-bold text-lg gradient-text">{t.prize || t.prize_pool || "TBA"}</div>
                    </div>
                    <Link to="/tournaments" className="inline-flex items-center gap-1 text-sm font-heading font-semibold text-primary hover:gap-2 transition-all">
                      Details <ChevronRight className="w-4 h-4" />
                    </Link>
                  </div>
                </motion.div>
              );
            })}
          </div>
        </div>
      </section>

      {/* PARTNERS */}
      <section className="relative py-16 border-y border-border/40">
        <div className="mx-auto max-w-7xl px-4 sm:px-6">
          <div className="text-center mb-8">
            <div className="text-xs font-heading font-bold uppercase tracking-[0.3em] text-muted-foreground">Official Partners</div>
          </div>
          <div className="relative overflow-hidden">
            <div className="flex gap-12 animate-marquee w-max">
              {[...PARTNERS, ...PARTNERS].map((p, i) => (
                <div key={i} className="flex items-center gap-2.5 shrink-0 opacity-60 hover:opacity-100 transition-opacity">
                  <div className="w-8 h-8 rounded-lg grid place-items-center" style={{ background: `${p.color}22`, color: p.color }}>
                    <Star className="w-4 h-4" fill="currentColor" />
                  </div>
                  <span className="font-display font-bold text-xl tracking-wide whitespace-nowrap" style={{ color: p.color }}>
                    {p.name}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* CTA — signed-in players/organizers already have an account, so this only makes sense for visitors */}
      {!user && (
      <section className="relative py-24 sm:py-32">
        <div className="mx-auto max-w-4xl px-4 sm:px-6 text-center">
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            whileInView={{ opacity: 1, scale: 1 }}
            viewport={{ once: true }}
            className="relative rounded-3xl glass border border-primary/30 p-10 sm:p-16 overflow-hidden"
          >
            <div className="absolute inset-0 mesh-bg opacity-50" />
            <div className="relative">
              <h2 className="font-display font-extrabold text-4xl sm:text-5xl">
                Ready to <span className="gradient-text">level up</span>?
              </h2>
              <p className="mt-4 text-muted-foreground max-w-md mx-auto">
                Create your free account and join Pakistan's fastest growing esports community today.
              </p>
              <Link
                to="/login"
                className="mt-8 inline-flex items-center gap-2 px-8 py-4 rounded-xl font-heading font-bold text-base bg-gradient-to-r from-primary to-green-500 text-background hover:shadow-[0_0_40px_hsl(186_100%_50%/0.4)] transition-shadow"
              >
                Create Account
                <ChevronRight className="w-5 h-5" />
              </Link>
            </div>
          </motion.div>
        </div>
      </section>
      )}

      <footer className="border-t border-border/40 py-8">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 flex flex-col sm:flex-row items-center justify-between gap-3 text-sm text-muted-foreground">
          <div className="flex items-center gap-2 font-display font-bold tracking-wider">
            <Logo className="h-6 w-auto" />
            ESPORTS <span className="gradient-text">PAKISTAN</span>
          </div>
          <Link to="/about" className="hover:text-primary transition-colors">About</Link>
          <div>© 2026 Esports Pakistan. All rights reserved.</div>
        </div>
      </footer>
    </div>
  );
}

function SectionHeader({ eyebrow, title, icon: Icon }) {
  return (
    <div className="flex items-end justify-between mb-8 sm:mb-10">
      <div>
        <div className="flex items-center gap-2 mb-2">
          <Icon className="w-4 h-4 text-primary" />
          <span className="text-xs font-heading font-bold uppercase tracking-[0.25em] text-primary">{eyebrow}</span>
        </div>
        <h2 className="font-display font-extrabold text-3xl sm:text-4xl">{title}</h2>
      </div>
      <Link to="/tournaments" className="hidden sm:inline-flex items-center gap-1 text-sm font-heading font-semibold text-muted-foreground hover:text-primary transition-colors">
        View all <ChevronRight className="w-4 h-4" />
      </Link>
    </div>
  );
}