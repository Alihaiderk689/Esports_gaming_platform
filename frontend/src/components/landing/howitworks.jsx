import React from "react";
import { motion } from "framer-motion";
import { UserPlus, Swords, TrendingUp } from "lucide-react";

const STEPS = [
  { icon: UserPlus, step: "01", title: "Create your profile", desc: "Sign up, pick your games and showcase your gamer tag — it takes under a minute." },
  { icon: Swords, step: "02", title: "Join tournaments", desc: "Register for live and upcoming brackets across Valorant, Tekken, CS2 and more." },
  { icon: TrendingUp, step: "03", title: "Climb the ranks", desc: "Win matches, earn points and rise through Pakistan's national leaderboard." },
];

export default function HowItWorks() {
  return (
    <section className="relative py-20 sm:py-28">
      <div className="mx-auto max-w-7xl px-4 sm:px-6">
        <div className="text-center mb-12">
          <div className="text-xs font-heading font-bold uppercase tracking-[0.3em] text-primary">How it works</div>
          <h2 className="font-display font-extrabold text-3xl sm:text-5xl mt-2">Three steps to the arena</h2>
        </div>
        <div className="grid md:grid-cols-3 gap-6">
          {STEPS.map((s, i) => (
            <motion.div
              key={s.step}
              initial={{ opacity: 0, y: 30 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.1 }}
              className="relative rounded-2xl glass border border-border/60 p-7 hover:neon-border transition-all overflow-hidden group"
            >
              <div className="absolute -top-6 -right-2 font-display font-extrabold text-7xl text-primary/10 group-hover:text-primary/20 transition-colors">
                {s.step}
              </div>
              <div className="relative">
                <div className="w-12 h-12 rounded-xl bg-primary/10 border border-primary/30 grid place-items-center mb-5">
                  <s.icon className="w-6 h-6 text-primary" />
                </div>
                <h3 className="font-display font-bold text-xl mb-2">{s.title}</h3>
                <p className="text-sm text-muted-foreground leading-relaxed">{s.desc}</p>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}