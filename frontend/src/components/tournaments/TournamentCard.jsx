import React from "react";
import { Link } from "react-router-dom";
import { Gamepad2, Calendar, Users, MapPin, Wifi, Award, Swords, ArrowRight } from "lucide-react";
import { BRACKET_FORMAT_LABELS, formatMoney, formatDateRange } from "@/lib/tournamentFormat";

// Wide Steam-style banners often carry their key art off-center — these two are
// framed for the sides, so a plain center crop clips the character/logo.
const COVER_OBJECT_POSITION = {
  "tekken 8": "left center",
  "counter-strike 2": "right center",
};

function Row({ icon: Icon, label, value }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="flex items-center gap-1.5 text-muted-foreground shrink-0">
        <Icon className="w-3.5 h-3.5" /> {label}
      </span>
      <span className="font-heading font-semibold text-right truncate">{value}</span>
    </div>
  );
}

export default function TournamentCard({ tournament: t }) {
  return (
    <div className="group rounded-2xl overflow-hidden glass border border-border/60 hover:neon-border transition-all flex flex-col">
      <Link to={`/tournaments/${t.id}`} className="block">
        <div className="relative h-44 overflow-hidden">
          <img
            src={t.cover_image_url || `https://placehold.co/600x400/11131F/00F0FF?text=${encodeURIComponent(t.game)}`}
            alt=""
            style={{ objectPosition: COVER_OBJECT_POSITION[t.game?.toLowerCase()] || "center" }}
            className="absolute inset-0 w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
          />
          <div className="absolute inset-0 bg-gradient-to-t from-background via-background/50 to-transparent" />
          <span
            className={`absolute top-3 left-3 text-[10px] font-heading font-bold uppercase tracking-wider px-2.5 py-1 rounded-full ${
              t.phase === "live" ? "bg-accent/90 text-background" : "bg-primary/90 text-primary-foreground"
            }`}
          >
            {t.phase}
          </span>
        </div>
        <div className="px-5 pt-4 pb-3">
          <h3 className="font-heading font-bold text-lg leading-tight group-hover:text-primary transition-colors">
            {t.title}
          </h3>
          <div className="flex items-center gap-1.5 mt-1 text-sm text-muted-foreground">
            <Gamepad2 className="w-3.5 h-3.5" /> {t.game}
          </div>
        </div>
      </Link>

      <div className="px-5 pb-5 flex-1 flex flex-col">
        <div className="space-y-2.5 text-sm border-t border-border/60 pt-4">
          <Row icon={Calendar} label="Main Event" value={formatDateRange(t.start_date, t.end_date)} />
          <Row icon={Swords} label="Format" value={BRACKET_FORMAT_LABELS[t.bracket_format] || t.bracket_format} />
          <Row icon={Award} label="Prize Pool" value={formatMoney(t.prize_pool)} />
          <Row
            icon={Users}
            label="Registered"
            value={t.max_participants ? `${t.teams} / ${t.max_participants}` : `${t.teams}`}
          />
          <Row
            icon={t.mode === "online" ? Wifi : MapPin}
            label={t.mode === "online" ? "Platform" : "Venue"}
            value={
              t.mode === "online"
                ? t.platform || "Online"
                : [t.venue_name, t.venue_city].filter(Boolean).join(", ") || (t.mode === "hybrid" ? "Hybrid" : "TBA")
            }
          />
        </div>

        <div className="mt-5">
          <Link
            to={`/tournaments/${t.id}`}
            className="flex items-center justify-center gap-1 px-3 py-2.5 rounded-lg text-xs font-heading font-bold uppercase tracking-wide bg-primary text-primary-foreground hover:shadow-[0_0_20px_hsl(186_100%_50%/0.4)] transition-shadow"
          >
            View Tournament <ArrowRight className="w-3 h-3" />
          </Link>
        </div>
      </div>
    </div>
  );
}
