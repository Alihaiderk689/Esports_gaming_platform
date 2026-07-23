import React, { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { ArrowLeft, Swords, Clock, Crown, ListOrdered, Loader2 } from "lucide-react";
import { api } from "@/lib/api";

const FORMAT_OPTIONS = [
  { key: "single", label: "Single Elimination" },
  { key: "double", label: "Double Elimination" },
  { key: "guarantee3", label: "3-Game Guarantee" },
  { key: "round_robin", label: "Round Robin" },
  { key: "swiss", label: "Swiss System" },
  { key: "group_playoff", label: "Group + Playoff" },
];

function MatchResultForm({ match, onSubmitResult }) {
  const [winner, setWinner] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const submit = async (e) => {
    e.preventDefault();
    if (!winner) return;
    setSaving(true);
    setError("");
    try {
      await onSubmitResult(match.id, { winner: Number(winner) });
    } catch (err) {
      setError(err.message || "Could not submit result.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={submit} className="mt-2 pt-2 border-t border-border/40 space-y-1.5" onClick={(e) => e.stopPropagation()}>
      <select
        value={winner}
        onChange={(e) => setWinner(e.target.value)}
        className="w-full text-[11px] px-2 py-1 rounded-lg bg-muted/40 border border-border outline-none focus:border-primary"
      >
        <option value="">Select winner</option>
        <option value={match.player1}>{match.player1_email}</option>
        <option value={match.player2}>{match.player2_email}</option>
      </select>
      {error && <p className="text-[10px] text-destructive">{error}</p>}
      <button
        type="submit"
        disabled={saving || !winner}
        className="w-full text-[11px] py-1 rounded-lg bg-primary text-primary-foreground font-heading font-semibold disabled:opacity-50"
      >
        {saving ? "Saving…" : "Submit Result"}
      </button>
    </form>
  );
}

function MatchCard({ match, canManage, onSubmitResult }) {
  const done = match.status === "completed";
  const canSubmit = canManage && match.status === "ready" && match.player1 && match.player2;
  return (
    <div className={`w-56 shrink-0 rounded-xl border p-3 ${done ? "border-primary/40 bg-primary/5" : "border-border/60 glass"}`}>
      <div className="flex items-center justify-between mb-2">
        <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
          {match.status}
        </span>
        {done && <Crown className="w-3.5 h-3.5 text-primary" />}
      </div>
      {[
        { email: match.player1_email, id: match.player1 },
        { email: match.player2_email, id: match.player2 },
      ].map((p, i) => (
        <div
          key={i}
          className={`flex items-center justify-between px-2 py-1.5 rounded-lg text-sm mb-1 last:mb-0 ${
            done && match.winner === p.id ? "bg-primary/20 font-semibold" : "bg-muted/30 text-muted-foreground"
          }`}
        >
          <span className="truncate">{p.email || "TBD"}</span>
        </div>
      ))}
      {match.score && <p className="mt-2 text-xs text-muted-foreground">Score: {match.score}</p>}
      {canSubmit && <MatchResultForm match={match} onSubmitResult={onSubmitResult} />}
    </div>
  );
}

function RoundsRow({ rounds, finalRoundNumber, canManage, onSubmitResult }) {
  return (
    <div className="flex gap-6 overflow-x-auto pb-4">
      {rounds.map((round) => (
        <div key={round.round_number} className="flex flex-col gap-4 shrink-0">
          <div className="flex items-center gap-1.5 text-xs font-heading font-bold uppercase tracking-wider text-muted-foreground">
            {round.round_number === finalRoundNumber ? <Crown className="w-3.5 h-3.5" /> : <Clock className="w-3.5 h-3.5" />}
            {round.round_number === finalRoundNumber ? "Final" : `Round ${round.round_number}`}
          </div>
          <div className="flex flex-col gap-4 justify-around flex-1">
            {round.matches.map((m) => (
              <MatchCard key={m.id} match={m} canManage={canManage} onSubmitResult={onSubmitResult} />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function SectionLabel({ children }) {
  return (
    <h3 className="text-xs font-heading font-bold uppercase tracking-wider text-muted-foreground mb-3">
      {children}
    </h3>
  );
}

function StandingsTable({ standings }) {
  if (!standings || !standings.length) return null;
  return (
    <div className="overflow-x-auto rounded-xl border border-border/60 glass">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-[10px] font-heading font-bold uppercase tracking-wider text-muted-foreground">
            <th className="py-2 pl-4 pr-2">#</th>
            <th className="py-2 pr-2">Player</th>
            <th className="py-2 pr-2">Wins</th>
            <th className="py-2 pr-4">Played</th>
          </tr>
        </thead>
        <tbody>
          {standings.map((s, i) => (
            <tr key={s.player_id} className="border-t border-border/30">
              <td className="py-2 pl-4 pr-2 text-muted-foreground">{i + 1}</td>
              <td className="py-2 pr-2 font-medium">{s.name}</td>
              <td className="py-2 pr-2">{s.wins}</td>
              <td className="py-2 pr-4 text-muted-foreground">{s.played}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function EliminationSections({ bracket, canManage, onSubmitResult }) {
  const losersRounds = bracket.rounds.losers;
  const guaranteeRounds = bracket.rounds.guarantee;
  return (
    <div className="space-y-8">
      <div>
        <SectionLabel>Winners Bracket</SectionLabel>
        <RoundsRow rounds={bracket.rounds.winners} finalRoundNumber={bracket.total_rounds} canManage={canManage} onSubmitResult={onSubmitResult} />
      </div>
      <div>
        <SectionLabel>Losers Bracket</SectionLabel>
        <RoundsRow
          rounds={losersRounds}
          finalRoundNumber={losersRounds.length ? losersRounds[losersRounds.length - 1].round_number : null}
          canManage={canManage}
          onSubmitResult={onSubmitResult}
        />
      </div>
      {guaranteeRounds && guaranteeRounds.length > 0 && (
        <div>
          <SectionLabel>Guarantee Round</SectionLabel>
          <RoundsRow rounds={guaranteeRounds} finalRoundNumber={null} canManage={canManage} onSubmitResult={onSubmitResult} />
        </div>
      )}
      <div>
        <SectionLabel>Grand Final</SectionLabel>
        <RoundsRow rounds={bracket.rounds.grand_final} finalRoundNumber={1} canManage={canManage} onSubmitResult={onSubmitResult} />
      </div>
    </div>
  );
}

export default function BracketPage() {
  const { id } = useParams();

  const [tournament, setTournament] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [bracket, setBracket] = useState(null);
  const [bracketState, setBracketState] = useState("loading"); // loading | none | ready | error
  const [genFormat, setGenFormat] = useState("single");
  const [genNumGroups, setGenNumGroups] = useState(2);
  const [genSaving, setGenSaving] = useState(false);
  const [genError, setGenError] = useState("");
  const [stageSaving, setStageSaving] = useState(false);
  const [stageError, setStageError] = useState("");

  const loadBracket = () => {
    setBracketState("loading");
    api
      .get(`/api/tournaments/${id}/brackets/`)
      .then((b) => {
        setBracket(b);
        setBracketState("ready");
      })
      .catch((e) => {
        if (e.status === 404) setBracketState("none");
        else setBracketState("error");
      });
  };

  useEffect(() => {
    setLoading(true);
    api.get(`/api/tournaments/${id}/`)
      .then(setTournament)
      .catch((e) => setLoadError(e.message || "Could not load this tournament."))
      .finally(() => setLoading(false));
    loadBracket();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const generateBracket = async () => {
    setGenSaving(true);
    setGenError("");
    try {
      const payload = { format: genFormat };
      if (genFormat === "group_playoff") payload.num_groups = Number(genNumGroups);
      const b = await api.post(`/api/tournaments/${id}/brackets/`, payload);
      setBracket(b);
      setBracketState("ready");
    } catch (e) {
      setGenError(e.message || "Could not generate the bracket.");
    } finally {
      setGenSaving(false);
    }
  };

  const generateNextRound = async () => {
    setStageSaving(true);
    setStageError("");
    try {
      const b = await api.post(`/api/tournaments/${id}/brackets/next-round/`, {});
      setBracket(b);
    } catch (e) {
      setStageError(e.message || "Could not generate the next round.");
    } finally {
      setStageSaving(false);
    }
  };

  const generatePlayoff = async () => {
    setStageSaving(true);
    setStageError("");
    try {
      const b = await api.post(`/api/tournaments/${id}/brackets/generate-playoff/`, {});
      setBracket(b);
    } catch (e) {
      setStageError(e.message || "Could not generate the playoff bracket.");
    } finally {
      setStageSaving(false);
    }
  };

  const submitMatchResult = async (matchId, payload) => {
    await api.patch(`/api/matches/${matchId}/result/`, payload);
    loadBracket();
  };

  if (loading) {
    return (
      <div className="flex justify-center py-20 text-muted-foreground">
        <Loader2 className="w-6 h-6 animate-spin" />
      </div>
    );
  }

  if (loadError || !tournament) {
    return (
      <div className="max-w-lg mx-auto px-4 py-16 text-center">
        <p className="text-sm text-destructive bg-destructive/10 border border-destructive/30 rounded-lg px-3 py-2 inline-block">
          {loadError || "Tournament not found."}
        </p>
      </div>
    );
  }

  if (!tournament.can_manage && bracketState !== "ready" && bracketState !== "loading") {
    return (
      <div className="max-w-lg mx-auto px-4 py-16 text-center">
        <Link to={`/tournaments/${id}`} className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-primary mb-6">
          <ArrowLeft className="w-4 h-4" /> Back to tournament
        </Link>
        <p className="text-sm text-muted-foreground">No bracket has been generated for this tournament yet.</p>
      </div>
    );
  }

  let swissCanAdvance = false;
  let swissBlockedReason = "";
  if (bracket && bracket.format === "swiss") {
    const lastRound = bracket.rounds[bracket.rounds.length - 1];
    const currentComplete = !!lastRound && lastRound.matches.every((m) => m.status === "completed");
    const hasMoreRounds = bracket.rounds.length < bracket.total_rounds;
    swissCanAdvance = currentComplete && hasMoreRounds;
    if (!hasMoreRounds) swissBlockedReason = "";
    else if (!currentComplete) swissBlockedReason = "Finish every match in the current round to unlock the next one.";
  }

  let groupStageComplete = false;
  if (bracket && bracket.format === "group_playoff") {
    const allGroupMatches = Object.values(bracket.rounds.groups).flatMap((rounds) => rounds.flatMap((r) => r.matches));
    groupStageComplete = allGroupMatches.length > 0 && allGroupMatches.every((m) => m.status === "completed");
  }

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 py-10 sm:py-14">
      <div className="flex items-center justify-between gap-4 mb-6">
        <Link to={`/tournaments/${id}`} className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-primary">
          <ArrowLeft className="w-4 h-4" /> Back to tournament
        </Link>
      </div>

      <div className="flex items-center gap-2 mb-6">
        <Swords className="w-6 h-6 text-primary" />
        <h1 className="font-display font-extrabold text-2xl">{tournament.title} — Bracket</h1>
      </div>

      {bracketState === "loading" && (
        <div className="flex justify-center py-12 text-muted-foreground">
          <Loader2 className="w-5 h-5 animate-spin" />
        </div>
      )}

      {bracketState === "none" && tournament.can_manage && (
        <div className="glass rounded-xl border border-border/60 p-6 text-center">
          <p className="text-sm text-muted-foreground mb-4">
            No bracket has been generated for this tournament yet. Only checked-in players are seeded into the bracket — generate one once at least two players have checked in.
          </p>

          <div className="inline-flex flex-wrap gap-1 p-1 rounded-xl bg-muted/30 border border-border/60 mb-4">
            {FORMAT_OPTIONS.map((f) => (
              <button
                key={f.key}
                type="button"
                onClick={() => setGenFormat(f.key)}
                className={`px-3.5 py-1.5 rounded-lg text-sm font-heading font-semibold transition-colors ${
                  genFormat === f.key ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground"
                }`}
              >
                {f.label}
              </button>
            ))}
          </div>

          {genFormat === "single" && (
            <p className="text-xs text-muted-foreground mb-4">
              Works with any number of players — byes are seeded in automatically to fill out the bracket.
            </p>
          )}
          {genFormat === "double" && (
            <p className="text-xs text-muted-foreground mb-4">
              Double elimination needs an exact power of two checked-in players (4, 8, 16, or 32).
            </p>
          )}
          {genFormat === "guarantee3" && (
            <p className="text-xs text-muted-foreground mb-4">
              3-game guarantee needs an exact power of two checked-in players, at least 8 (8, 16, or 32).
            </p>
          )}
          {genFormat === "group_playoff" && (
            <div className="mb-4">
              <label className="block text-xs font-heading font-bold uppercase tracking-wider text-muted-foreground mb-2">
                Number of groups
              </label>
              <input
                type="number"
                min={2}
                value={genNumGroups}
                onChange={(e) => setGenNumGroups(Math.max(2, Number(e.target.value) || 2))}
                className="w-24 px-3 py-1.5 rounded-lg bg-muted/40 border border-border text-sm outline-none focus:border-primary text-center"
              />
              <p className="mt-2 text-xs text-muted-foreground">
                Needs at least {2 * genNumGroups} checked-in players.
              </p>
            </div>
          )}

          {genError && (
            <div className="mb-4 text-sm text-destructive bg-destructive/10 border border-destructive/30 rounded-lg px-3 py-2 inline-block">
              {genError}
            </div>
          )}
          <div>
            <button
              onClick={generateBracket}
              disabled={genSaving}
              className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-heading font-semibold bg-primary text-primary-foreground disabled:opacity-50"
            >
              {genSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Swords className="w-4 h-4" />}
              Generate Bracket
            </button>
          </div>
        </div>
      )}

      {bracketState === "error" && (
        <div className="text-sm text-destructive bg-destructive/10 border border-destructive/30 rounded-lg px-3 py-2">
          Could not load the bracket.
        </div>
      )}

      {bracketState === "ready" && bracket && (bracket.format === "double" || bracket.format === "guarantee3") && (
        <EliminationSections bracket={bracket} canManage={tournament.can_manage} onSubmitResult={submitMatchResult} />
      )}

      {bracketState === "ready" && bracket && (bracket.format === "round_robin" || bracket.format === "swiss") && (
        <div className="space-y-8">
          <RoundsRow rounds={bracket.rounds} finalRoundNumber={bracket.total_rounds} canManage={tournament.can_manage} onSubmitResult={submitMatchResult} />

          {bracket.format === "swiss" && tournament.can_manage && (
            <div>
              {stageError && (
                <div className="mb-3 text-sm text-destructive bg-destructive/10 border border-destructive/30 rounded-lg px-3 py-2 inline-block">
                  {stageError}
                </div>
              )}
              {bracket.rounds.length < bracket.total_rounds && (
                <div>
                  <button
                    onClick={generateNextRound}
                    disabled={!swissCanAdvance || stageSaving}
                    className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-heading font-semibold bg-primary text-primary-foreground disabled:opacity-50"
                  >
                    {stageSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Swords className="w-4 h-4" />}
                    Generate Next Round
                  </button>
                  {swissBlockedReason && (
                    <p className="mt-2 text-xs text-muted-foreground">{swissBlockedReason}</p>
                  )}
                </div>
              )}
            </div>
          )}

          <div>
            <SectionLabel>
              <span className="inline-flex items-center gap-1.5"><ListOrdered className="w-3.5 h-3.5" /> Standings</span>
            </SectionLabel>
            <StandingsTable standings={bracket.standings} />
          </div>
        </div>
      )}

      {bracketState === "ready" && bracket && bracket.format === "group_playoff" && (
        <div className="space-y-8">
          <div>
            <SectionLabel>Group Stage</SectionLabel>
            <div className="space-y-6">
              {Object.entries(bracket.rounds.groups).map(([label, rounds]) => (
                <div key={label}>
                  <p className="text-sm font-heading font-semibold mb-2">Group {label}</p>
                  <RoundsRow rounds={rounds} finalRoundNumber={null} canManage={tournament.can_manage} onSubmitResult={submitMatchResult} />
                  <StandingsTable standings={bracket.standings?.[label]} />
                </div>
              ))}
            </div>
          </div>

          <div>
            <SectionLabel>Playoff</SectionLabel>
            {bracket.rounds.playoff.length > 0 ? (
              <RoundsRow
                rounds={bracket.rounds.playoff}
                finalRoundNumber={Math.max(...bracket.rounds.playoff.map((r) => r.round_number))}
                canManage={tournament.can_manage}
                onSubmitResult={submitMatchResult}
              />
            ) : (
              <div className="glass rounded-xl border border-border/60 p-6 text-center">
                <p className="text-sm text-muted-foreground mb-4">
                  The playoff bracket unlocks once every group match is complete. The top finisher from each group advances.
                </p>
                {tournament.can_manage && (
                  <>
                    {stageError && (
                      <div className="mb-4 text-sm text-destructive bg-destructive/10 border border-destructive/30 rounded-lg px-3 py-2 inline-block">
                        {stageError}
                      </div>
                    )}
                    <div>
                      <button
                        onClick={generatePlayoff}
                        disabled={!groupStageComplete || stageSaving}
                        className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-heading font-semibold bg-primary text-primary-foreground disabled:opacity-50"
                      >
                        {stageSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Swords className="w-4 h-4" />}
                        Generate Playoff
                      </button>
                      {!groupStageComplete && (
                        <p className="mt-2 text-xs text-muted-foreground">Finish every group match to unlock the playoff.</p>
                      )}
                    </div>
                  </>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {bracketState === "ready" && bracket && bracket.format === "single" && (
        <RoundsRow rounds={bracket.rounds} finalRoundNumber={bracket.total_rounds} canManage={tournament.can_manage} onSubmitResult={submitMatchResult} />
      )}
    </div>
  );
}
