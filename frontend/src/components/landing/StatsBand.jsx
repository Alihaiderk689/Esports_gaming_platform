import React, { useEffect, useRef, useState } from "react";
import { motion, useInView } from "framer-motion";
import { Trophy, Users, Gamepad2, Swords } from "lucide-react";
import { api } from "@/lib/api";

const STAT_FIELDS = [
  { key: "total_tournaments", icon: Trophy, suffix: "+", label: "Tournaments hosted" },
  { key: "total_players", icon: Users, suffix: "+", label: "Active players" },
  { key: "total_games", icon: Gamepad2, suffix: "", label: "Supported games" },
  { key: "total_matches_played", icon: Swords, suffix: "+", label: "Matches played" },
];

function CountUp({ to, duration = 1.6 }) {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true, margin: "-60px" });
  const [n, setN] = useState(0);
  useEffect(() => {
    if (!inView) return;
    let raf;
    const start = performance.now();
    const tick = (t) => {
      const p = Math.min((t - start) / (duration * 1000), 1);
      const eased = 1 - Math.pow(1 - p, 3);
      setN(Math.round(to * eased));
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [inView, to, duration]);
  return <span ref={ref}>{n.toLocaleString()}</span>;
}

export default function StatsBand() {
  const [stats, setStats] = useState(null);

  useEffect(() => {
    api.get("/api/dashboard/stats/").then(setStats).catch(() => {});
  }, []);

  if (!stats) return null;

  return (
    <section className="relative py-16 border-y border-border/40">
      <div className="absolute inset-0 mesh-bg opacity-40" />
      <div className="relative mx-auto max-w-7xl px-4 sm:px-6 grid grid-cols-2 lg:grid-cols-4 gap-8">
        {STAT_FIELDS.map((s, i) => (
          <motion.div
            key={s.key}
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ delay: i * 0.08 }}
            className="flex flex-col sm:flex-row items-center sm:items-start gap-3 text-center sm:text-left"
          >
            <div className="w-11 h-11 rounded-xl glass grid place-items-center shrink-0">
              <s.icon className="w-5 h-5 text-primary" />
            </div>
            <div>
              <div className="font-display font-extrabold text-3xl sm:text-4xl gradient-text">
                <CountUp to={stats[s.key] || 0} />
                {s.suffix}
              </div>
              <div className="text-xs text-muted-foreground uppercase tracking-wider mt-1">{s.label}</div>
            </div>
          </motion.div>
        ))}
      </div>
    </section>
  );
}
