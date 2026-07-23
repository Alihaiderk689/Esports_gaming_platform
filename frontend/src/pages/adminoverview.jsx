import React, { useEffect, useState } from "react";
import { Users, Shield, Gamepad2, Trophy, ClipboardList, Handshake, Loader2 } from "lucide-react";
import { api } from "@/lib/api";

const TILES = [
  { key: "total_users", label: "Total Users", icon: Users },
  { key: "total_organizers", label: "Organizers", icon: Shield },
  { key: "total_games", label: "Games", icon: Gamepad2 },
  { key: "total_tournaments", label: "Tournaments", icon: Trophy },
  { key: "total_registrations", label: "Registrations", icon: ClipboardList },
  { key: "total_partners", label: "Partners", icon: Handshake },
];

export default function AdminOverview() {
  const [stats, setStats] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .get("/api/dashboard/admin/")
      .then(setStats)
      .catch((e) => setError(e.message || "Failed to load platform stats."));
  }, []);

  if (error) {
    return (
      <div className="text-sm text-destructive bg-destructive/10 border border-destructive/30 rounded-lg px-4 py-3">
        {error}
      </div>
    );
  }

  if (!stats) {
    return (
      <div className="flex items-center justify-center py-16 text-muted-foreground">
        <Loader2 className="w-6 h-6 animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
        {TILES.map((t) => (
          <div key={t.key} className="glass rounded-xl border border-border/60 p-5">
            <div className="w-9 h-9 rounded-lg bg-primary/10 grid place-items-center mb-3">
              <t.icon className="w-5 h-5 text-primary" />
            </div>
            <div className="font-display font-extrabold text-3xl">{stats[t.key]}</div>
            <div className="text-xs text-muted-foreground mt-1">{t.label}</div>
          </div>
        ))}
      </div>

      <div className="glass rounded-xl border border-border/60 p-5">
        <h2 className="font-heading font-bold text-sm uppercase tracking-wider text-muted-foreground mb-4">
          Organizers by status
        </h2>
        <div className="flex flex-wrap gap-3">
          {Object.entries(stats.organizers_by_status || {}).map(([status, count]) => (
            <div key={status} className="flex items-center gap-2 px-3.5 py-2 rounded-lg bg-muted/40 border border-border/60">
              <span className="text-xs font-heading font-bold uppercase tracking-wider text-muted-foreground">
                {status}
              </span>
              <span className="font-display font-bold text-lg">{count}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
