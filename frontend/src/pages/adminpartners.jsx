import React, { useEffect, useState } from "react";
import { Plus, Pencil, Trash2, Loader2, X, Check } from "lucide-react";
import { api } from "@/lib/api";

const EMPTY_FORM = { name: "", logo_url: "", website_url: "", description: "", display_order: 0, is_active: true };

export default function AdminPartners() {
  const [partners, setPartners] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [editingId, setEditingId] = useState(null); // null | "new" | id
  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [deletingId, setDeletingId] = useState(null);

  const load = () => {
    setLoading(true);
    api
      .get("/api/partners/")
      .then(setPartners)
      .catch((e) => setError(e.message || "Failed to load partners."))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const startEdit = (p) => {
    setEditingId(p.id);
    setForm({
      name: p.name, logo_url: p.logo_url, website_url: p.website_url,
      description: p.description, display_order: p.display_order, is_active: p.is_active,
    });
  };

  const startNew = () => {
    setEditingId("new");
    setForm(EMPTY_FORM);
  };

  const cancel = () => {
    setEditingId(null);
    setForm(EMPTY_FORM);
  };

  const save = async () => {
    setSaving(true);
    setError("");
    try {
      const payload = { ...form, display_order: Number(form.display_order) || 0 };
      if (editingId === "new") {
        const created = await api.post("/api/partners/", payload);
        setPartners((list) => [...list, created]);
      } else {
        const updated = await api.patch(`/api/partners/${editingId}/`, payload);
        setPartners((list) => list.map((p) => (p.id === editingId ? updated : p)));
      }
      cancel();
    } catch (e) {
      setError(e.message || "Could not save partner.");
    } finally {
      setSaving(false);
    }
  };

  const remove = async (id) => {
    setError("");
    try {
      await api.delete(`/api/partners/${id}/`);
      setPartners((list) => list.filter((p) => p.id !== id));
    } catch (e) {
      setError(e.message || "Could not delete partner.");
    } finally {
      setDeletingId(null);
    }
  };

  const Row = ({ p }) => (
    <tr className="border-b border-border/40 last:border-0">
      <td className="px-4 py-3 font-medium">{p.name}</td>
      <td className="px-4 py-3 text-muted-foreground truncate max-w-[200px]">{p.website_url || "—"}</td>
      <td className="px-4 py-3 text-muted-foreground">{p.display_order}</td>
      <td className="px-4 py-3">
        <span className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded-full ${p.is_active ? "bg-primary/20 text-primary" : "bg-muted text-muted-foreground"}`}>
          {p.is_active ? "Active" : "Inactive"}
        </span>
      </td>
      <td className="px-4 py-3">
        <div className="flex items-center gap-2 justify-end">
          {deletingId === p.id ? (
            <>
              <button onClick={() => remove(p.id)} className="text-xs font-heading font-semibold text-destructive">Confirm delete</button>
              <button onClick={() => setDeletingId(null)} className="text-xs text-muted-foreground">Cancel</button>
            </>
          ) : (
            <>
              <button onClick={() => startEdit(p)} className="p-1.5 rounded-lg hover:bg-muted text-muted-foreground hover:text-primary">
                <Pencil className="w-4 h-4" />
              </button>
              <button onClick={() => setDeletingId(p.id)} className="p-1.5 rounded-lg hover:bg-muted text-muted-foreground hover:text-destructive">
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
      <td colSpan={5} className="px-4 py-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <input placeholder="Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className="px-3 py-2 rounded-lg bg-muted/40 border border-border text-sm outline-none focus:border-primary" />
          <input placeholder="Logo URL" value={form.logo_url} onChange={(e) => setForm({ ...form, logo_url: e.target.value })} className="px-3 py-2 rounded-lg bg-muted/40 border border-border text-sm outline-none focus:border-primary" />
          <input placeholder="Website URL" value={form.website_url} onChange={(e) => setForm({ ...form, website_url: e.target.value })} className="px-3 py-2 rounded-lg bg-muted/40 border border-border text-sm outline-none focus:border-primary" />
          <input type="number" placeholder="Display order" value={form.display_order} onChange={(e) => setForm({ ...form, display_order: e.target.value })} className="px-3 py-2 rounded-lg bg-muted/40 border border-border text-sm outline-none focus:border-primary" />
          <textarea placeholder="Description" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} className="sm:col-span-2 px-3 py-2 rounded-lg bg-muted/40 border border-border text-sm outline-none focus:border-primary resize-none" rows={2} />
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
      <div className="flex justify-end">
        <button onClick={startNew} className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-sm font-heading font-semibold bg-primary text-primary-foreground">
          <Plus className="w-4 h-4" /> Add Partner
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
              <th className="px-4 py-3 font-heading font-semibold">Website</th>
              <th className="px-4 py-3 font-heading font-semibold">Order</th>
              <th className="px-4 py-3 font-heading font-semibold">Status</th>
              <th className="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody>
            {editingId === "new" && <Form />}
            {loading ? (
              <tr><td colSpan={5} className="px-4 py-8 text-center text-muted-foreground"><Loader2 className="w-5 h-5 animate-spin inline-block" /></td></tr>
            ) : partners.length === 0 && editingId !== "new" ? (
              <tr><td colSpan={5} className="px-4 py-8 text-center text-muted-foreground">No partners yet.</td></tr>
            ) : (
              partners.map((p) => (editingId === p.id ? <Form key={p.id} /> : <Row key={p.id} p={p} />))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
