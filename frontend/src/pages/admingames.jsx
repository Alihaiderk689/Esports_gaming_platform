import React, { useEffect, useState } from "react";
import { Plus, Pencil, Trash2, Loader2, X, Check, Gamepad2 } from "lucide-react";
import { api } from "@/lib/api";

const EMPTY_FORM = {
  name: "", genre: "", platform: "", description: "", cover_image_url: "", is_active: true,
};

function CategoryManager({ categories, onCreate, onDelete }) {
  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);
  const [deletingId, setDeletingId] = useState(null);
  const [error, setError] = useState("");

  const submit = async (e) => {
    e.preventDefault();
    if (!name.trim()) return;
    setSaving(true);
    setError("");
    try {
      await onCreate(name.trim());
      setName("");
    } catch (err) {
      setError(err.message || "Could not create category.");
    } finally {
      setSaving(false);
    }
  };

  const remove = async (id) => {
    setDeletingId(id);
    try {
      await onDelete(id);
    } catch {
      /* best effort */
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <div className="glass rounded-xl border border-border/60 p-4">
      <h3 className="font-heading font-bold text-sm mb-3">Game Categories</h3>
      <div className="flex flex-wrap gap-2 mb-3">
        {categories.length === 0 ? (
          <span className="text-xs text-muted-foreground">No categories yet.</span>
        ) : (
          categories.map((c) => (
            <span
              key={c.id}
              className="inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full bg-muted/40 border border-border"
            >
              {c.name}
              <button
                onClick={() => remove(c.id)}
                disabled={deletingId === c.id}
                className="text-muted-foreground hover:text-destructive transition-colors"
              >
                {deletingId === c.id ? <Loader2 className="w-3 h-3 animate-spin" /> : <X className="w-3 h-3" />}
              </button>
            </span>
          ))
        )}
      </div>
      <form onSubmit={submit} className="flex gap-2">
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="New category, e.g. FPS"
          className="flex-1 px-3 py-1.5 rounded-lg bg-muted/40 border border-border text-sm outline-none focus:border-primary"
        />
        <button
          type="submit"
          disabled={saving || !name.trim()}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-heading font-semibold bg-primary text-primary-foreground disabled:opacity-50"
        >
          {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />} Add
        </button>
      </form>
      {error && <p className="mt-2 text-xs text-destructive">{error}</p>}
    </div>
  );
}

