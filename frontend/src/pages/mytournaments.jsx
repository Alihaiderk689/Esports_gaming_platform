import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Loader2, ChevronRight, Clock, CheckCircle2, XCircle, Calendar, MapPin, Wifi } from "lucide-react";
import { api } from "@/lib/api";

const STATUS_META = {
  pending: { label: "Pending Admin Approval", icon: Clock, className: "bg-muted text-muted-foreground" },
  approved: { label: "Approved", icon: CheckCircle2, className: "bg-primary/10 text-primary" },
  rejected: { label: "Rejected", icon: XCircle, className: "bg-destructive/10 text-destructive" },
};

export default function MyTournaments() {
  const [tournaments, setTournaments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .get("/api/tournaments/mine/")
      .then(setTournaments)
      .catch((e) => setError(e.message || "Could not load your tournaments."))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="mx-auto max-w-5xl px-4 sm:px-6 py-10 sm:py-14">
      <h1 className="font-display font-extrabold text-4xl gradient-text mb-1">My Tournaments</h1>
      <p className="text-muted-foreground mb-8">Everything you've submitted — check status and make amendments.</p>

      {error && (
        <div className="mb-4 text-sm text-destructive bg-destructive/10 border border-destructive/30 rounded-lg px-3 py-2">
          {error}
        </div>
      )}

      {loading ? (
        <div className="flex justify-center py-20 text-muted-foreground">
          <Loader2 className="w-6 h-6 animate-spin" />
        </div>
      ) : tournaments.length === 0 ? (
        <div className="text-center py-20 text-muted-foreground">
          You haven't created any tournaments yet.{" "}
          <Link to="/create" className="text-primary hover:underline">Create one</Link>.
        </div>
      ) : (
        <div className="space-y-3">
          {tournaments.map((t) => {
            const meta = STATUS_META[t.status] || STATUS_META.pending;
            return (
              <Link
                key={t.id}
                to={`/tournaments/${t.id}`}
                state={{ from: "my-tournaments" }}
                className="flex flex-col sm:flex-row sm:items-center gap-3 p-4 sm:p-5 rounded-xl glass border border-border/60 hover:neon-border transition-all"
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <h3 className="font-heading font-bold text-lg truncate">{t.title}</h3>
                    <span className={`inline-flex items-center gap-1 text-[10px] font-bold uppercase px-2 py-0.5 rounded-full shrink-0 ${meta.className}`}>
                      <meta.icon className="w-3 h-3" /> {meta.label}
                    </span>
                    {t.status === "approved" && (
                      <span className={`inline-flex items-center gap-1 text-[10px] font-bold uppercase px-2 py-0.5 rounded-full shrink-0 ${
                        t.is_published ? "bg-primary/10 text-primary" : "bg-accent/10 text-accent"
                      }`}>
                        {t.is_published ? "Published" : "Not Published"}
                      </span>
                    )}
                  </div>
                  <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mt-1.5 text-sm text-muted-foreground">
                    <span className="flex items-center gap-1">
                      <Calendar className="w-3.5 h-3.5" />
                      {new Date(t.start_date).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })}
                    </span>
                    {t.mode === "online" ? (
                      <span className="flex items-center gap-1"><Wifi className="w-3.5 h-3.5" /> Online{t.platform ? ` · ${t.platform}` : ""}</span>
                    ) : (
                      <span className="flex items-center gap-1">
                        <MapPin className="w-3.5 h-3.5" />
                        {[t.venue_name, t.venue_city].filter(Boolean).join(", ") || "Venue TBA"}
                      </span>
                    )}
                  </div>
                  {t.status === "rejected" && t.rejection_reason && (
                    <p className="mt-1.5 text-xs text-destructive">Reason: {t.rejection_reason}</p>
                  )}
                </div>
                <ChevronRight className="w-4 h-4 text-muted-foreground shrink-0" />
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
