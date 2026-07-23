import React from "react";

// Purely illustrative match card used by FormatShowcase — sample data only,
// not connected to any real tournament.
export default function MatchChip({ a, b }) {
  const aWins = a.score > b.score;
  const bWins = b.score > a.score;

  const Row = ({ team, score, win }) => (
    <div
      className={`flex items-center justify-between px-2.5 py-1.5 rounded-lg text-sm ${
        win ? "bg-primary/15 font-semibold text-foreground" : "text-muted-foreground"
      }`}
    >
      <span className="truncate">{team}</span>
      <span
        className={`ml-2 shrink-0 w-5 h-5 rounded grid place-items-center text-[11px] font-bold ${
          win ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground"
        }`}
      >
        {score}
      </span>
    </div>
  );

  return (
    <div className="w-full rounded-xl border border-border/60 glass p-1 space-y-0.5">
      <Row team={a.team} score={a.score} win={aWins} />
      <Row team={b.team} score={b.score} win={bWins} />
    </div>
  );
}
