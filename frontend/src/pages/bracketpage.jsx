import React, { useEffect, useState } from "react";
import { useParams, Link, useLocation } from "react-router-dom";
import {
  ArrowLeft, Swords, Clock, Crown, ListOrdered, Loader2, Eye, RotateCcw, ArrowUpDown,
  Settings2, Flag, Pencil, CalendarClock, StickyNote,
} from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/appauth";

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

function MatchManagePanel({ match, actions }) {
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const [forfeitPlayer, setForfeitPlayer] = useState("");
  const [forfeitReason, setForfeitReason] = useState("");
  const [overrideWinner, setOverrideWinner] = useState("");
  const [overrideScore, setOverrideScore] = useState("");
  const [overrideReason, setOverrideReason] = useState("");
  const [scheduledAt, setScheduledAt] = useState(match.scheduled_at ? match.scheduled_at.slice(0, 16) : "");
  const [notes, setNotes] = useState(null);
  const [notesSaving, setNotesSaving] = useState(false);

  const canForfeit = match.status === "ready" && match.player1 && match.player2;
  const canOverride = match.status === "completed" && match.player1 && match.player2;

  const openTab = (t) => {
    setTab((cur) => (cur === t ? null : t));
    setError("");
    if (t === "notes" && notes === null) {
      api.get(`/api/matches/${match.id}/notes/`).then((d) => setNotes(d.organizer_notes)).catch(() => setNotes(""));
    }
  };

  const submitForfeit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError("");
    try {
      await actions.onForfeit(match.id, { forfeiting_player: Number(forfeitPlayer), reason: forfeitReason });
      setTab(null);
    } catch (err) {
      setError(err.message || "Could not record the forfeit.");
    } finally {
      setSaving(false);
    }
  };

  const submitOverride = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError("");
    try {
      await actions.onOverride(match.id, { winner: Number(overrideWinner), score: overrideScore, reason: overrideReason });
      setTab(null);
    } catch (err) {
      setError(err.message || "Could not correct this result.");
    } finally {
      setSaving(false);
    }
  };

  const submitSchedule = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError("");
    try {
      await actions.onSchedule(match.id, { scheduled_at: scheduledAt ? new Date(scheduledAt).toISOString() : null });
      setTab(null);
    } catch (err) {
      setError(err.message || "Could not schedule this match.");
    } finally {
      setSaving(false);
    }
  };

  const saveNotes = async () => {
    setNotesSaving(true);
    setError("");
    try {
      await api.patch(`/api/matches/${match.id}/notes/`, { organizer_notes: notes });
    } catch (err) {
      setError(err.message || "Could not save notes.");
    } finally {
      setNotesSaving(false);
    }
  };

  return (
    <div className="mt-2 pt-2 border-t border-border/40" onClick={(e) => e.stopPropagation()}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1 text-[10px] text-muted-foreground hover:text-primary"
      >
        <Settings2 className="w-3 h-3" /> Manage
      </button>
      {open && (
        <div className="mt-1.5 space-y-1.5">
          <div className="flex flex-wrap gap-1">
            {canForfeit && (
              <button type="button" onClick={() => openTab("forfeit")} className={`text-[10px] px-1.5 py-0.5 rounded-md flex items-center gap-1 ${tab === "forfeit" ? "bg-destructive/20 text-destructive" : "bg-muted/40 text-muted-foreground hover:text-foreground"}`}>
                <Flag className="w-2.5 h-2.5" /> Forfeit
              </button>
            )}
            {canOverride && (
              <button type="button" onClick={() => openTab("override")} className={`text-[10px] px-1.5 py-0.5 rounded-md flex items-center gap-1 ${tab === "override" ? "bg-primary/20 text-primary" : "bg-muted/40 text-muted-foreground hover:text-foreground"}`}>
                <Pencil className="w-2.5 h-2.5" /> Correct
              </button>
            )}
            <button type="button" onClick={() => openTab("schedule")} className={`text-[10px] px-1.5 py-0.5 rounded-md flex items-center gap-1 ${tab === "schedule" ? "bg-primary/20 text-primary" : "bg-muted/40 text-muted-foreground hover:text-foreground"}`}>
              <CalendarClock className="w-2.5 h-2.5" /> Schedule
            </button>
            <button type="button" onClick={() => openTab("notes")} className={`text-[10px] px-1.5 py-0.5 rounded-md flex items-center gap-1 ${tab === "notes" ? "bg-primary/20 text-primary" : "bg-muted/40 text-muted-foreground hover:text-foreground"}`}>
              <StickyNote className="w-2.5 h-2.5" /> Notes
            </button>
          </div>

          {error && <p className="text-[10px] text-destructive">{error}</p>}

          {tab === "forfeit" && (
            <form onSubmit={submitForfeit} className="space-y-1">
              <select value={forfeitPlayer} onChange={(e) => setForfeitPlayer(e.target.value)} required className="w-full text-[11px] px-2 py-1 rounded-lg bg-muted/40 border border-border outline-none focus:border-primary">
                <option value="">Forfeiting player…</option>
                <option value={match.player1}>{match.player1_email}</option>
                <option value={match.player2}>{match.player2_email}</option>
              </select>
              <input value={forfeitReason} onChange={(e) => setForfeitReason(e.target.value)} placeholder="Reason" required className="w-full text-[11px] px-2 py-1 rounded-lg bg-muted/40 border border-border outline-none focus:border-primary" />
              <button type="submit" disabled={saving} className="w-full text-[11px] py-1 rounded-lg bg-destructive text-destructive-foreground font-heading font-semibold disabled:opacity-50">
                {saving ? "Saving…" : "Confirm Forfeit"}
              </button>
            </form>
          )}

          {tab === "override" && (
            <form onSubmit={submitOverride} className="space-y-1">
              <select value={overrideWinner} onChange={(e) => setOverrideWinner(e.target.value)} required className="w-full text-[11px] px-2 py-1 rounded-lg bg-muted/40 border border-border outline-none focus:border-primary">
                <option value="">Correct winner…</option>
                <option value={match.player1}>{match.player1_email}</option>
                <option value={match.player2}>{match.player2_email}</option>
              </select>
              <input value={overrideScore} onChange={(e) => setOverrideScore(e.target.value)} placeholder="Score (optional)" className="w-full text-[11px] px-2 py-1 rounded-lg bg-muted/40 border border-border outline-none focus:border-primary" />
              <input value={overrideReason} onChange={(e) => setOverrideReason(e.target.value)} placeholder="Reason (required)" required className="w-full text-[11px] px-2 py-1 rounded-lg bg-muted/40 border border-border outline-none focus:border-primary" />
              <button type="submit" disabled={saving} className="w-full text-[11px] py-1 rounded-lg bg-primary text-primary-foreground font-heading font-semibold disabled:opacity-50">
                {saving ? "Saving…" : "Confirm Correction"}
              </button>
              <p className="text-[9px] text-muted-foreground">Only works if nothing downstream has been played yet.</p>
            </form>
          )}

          {tab === "schedule" && (
            <form onSubmit={submitSchedule} className="space-y-1">
              <input
                type="datetime-local"
                value={scheduledAt}
                onChange={(e) => setScheduledAt(e.target.value)}
                className="w-full text-[11px] px-2 py-1 rounded-lg bg-muted/40 border border-border outline-none focus:border-primary"
              />
              <button type="submit" disabled={saving} className="w-full text-[11px] py-1 rounded-lg bg-primary text-primary-foreground font-heading font-semibold disabled:opacity-50">
                {saving ? "Saving…" : "Save Schedule"}
              </button>
            </form>
          )}

          {tab === "notes" && (
            <div className="space-y-1">
              {notes === null ? (
                <Loader2 className="w-3 h-3 animate-spin text-muted-foreground" />
              ) : (
                <>
                  <textarea
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                    rows={2}
                    placeholder="Private organizer notes…"
                    className="w-full text-[11px] px-2 py-1 rounded-lg bg-muted/40 border border-border outline-none focus:border-primary"
                  />
                  <button type="button" onClick={saveNotes} disabled={notesSaving} className="w-full text-[11px] py-1 rounded-lg bg-primary text-primary-foreground font-heading font-semibold disabled:opacity-50">
                    {notesSaving ? "Saving…" : "Save Notes"}
                  </button>
                </>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function MatchDisputeButton({ matchId }) {
  const [open, setOpen] = useState(false);
  const [description, setDescription] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [submitted, setSubmitted] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    e.stopPropagation();
    setSaving(true);
    setError("");
    try {
      await api.post(`/api/matches/${matchId}/disputes/`, { description });
      setSubmitted(true);
      setOpen(false);
    } catch (err) {
      setError(err.message || "Could not file this dispute.");
    } finally {
      setSaving(false);
    }
  };

  if (submitted) {
    return <p className="mt-2 pt-2 border-t border-border/40 text-[10px] text-primary">Dispute filed for this match.</p>;
  }

  return (
    <div className="mt-2 pt-2 border-t border-border/40" onClick={(e) => e.stopPropagation()}>
      {!open ? (
        <button type="button" onClick={() => setOpen(true)} className="flex items-center gap-1 text-[10px] text-muted-foreground hover:text-destructive">
          <Flag className="w-3 h-3" /> Dispute this match
        </button>
      ) : (
        <form onSubmit={submit} className="space-y-1">
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="What went wrong?"
            rows={2}
            required
            className="w-full text-[11px] px-2 py-1 rounded-lg bg-muted/40 border border-border outline-none focus:border-primary"
          />
          {error && <p className="text-[10px] text-destructive">{error}</p>}
          <button type="submit" disabled={saving || !description.trim()} className="w-full text-[11px] py-1 rounded-lg bg-destructive text-destructive-foreground font-heading font-semibold disabled:opacity-50">
            {saving ? "Filing…" : "File Dispute"}
          </button>
        </form>
      )}
    </div>
  );
}

function MatchCard({ match, canManage, matchActions, currentUserId }) {
  const done = match.status === "completed";
  const canSubmit = canManage && match.status === "ready" && match.player1 && match.player2;
  const isParticipant = currentUserId && (match.player1 === currentUserId || match.player2 === currentUserId);
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
      {match.is_forfeit ? (
        <p className="mt-2 text-xs text-muted-foreground">Won by forfeit</p>
      ) : (
        match.score && <p className="mt-2 text-xs text-muted-foreground">Score: {match.score}</p>
      )}
      {match.scheduled_at && (
        <p className="mt-1 text-[10px] text-muted-foreground flex items-center gap-1">
          <CalendarClock className="w-3 h-3" /> {new Date(match.scheduled_at).toLocaleString()}
        </p>
      )}
      {canSubmit && <MatchResultForm match={match} onSubmitResult={matchActions.onSubmitResult} />}
      {canManage && <MatchManagePanel match={match} actions={matchActions} />}
      {!canManage && isParticipant && done && <MatchDisputeButton matchId={match.id} />}
    </div>
  );
}

function RoundsRow({ rounds, finalRoundNumber, canManage, matchActions, currentUserId }) {
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
              <MatchCard key={m.id} match={m} canManage={canManage} matchActions={matchActions} currentUserId={currentUserId} />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function PairingPreview({ preview }) {
  if (!preview) return null;
  if (preview.error) {
    return (
      <p className="text-xs text-muted-foreground bg-muted/30 border border-border/60 rounded-lg px-3 py-2">
        {preview.error}
      </p>
    );
  }
  return (
    <div className="text-left rounded-lg border border-border/60 bg-muted/20 p-3 space-y-2">
      <p className="text-[11px] text-muted-foreground">
        {preview.player_count} checked-in players
        {preview.total_rounds != null && ` · ${preview.total_rounds} round${preview.total_rounds === 1 ? "" : "s"}`}
        {preview.num_groups != null && ` · ${preview.num_groups} groups`}
      </p>
      {preview.round1 && (
        <div className="space-y-1">
          {preview.round1.map((m, i) => (
            <div key={i} className="flex items-center justify-between text-xs px-2 py-1 rounded-md bg-background/60">
              <span className={!m.player1 ? "text-muted-foreground italic" : ""}>{m.player1?.name || "Bye"}</span>
              <span className="text-muted-foreground px-2">{m.is_bye ? "→ bye" : "vs"}</span>
              <span className={!m.player2 ? "text-muted-foreground italic" : ""}>{m.player2?.name || "Bye"}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function SeedingPanel({ id, onClose }) {
  const [regs, setRegs] = useState(null);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");

  useEffect(() => {
    api
      .get(`/api/tournaments/${id}/seeding/`)
      .then(setRegs)
      .catch((e) => setError(e.message || "Could not load seeding."));
  }, [id]);

  const setSeed = (regId, value) => {
    setRegs((prev) => prev.map((r) => (r.id === regId ? { ...r, seed: value === "" ? null : Number(value) } : r)));
  };

  const save = async () => {
    setSaving(true);
    setSaveError("");
    try {
      const payload = { seeds: regs.map((r) => ({ registration_id: r.id, seed: r.seed })) };
      const updated = await api.post(`/api/tournaments/${id}/seeding/`, payload);
      setRegs(updated);
    } catch (e) {
      setSaveError(e.message || "Could not save seeding.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="glass rounded-xl border border-border/60 p-4 text-left mb-4">
      <div className="flex items-center justify-between mb-3">
        <p className="text-xs font-heading font-bold uppercase tracking-wider text-muted-foreground">
          Manual Seeding
        </p>
        <button onClick={onClose} className="text-xs text-muted-foreground hover:text-foreground">
          Close
        </button>
      </div>
      <p className="text-xs text-muted-foreground mb-3">
        Lower numbers seed higher (seed 1 is top seed). Leave blank to fall back to registration order.
      </p>
      {error && <p className="text-xs text-destructive mb-3">{error}</p>}
      {!regs && !error && (
        <div className="flex justify-center py-6 text-muted-foreground">
          <Loader2 className="w-4 h-4 animate-spin" />
        </div>
      )}
      {regs && regs.length === 0 && (
        <p className="text-xs text-muted-foreground">No checked-in players yet.</p>
      )}
      {regs && regs.length > 0 && (
        <div className="space-y-1.5 mb-3">
          {regs.map((r) => (
            <div key={r.id} className="flex items-center justify-between gap-2 px-2 py-1.5 rounded-lg bg-muted/30">
              <span className="text-sm truncate">{r.team_name || r.player_email}</span>
              <input
                type="number"
                min={1}
                value={r.seed ?? ""}
                onChange={(e) => setSeed(r.id, e.target.value)}
                placeholder="—"
                className="w-16 px-2 py-1 rounded-md bg-background border border-border text-sm text-center outline-none focus:border-primary"
              />
            </div>
          ))}
        </div>
      )}
      {saveError && <p className="text-xs text-destructive mb-2">{saveError}</p>}
      {regs && regs.length > 0 && (
        <button
          onClick={save}
          disabled={saving}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-heading font-semibold bg-primary text-primary-foreground disabled:opacity-50"
        >
          {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : null}
          Save Seeding
        </button>
      )}
    </div>
  );
}

function ResetBracketPanel({ id, onReset }) {
  const [confirming, setConfirming] = useState(false);
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const submit = async () => {
    setSaving(true);
    setError("");
    try {
      const result = await api.post(`/api/tournaments/${id}/brackets/reset/`, { reason });
      if (result && result.detail) {
        setNotice(result.detail);
        setConfirming(false);
      } else {
        onReset();
      }
    } catch (e) {
      setError(e.message || "Could not reset the bracket.");
    } finally {
      setSaving(false);
    }
  };

  if (notice) {
    return (
      <div className="mt-8 text-sm text-primary bg-primary/10 border border-primary/30 rounded-lg px-3 py-2">
        {notice}
      </div>
    );
  }

  return (
    <div className="mt-8 pt-6 border-t border-border/40">
      {!confirming ? (
        <button
          onClick={() => setConfirming(true)}
          className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-destructive"
        >
          <RotateCcw className="w-3.5 h-3.5" /> Reset Bracket
        </button>
      ) : (
        <div className="rounded-xl border border-destructive/30 bg-destructive/5 p-4 max-w-md">
          <p className="text-sm font-heading font-semibold mb-1">Reset this bracket?</p>
          <p className="text-xs text-muted-foreground mb-3">
            This permanently deletes all matches. If any real result has already been recorded, this will instead be
            submitted for admin review.
          </p>
          <textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Reason for resetting (required)"
            rows={2}
            className="w-full text-xs px-2.5 py-2 rounded-lg bg-background border border-border outline-none focus:border-primary mb-2"
          />
          {error && <p className="text-xs text-destructive mb-2">{error}</p>}
          <div className="flex gap-2">
            <button
              onClick={submit}
              disabled={saving || !reason.trim()}
              className="px-3 py-1.5 rounded-lg text-xs font-heading font-semibold bg-destructive text-destructive-foreground disabled:opacity-50"
            >
              {saving ? "Resetting…" : "Confirm Reset"}
            </button>
            <button
              onClick={() => {
                setConfirming(false);
                setError("");
              }}
              className="px-3 py-1.5 rounded-lg text-xs font-heading font-semibold text-muted-foreground hover:text-foreground"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
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

function EliminationSections({ bracket, canManage, matchActions, currentUserId }) {
  const losersRounds = bracket.rounds.losers;
  const guaranteeRounds = bracket.rounds.guarantee;
  return (
    <div className="space-y-8">
      <div>
        <SectionLabel>Winners Bracket</SectionLabel>
        <RoundsRow rounds={bracket.rounds.winners} finalRoundNumber={bracket.total_rounds} canManage={canManage} matchActions={matchActions} currentUserId={currentUserId} />
      </div>
      <div>
        <SectionLabel>Losers Bracket</SectionLabel>
        <RoundsRow
          rounds={losersRounds}
          finalRoundNumber={losersRounds.length ? losersRounds[losersRounds.length - 1].round_number : null}
          canManage={canManage}
          matchActions={matchActions}
          currentUserId={currentUserId}
        />
      </div>
      {guaranteeRounds && guaranteeRounds.length > 0 && (
        <div>
          <SectionLabel>Guarantee Round</SectionLabel>
          <RoundsRow rounds={guaranteeRounds} finalRoundNumber={null} canManage={canManage} matchActions={matchActions} currentUserId={currentUserId} />
        </div>
      )}
      <div>
        <SectionLabel>Grand Final</SectionLabel>
        <RoundsRow rounds={bracket.rounds.grand_final} finalRoundNumber={1} canManage={canManage} matchActions={matchActions} currentUserId={currentUserId} />
      </div>
    </div>
  );
}

export default function BracketPage() {
  const { id } = useParams();
  const { user } = useAuth();
  const location = useLocation();
  const backToTournamentState = { from: location.state?.from };

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
  const [preview, setPreview] = useState(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState("");
  const [showSeeding, setShowSeeding] = useState(false);

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

  const previewMatchups = async () => {
    setPreviewLoading(true);
    setPreviewError("");
    try {
      const p = await api.get(`/api/tournaments/${id}/brackets/preview/`, {
        query: { bracket_format: genFormat },
      });
      setPreview(p);
    } catch (e) {
      setPreviewError(e.message || "Could not load a preview.");
    } finally {
      setPreviewLoading(false);
    }
  };

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

  const forfeitMatch = async (matchId, payload) => {
    await api.post(`/api/matches/${matchId}/forfeit/`, payload);
    loadBracket();
  };

  const overrideMatch = async (matchId, payload) => {
    await api.patch(`/api/matches/${matchId}/override/`, payload);
    loadBracket();
  };

  const scheduleMatch = async (matchId, payload) => {
    await api.patch(`/api/matches/${matchId}/schedule/`, payload);
    loadBracket();
  };

  const matchActions = {
    onSubmitResult: submitMatchResult,
    onForfeit: forfeitMatch,
    onOverride: overrideMatch,
    onSchedule: scheduleMatch,
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
        <Link to={`/tournaments/${id}`} state={backToTournamentState} className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-primary mb-6">
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
        <Link to={`/tournaments/${id}`} state={backToTournamentState} className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-primary">
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
                onClick={() => {
                  setGenFormat(f.key);
                  setPreview(null);
                  setPreviewError("");
                }}
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
              Works with any number of players (minimum 4) — byes are seeded in automatically to fill out the bracket.
            </p>
          )}
          {genFormat === "guarantee3" && (
            <p className="text-xs text-muted-foreground mb-4">
              Works with any number of players (minimum 8) — byes are seeded in automatically to fill out the bracket.
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

          <div className="mb-4">
            <button
              onClick={() => setShowSeeding((v) => !v)}
              className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-primary"
            >
              <ArrowUpDown className="w-3.5 h-3.5" /> {showSeeding ? "Hide manual seeding" : "Manage manual seeding"}
            </button>
          </div>
          {showSeeding && <SeedingPanel id={id} onClose={() => setShowSeeding(false)} />}

          {genError && (
            <div className="mb-4 text-sm text-destructive bg-destructive/10 border border-destructive/30 rounded-lg px-3 py-2 inline-block">
              {genError}
            </div>
          )}
          <div className="flex items-center justify-center gap-2 mb-4">
            <button
              onClick={generateBracket}
              disabled={genSaving}
              className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-heading font-semibold bg-primary text-primary-foreground disabled:opacity-50"
            >
              {genSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Swords className="w-4 h-4" />}
              Generate Bracket
            </button>
            <button
              onClick={previewMatchups}
              disabled={previewLoading}
              className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-heading font-semibold border border-border hover:border-primary disabled:opacity-50"
            >
              {previewLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Eye className="w-4 h-4" />}
              Preview Matchups
            </button>
          </div>

          {previewError && (
            <p className="text-xs text-destructive mb-4">{previewError}</p>
          )}
          {preview && <PairingPreview preview={preview} />}
        </div>
      )}

      {bracketState === "error" && (
        <div className="text-sm text-destructive bg-destructive/10 border border-destructive/30 rounded-lg px-3 py-2">
          Could not load the bracket.
        </div>
      )}

      {bracketState === "ready" && bracket && (bracket.format === "double" || bracket.format === "guarantee3") && (
        <EliminationSections bracket={bracket} canManage={tournament.can_manage} matchActions={matchActions} currentUserId={user?.id} />
      )}

      {bracketState === "ready" && bracket && (bracket.format === "round_robin" || bracket.format === "swiss") && (
        <div className="space-y-8">
          <RoundsRow rounds={bracket.rounds} finalRoundNumber={bracket.total_rounds} canManage={tournament.can_manage} matchActions={matchActions} currentUserId={user?.id} />

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
                  <RoundsRow rounds={rounds} finalRoundNumber={null} canManage={tournament.can_manage} matchActions={matchActions} currentUserId={user?.id} />
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
                matchActions={matchActions}
                currentUserId={user?.id}
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
        <RoundsRow rounds={bracket.rounds} finalRoundNumber={bracket.total_rounds} canManage={tournament.can_manage} matchActions={matchActions} currentUserId={user?.id} />
      )}

      {bracketState === "ready" && bracket && tournament.can_manage && (
        <ResetBracketPanel
          id={id}
          onReset={() => {
            setBracket(null);
            setBracketState("none");
          }}
        />
      )}
    </div>
  );
}