export default function AdminGames() {
  const [games, setGames] = useState([]);
  const [categories, setCategories] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [editingId, setEditingId] = useState(null); // null | "new" | id
  const [form, setForm] = useState(EMPTY_FORM);
  const [logoFile, setLogoFile] = useState(null);
  const [selectedCategoryIds, setSelectedCategoryIds] = useState([]);
  const [saving, setSaving] = useState(false);
  const [deletingId, setDeletingId] = useState(null);

  const load = () => {
    setLoading(true);
    Promise.all([api.get("/api/games/"), api.get("/api/games/categories/")])
      .then(([g, c]) => {
        setGames(g);
        setCategories(c);
      })
      .catch((e) => setError(e.message || "Failed to load games."))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const createCategory = async (name) => {
    const created = await api.post("/api/games/categories/", { name });
    setCategories((list) => [...list, created].sort((a, b) => a.name.localeCompare(b.name)));
  };

  const deleteCategory = async (id) => {
    await api.delete(`/api/games/categories/${id}/`);
    setCategories((list) => list.filter((c) => c.id !== id));
  };

  const startEdit = (game) => {
    setEditingId(game.id);
    setForm({
      name: game.name, genre: game.genre, platform: game.platform,
      description: game.description, cover_image_url: game.cover_image_url, is_active: game.is_active,
    });
    setSelectedCategoryIds(game.categories.map((c) => c.id));
    setLogoFile(null);
  };

  const startNew = () => {
    setEditingId("new");
    setForm(EMPTY_FORM);
    setSelectedCategoryIds([]);
    setLogoFile(null);
  };

  const cancel = () => {
    setEditingId(null);
    setForm(EMPTY_FORM);
    setSelectedCategoryIds([]);
    setLogoFile(null);
  };

  const toggleCategory = (id) => {
    setSelectedCategoryIds((ids) => (ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id]));
  };

  const save = async () => {
    setSaving(true);
    setError("");
    try {
      const formData = new FormData();
      Object.entries(form).forEach(([key, value]) => formData.append(key, value));
      selectedCategoryIds.forEach((id) => formData.append("category_ids", id));
      if (logoFile) formData.append("logo", logoFile);

      if (editingId === "new") {
        const created = await api.post("/api/games/", formData, { formData: true });
        setGames((list) => [...list, created].sort((a, b) => a.name.localeCompare(b.name)));
      } else {
        const updated = await api.patch(`/api/games/${editingId}/`, formData, { formData: true });
        setGames((list) => list.map((g) => (g.id === editingId ? updated : g)));
      }
      cancel();
    } catch (e) {
      setError(e.message || "Could not save game.");
    } finally {
      setSaving(false);
    }
  };

  const remove = async (id) => {
    setError("");
    try {
      await api.delete(`/api/games/${id}/`);
      setGames((list) => list.filter((g) => g.id !== id));
    } catch (e) {
      setError(e.message || "Could not delete game.");
    } finally {
      setDeletingId(null);
    }
  };

  const Row = ({ game }) => (
    <tr className="border-b border-border/40 last:border-0">
      <td className="px-4 py-3">
        <div className="flex items-center gap-3">
          {game.logo_url ? (
            <img src={game.logo_url} alt="" className="w-8 h-8 rounded-lg object-cover shrink-0" />
          ) : (
            <div className="w-8 h-8 rounded-lg bg-muted grid place-items-center shrink-0">
              <Gamepad2 className="w-4 h-4 text-muted-foreground" />
            </div>
          )}
          <span className="font-medium">{game.name}</span>
        </div>
      </td>
      <td className="px-4 py-3 text-muted-foreground">{game.genre || "—"}</td>
      <td className="px-4 py-3 text-muted-foreground">
        {game.categories.length > 0 ? game.categories.map((c) => c.name).join(", ") : "—"}
      </td>
      <td className="px-4 py-3 text-muted-foreground">{game.platform || "—"}</td>
      <td className="px-4 py-3">
        <span className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded-full ${game.is_active ? "bg-primary/20 text-primary" : "bg-muted text-muted-foreground"}`}>
          {game.is_active ? "Active" : "Inactive"}
        </span>
      </td>
      <td className="px-4 py-3">
        <div className="flex items-center gap-2 justify-end">
          {deletingId === game.id ? (
            <>
              <button onClick={() => remove(game.id)} className="text-xs font-heading font-semibold text-destructive">Confirm delete</button>
              <button onClick={() => setDeletingId(null)} className="text-xs text-muted-foreground">Cancel</button>
            </>
          ) : (
            <>
              <button onClick={() => startEdit(game)} className="p-1.5 rounded-lg hover:bg-muted text-muted-foreground hover:text-primary">
                <Pencil className="w-4 h-4" />
              </button>
              <button onClick={() => setDeletingId(game.id)} className="p-1.5 rounded-lg hover:bg-muted text-muted-foreground hover:text-destructive">
                <Trash2 className="w-4 h-4" />
              </button>
            </>
          )}
        </div>
      </td>
    </tr>
  );

  const Form = () => (
    <tr className="border-b border-border/40 bg-muted/20">
      <td colSpan={6} className="px-4 py-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <input placeholder="Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className="px-3 py-2 rounded-lg bg-muted/40 border border-border text-sm outline-none focus:border-primary" />
          <input placeholder="Genre" value={form.genre} onChange={(e) => setForm({ ...form, genre: e.target.value })} className="px-3 py-2 rounded-lg bg-muted/40 border border-border text-sm outline-none focus:border-primary" />
          <input placeholder="Platform" value={form.platform} onChange={(e) => setForm({ ...form, platform: e.target.value })} className="px-3 py-2 rounded-lg bg-muted/40 border border-border text-sm outline-none focus:border-primary" />
          <input placeholder="Cover image URL (fallback if no logo uploaded)" value={form.cover_image_url} onChange={(e) => setForm({ ...form, cover_image_url: e.target.value })} className="px-3 py-2 rounded-lg bg-muted/40 border border-border text-sm outline-none focus:border-primary" />
          <textarea placeholder="Description" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} className="sm:col-span-2 px-3 py-2 rounded-lg bg-muted/40 border border-border text-sm outline-none focus:border-primary resize-none" rows={2} />

          <div className="sm:col-span-2">
            <label className="block text-xs font-heading font-bold uppercase tracking-wider text-muted-foreground mb-2">
              Logo
            </label>
            <input
              type="file"
              accept="image/*"
              onChange={(e) => setLogoFile(e.target.files?.[0] || null)}
              className="w-full text-xs text-muted-foreground file:mr-3 file:px-3 file:py-1.5 file:rounded-lg file:border-0 file:bg-primary file:text-primary-foreground file:text-xs file:font-heading file:font-semibold"
            />
          </div>

          <div className="sm:col-span-2">
            <label className="block text-xs font-heading font-bold uppercase tracking-wider text-muted-foreground mb-2">
              Categories
            </label>
            <div className="flex flex-wrap gap-1.5">
              {categories.length === 0 ? (
                <span className="text-xs text-muted-foreground">No categories yet — add one below the table.</span>
              ) : (
                categories.map((c) => (
                  <button
                    key={c.id}
                    type="button"
                    onClick={() => toggleCategory(c.id)}
                    className={`px-2.5 py-1 rounded-full text-xs font-heading font-semibold transition-colors ${
                      selectedCategoryIds.includes(c.id) ? "bg-primary text-primary-foreground" : "bg-muted/40 border border-border text-muted-foreground"
                    }`}
                  >
                    {c.name}
                  </button>
                ))
              )}
            </div>
          </div>

          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} />
            Active
          </label>
        </div>
        <div className="flex gap-2 mt-3">
          <button onClick={save} disabled={saving || !form.name} className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-heading font-semibold bg-primary text-primary-foreground disabled:opacity-50">
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />} Save
          </button>
          <button onClick={cancel} className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-heading font-semibold bg-muted text-muted-foreground">
            <X className="w-4 h-4" /> Cancel
          </button>
        </div>
      </td>
    </tr>
  );

  return (
    <div className="space-y-4">
      <CategoryManager categories={categories} onCreate={createCategory} onDelete={deleteCategory} />

      <div className="flex justify-end">
        <button onClick={startNew} className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-sm font-heading font-semibold bg-primary text-primary-foreground">
          <Plus className="w-4 h-4" /> Add Game
        </button>
      </div>

      {error && (
        <div className="text-sm text-destructive bg-destructive/10 border border-destructive/30 rounded-lg px-3 py-2">{error}</div>
      )}

      <div className="glass rounded-xl border border-border/60 overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border/60 text-left text-muted-foreground">
              <th className="px-4 py-3 font-heading font-semibold">Name</th>
              <th className="px-4 py-3 font-heading font-semibold">Genre</th>
              <th className="px-4 py-3 font-heading font-semibold">Categories</th>
              <th className="px-4 py-3 font-heading font-semibold">Platform</th>
              <th className="px-4 py-3 font-heading font-semibold">Status</th>
              <th className="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody>
            {editingId === "new" && <Form />}
            {loading ? (
              <tr><td colSpan={6} className="px-4 py-8 text-center text-muted-foreground"><Loader2 className="w-5 h-5 animate-spin inline-block" /></td></tr>
            ) : games.length === 0 && editingId !== "new" ? (
              <tr><td colSpan={6} className="px-4 py-8 text-center text-muted-foreground">No games yet.</td></tr>
            ) : (
              games.map((g) => (editingId === g.id ? <Form key={g.id} /> : <Row key={g.id} game={g} />))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
