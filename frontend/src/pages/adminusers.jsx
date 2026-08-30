import React, { useEffect, useState } from "react";
import { Search, Loader2, CheckCircle2, XCircle } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/appauth";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";

function Toggle({ on, onClick, disabled }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`relative w-9 h-5 rounded-full transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${
        on ? "bg-primary" : "bg-muted"
      }`}
    >
      <span
        className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-background shadow transition-transform ${
          on ? "translate-x-4" : "translate-x-0"
        }`}
      />
    </button>
  );
}

function InfoRow({ label, value }) {
  return (
    <div>
      <p className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="text-sm">{value || "—"}</p>
    </div>
  );
}

const formatDateTime = (iso) => (iso ? new Date(iso).toLocaleString() : "—");

function UserDetailDialog({ user, onClose, onToggle, saving, isSelf }) {
  return (
    <Dialog open={!!user} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{[user?.first_name, user?.last_name].filter(Boolean).join(" ") || user?.email}</DialogTitle>
        </DialogHeader>
        {user && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <InfoRow label="Email" value={user.email} />
              <InfoRow label="Name" value={[user.first_name, user.last_name].filter(Boolean).join(" ")} />
              <InfoRow label="Email verified" value={user.is_email_verified ? "Yes" : "No"} />
              <InfoRow label="Signed up with Google" value={user.signed_up_with_google ? "Yes" : "No"} />
              <InfoRow label="Joined" value={formatDateTime(user.date_joined)} />
              <InfoRow label="Last login" value={formatDateTime(user.last_login)} />
              <InfoRow label="Organizer" value={user.is_organizer ? (user.organizer_company_name || "Yes") : "No"} />
              {user.is_organizer && <InfoRow label="Organizer status" value={user.organizer_status} />}
            </div>

            <div className="pt-3 border-t border-border/60 flex items-center justify-between">
              <span className="text-sm font-heading font-semibold">Active</span>
              <Toggle on={user.is_active} disabled={saving || isSelf} onClick={() => onToggle(user, "is_active")} />
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm font-heading font-semibold">Staff / Admin</span>
              <Toggle on={user.is_staff} disabled={saving || isSelf} onClick={() => onToggle(user, "is_staff")} />
            </div>
            {isSelf && (
              <p className="text-xs text-muted-foreground">You can't change your own admin access.</p>
            )}

            <div className="pt-2 border-t border-border/60">
              <button
                onClick={onClose}
                className="px-3 py-1.5 rounded-lg text-sm font-heading font-semibold bg-muted hover:bg-muted/70 transition-colors"
              >
                Back
              </button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

export default function AdminUsers() {
  const { user: me } = useAuth();
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [hasNext, setHasNext] = useState(false);
  const [hasPrevious, setHasPrevious] = useState(false);
  const [error, setError] = useState("");
  const [savingId, setSavingId] = useState(null);
  const [detailUser, setDetailUser] = useState(null);

  const load = (q, p) => {
    setLoading(true);
    api
      .get("/api/admin/users/", { query: { search: q, page: p } })
      .then((data) => {
        const results = Array.isArray(data) ? data : data.results;
        setUsers(results);
        setHasNext(Boolean(data && !Array.isArray(data) && data.next));
        setHasPrevious(Boolean(data && !Array.isArray(data) && data.previous));
      })
      .catch((e) => setError(e.message || "Failed to load users."))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    const t = setTimeout(() => load(search, page), 300);
    return () => clearTimeout(t);
  }, [search, page]);

  const toggle = async (u, field) => {
    setSavingId(u.id);
    setError("");
    try {
      const updated = await api.patch(`/api/admin/users/${u.id}/`, { [field]: !u[field] });
      setUsers((list) => list.map((x) => (x.id === u.id ? updated : x)));
      setDetailUser((d) => (d && d.id === u.id ? updated : d));
    } catch (e) {
      setError(e.message || "Could not update user.");
    } finally {
      setSavingId(null);
    }
  };

  return (
    <div className="space-y-4">
      <div className="relative max-w-sm">
        <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
        <input
          value={search}
          onChange={(e) => { setSearch(e.target.value); setPage(1); }}
          placeholder="Search by email or name…"
          className="w-full pl-10 pr-4 py-2.5 rounded-xl bg-muted/40 border border-border text-sm outline-none focus:border-primary focus:neon-border transition-all placeholder:text-muted-foreground/70"
        />
      </div>

      {error && (
        <div className="text-sm text-destructive bg-destructive/10 border border-destructive/30 rounded-lg px-3 py-2">
          {error}
        </div>
      )}

      <div className="glass rounded-xl border border-border/60 overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border/60 text-left text-muted-foreground">
              <th className="px-4 py-3 font-heading font-semibold">Email</th>
              <th className="px-4 py-3 font-heading font-semibold">Name</th>
              <th className="px-4 py-3 font-heading font-semibold">Verified</th>
              <th className="px-4 py-3 font-heading font-semibold">Active</th>
              <th className="px-4 py-3 font-heading font-semibold">Staff</th>
              <th className="px-4 py-3 font-heading font-semibold">Joined</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-muted-foreground">
                  <Loader2 className="w-5 h-5 animate-spin inline-block" />
                </td>
              </tr>
            ) : users.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-muted-foreground">
                  No users found.
                </td>
              </tr>
            ) : (
              users.map((u) => (
                <tr key={u.id} className="border-b border-border/40 last:border-0">
                  <td
                    onClick={() => setDetailUser(u)}
                    className="px-4 py-3 cursor-pointer hover:text-primary transition-colors"
                  >
                    {u.email}
                  </td>
                  <td
                    onClick={() => setDetailUser(u)}
                    className="px-4 py-3 text-muted-foreground cursor-pointer hover:text-primary transition-colors"
                  >
                    {[u.first_name, u.last_name].filter(Boolean).join(" ") || "—"}
                  </td>
                  <td className="px-4 py-3">
                    {u.is_email_verified ? (
                      <CheckCircle2 className="w-4 h-4 text-primary" />
                    ) : (
                      <XCircle className="w-4 h-4 text-muted-foreground" />
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <Toggle on={u.is_active} disabled={savingId === u.id || u.id === me?.id} onClick={() => toggle(u, "is_active")} />
                  </td>
                  <td className="px-4 py-3">
                    <Toggle on={u.is_staff} disabled={savingId === u.id || u.id === me?.id} onClick={() => toggle(u, "is_staff")} />
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {new Date(u.date_joined).toLocaleDateString()}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {!loading && (hasNext || hasPrevious) && (
        <div className="flex items-center justify-center gap-3 pt-2">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={!hasPrevious}
            className="px-3 py-1.5 rounded-lg text-sm font-heading font-semibold bg-muted/40 border border-border/60 disabled:opacity-40"
          >
            Previous
          </button>
          <span className="text-sm text-muted-foreground">Page {page}</span>
          <button
            onClick={() => setPage((p) => p + 1)}
            disabled={!hasNext}
            className="px-3 py-1.5 rounded-lg text-sm font-heading font-semibold bg-muted/40 border border-border/60 disabled:opacity-40"
          >
            Next
          </button>
        </div>
      )}

      <UserDetailDialog
        user={detailUser}
        onClose={() => setDetailUser(null)}
        onToggle={toggle}
        saving={detailUser ? savingId === detailUser.id : false}
        isSelf={detailUser ? detailUser.id === me?.id : false}
      />
    </div>
  );
}
