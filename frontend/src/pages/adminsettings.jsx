import React, { useEffect, useState } from "react";
import { Lock, ArrowRight, Loader2, ShieldCheck, Eye, EyeOff, UserCircle } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/appauth";

function ProfileCard() {
  const { refreshUser } = useAuth();
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    api
      .get("/api/players/me/")
      .then((p) => {
        setFirstName(p.first_name || "");
        setLastName(p.last_name || "");
      })
      .catch((e) => setLoadError(e.message || "Could not load your profile."))
      .finally(() => setLoading(false));
  }, []);

  const submit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError("");
    setSuccess(false);
    try {
      await api.patch("/api/players/me/", { first_name: firstName, last_name: lastName });
      setSuccess(true);
      refreshUser();
    } catch (err) {
      setError(err.message || "Could not update your profile.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="glass rounded-2xl border border-border/60 p-6 sm:p-8">
      <div className="w-11 h-11 rounded-xl bg-gradient-to-br from-primary to-green-500 grid place-items-center neon-border mb-5">
        <UserCircle className="w-6 h-6 text-background" strokeWidth={2.5} />
      </div>
      <h2 className="font-display font-bold text-xl mb-1">Profile</h2>
      <p className="text-sm text-muted-foreground mb-6">Your display name.</p>

      {loading ? (
        <div className="flex justify-center py-8 text-muted-foreground">
          <Loader2 className="w-5 h-5 animate-spin" />
        </div>
      ) : loadError ? (
        <div className="text-sm text-destructive bg-destructive/10 border border-destructive/30 rounded-lg px-3 py-2">
          {loadError}
        </div>
      ) : (
        <form onSubmit={submit} className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <input
              value={firstName}
              onChange={(e) => setFirstName(e.target.value)}
              placeholder="First name"
              className="px-3.5 py-2.5 rounded-xl bg-muted/40 border border-border text-sm outline-none focus:border-primary"
            />
            <input
              value={lastName}
              onChange={(e) => setLastName(e.target.value)}
              placeholder="Last name"
              className="px-3.5 py-2.5 rounded-xl bg-muted/40 border border-border text-sm outline-none focus:border-primary"
            />
          </div>

          {error && (
            <div className="text-sm text-destructive bg-destructive/10 border border-destructive/30 rounded-lg px-3 py-2">
              {error}
            </div>
          )}
          {success && (
            <div className="text-sm text-primary bg-primary/10 border border-primary/30 rounded-lg px-3 py-2">
              Profile updated.
            </div>
          )}

          <button
            type="submit"
            disabled={saving}
            className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl font-heading font-bold text-sm bg-primary text-primary-foreground hover:shadow-[0_0_28px_hsl(186_100%_50%/0.5)] transition-shadow disabled:opacity-50"
          >
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : "Save changes"}
          </button>
        </form>
      )}
    </div>
  );
}

export default function AdminSettings() {
  const { user } = useAuth();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    setSuccess(false);
    if (newPassword !== confirm) {
      setError("New passwords do not match.");
      return;
    }
    setLoading(true);
    try {
      await api.post("/api/auth/change-password/", {
        current_password: currentPassword,
        new_password: newPassword,
      });
      setCurrentPassword("");
      setNewPassword("");
      setConfirm("");
      setSuccess(true);
    } catch (err) {
      setError(err.message || "Could not change your password.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-lg mx-auto space-y-6">
      <div>
        <h2 className="font-display font-extrabold text-2xl gradient-text mb-1">Admin Settings</h2>
        <p className="text-sm text-muted-foreground">{user?.email}</p>
      </div>

      <ProfileCard />

      <div className="glass rounded-2xl border border-border/60 p-6 sm:p-8">
        <div className="w-11 h-11 rounded-xl bg-gradient-to-br from-primary to-green-500 grid place-items-center neon-border mb-5">
          <ShieldCheck className="w-6 h-6 text-background" strokeWidth={2.5} />
        </div>
        <h2 className="font-display font-bold text-xl mb-1">Change password</h2>
        <p className="text-sm text-muted-foreground mb-6">
          Enter your current password and choose a new one.
        </p>

        <form onSubmit={submit} className="space-y-4">
          <div className="relative">
            <Lock className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <input
              type={showPw ? "text" : "password"}
              autoComplete="current-password"
              required
              placeholder="Current password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              className="w-full pl-11 pr-11 py-3 rounded-xl bg-muted/40 border border-border text-sm outline-none focus:border-primary focus:neon-border transition-all placeholder:text-muted-foreground/70"
            />
            <button
              type="button"
              onClick={() => setShowPw((v) => !v)}
              className="absolute right-3.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-primary"
            >
              {showPw ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            </button>
          </div>
          <div className="relative">
            <Lock className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <input
              type={showPw ? "text" : "password"}
              autoComplete="new-password"
              required
              placeholder="New password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              className="w-full pl-11 pr-4 py-3 rounded-xl bg-muted/40 border border-border text-sm outline-none focus:border-primary focus:neon-border transition-all placeholder:text-muted-foreground/70"
            />
          </div>
          <div className="relative">
            <Lock className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <input
              type={showPw ? "text" : "password"}
              autoComplete="new-password"
              required
              placeholder="Confirm new password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              className="w-full pl-11 pr-4 py-3 rounded-xl bg-muted/40 border border-border text-sm outline-none focus:border-primary focus:neon-border transition-all placeholder:text-muted-foreground/70"
            />
          </div>

          {error && (
            <div className="text-sm text-destructive bg-destructive/10 border border-destructive/30 rounded-lg px-3 py-2">
              {error}
            </div>
          )}
          {success && (
            <div className="text-sm text-primary bg-primary/10 border border-primary/30 rounded-lg px-3 py-2">
              Password changed successfully.
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full flex items-center justify-center gap-2 py-3.5 rounded-xl font-heading font-bold text-base bg-primary text-primary-foreground hover:shadow-[0_0_28px_hsl(186_100%_50%/0.5)] transition-shadow disabled:opacity-60"
          >
            {loading ? <Loader2 className="w-5 h-5 animate-spin" /> : <>Change password <ArrowRight className="w-4 h-4" /></>}
          </button>
        </form>
      </div>
    </div>
  );
}
