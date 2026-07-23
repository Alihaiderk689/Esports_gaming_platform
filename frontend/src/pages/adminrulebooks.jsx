import React, { useEffect, useState } from "react";
import { Upload, Trash2, Loader2, FileText, CheckCircle2, Clock } from "lucide-react";
import { api } from "@/lib/api";

export default function AdminRulebooks() {
  const [rulebooks, setRulebooks] = useState([]);
  const [games, setGames] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [deletingId, setDeletingId] = useState(null);

  const [gameId, setGameId] = useState("");
  const [title, setTitle] = useState("");
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);

  const load = () => {
    setLoading(true);
    Promise.all([api.get("/api/rules/"), api.get("/api/games/")])
      .then(([rules, gamesList]) => {
        setRulebooks(rules);
        setGames(gamesList);
      })
      .catch((e) => setError(e.message || "Failed to load rulebooks."))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const gameName = (id) => games.find((g) => g.id === id)?.name || `Game #${id}`;

  const upload = async (e) => {
    e.preventDefault();
    if (!gameId || !title || !file) return;
    setUploading(true);
    setError("");
    try {
      const formData = new FormData();
      formData.append("game", gameId);
      formData.append("title", title);
      formData.append("pdf", file);
      const created = await api.post("/api/rules/upload/", formData, { formData: true });
      setRulebooks((list) => [created, ...list]);
      setGameId("");
      setTitle("");
      setFile(null);
      e.target.reset();
    } catch (err) {
      setError(err.message || "Could not upload rulebook.");
    } finally {
      setUploading(false);
    }
  };

  const remove = async (id) => {
    setError("");
    try {
      await api.delete(`/api/rules/${id}/delete/`);
      setRulebooks((list) => list.filter((r) => r.id !== id));
    } catch (e) {
      setError(e.message || "Could not delete rulebook.");
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <div className="space-y-6">
      <form onSubmit={upload} className="glass rounded-xl border border-border/60 p-5">
        <h2 className="font-heading font-bold text-sm uppercase tracking-wider text-muted-foreground mb-4">
          Upload rulebook
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <select
            value={gameId}
            onChange={(e) => setGameId(e.target.value)}
            required
            className="px-3 py-2 rounded-lg bg-muted/40 border border-border text-sm outline-none focus:border-primary"
          >
            <option value="">Select a game…</option>
            {games.map((g) => (
              <option key={g.id} value={g.id}>{g.name}</option>
            ))}
          </select>
          <input
            placeholder="Title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            required
            className="px-3 py-2 rounded-lg bg-muted/40 border border-border text-sm outline-none focus:border-primary"
          />
          <input
            type="file"
            accept="application/pdf"
            onChange={(e) => setFile(e.target.files?.[0] || null)}
            required
            className="text-sm text-muted-foreground file:mr-3 file:px-3 file:py-1.5 file:rounded-lg file:border-0 file:bg-primary file:text-primary-foreground file:text-sm file:font-heading file:font-semibold"
          />
        </div>
        <button
          type="submit"
          disabled={uploading || !gameId || !title || !file}
          className="mt-4 inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-sm font-heading font-semibold bg-primary text-primary-foreground disabled:opacity-50"
        >
          {uploading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
          Upload
        </button>
      </form>

      {error && (
        <div className="text-sm text-destructive bg-destructive/10 border border-destructive/30 rounded-lg px-3 py-2">{error}</div>
      )}

      <div className="glass rounded-xl border border-border/60 overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border/60 text-left text-muted-foreground">
              <th className="px-4 py-3 font-heading font-semibold">Title</th>
              <th className="px-4 py-3 font-heading font-semibold">Game</th>
              <th className="px-4 py-3 font-heading font-semibold">Status</th>
              <th className="px-4 py-3 font-heading font-semibold">Uploaded</th>
              <th className="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={5} className="px-4 py-8 text-center text-muted-foreground"><Loader2 className="w-5 h-5 animate-spin inline-block" /></td></tr>
            ) : rulebooks.length === 0 ? (
              <tr><td colSpan={5} className="px-4 py-8 text-center text-muted-foreground">No rulebooks uploaded yet.</td></tr>
            ) : (
              rulebooks.map((r) => (
                <tr key={r.id} className="border-b border-border/40 last:border-0">
                  <td className="px-4 py-3">
                    <a href={r.pdf_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1.5 hover:text-primary">
                      <FileText className="w-4 h-4" /> {r.title}
                    </a>
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">{gameName(r.game)}</td>
                  <td className="px-4 py-3">
                    {r.is_processed ? (
                      <span className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full bg-primary/10 text-primary">
                        <CheckCircle2 className="w-3 h-3" /> Ready
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full bg-muted text-muted-foreground">
                        <Clock className="w-3 h-3" /> Processing
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">{new Date(r.uploaded_at).toLocaleDateString()}</td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2 justify-end">
                      {deletingId === r.id ? (
                        <>
                          <button onClick={() => remove(r.id)} className="text-xs font-heading font-semibold text-destructive">Confirm delete</button>
                          <button onClick={() => setDeletingId(null)} className="text-xs text-muted-foreground">Cancel</button>
                        </>
                      ) : (
                        <button onClick={() => setDeletingId(r.id)} className="p-1.5 rounded-lg hover:bg-muted text-muted-foreground hover:text-destructive">
                          <Trash2 className="w-4 h-4" />
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
