import React, { useEffect, useState } from "react";
import { Lock, ArrowRight, Loader2, ShieldCheck, Eye, EyeOff, UserCircle, AlertTriangle, Trash2 } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/appauth";

function ProfileCard() {
  const { refreshUser } = useAuth();
  const [profile, setProfile] = useState(null);
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
        setProfile(p);
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
      const updated = await api.patch("/api/players/me/", { first_name: firstName, last_name: lastName });
      setProfile((p) => ({ ...p, ...updated }));
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
      <p className="text-sm text-muted-foreground mb-6">Your public display name and account details.</p>

      {loading ? (
        <div className="flex justify-center py-8 text-muted-foreground">
          <Loader2 className="w-5 h-5 animate-spin" />
        </div>
      ) : loadError ? (
        <div className="text-sm text-destructive bg-destructive/10 border border-destructive/30 rounded-lg px-3 py-2">
          {loadError}
        </div>
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-x-6 gap-y-1 mb-6 text-sm text-muted-foreground">
            <span>{profile.followers_count} followers</span>
            <span>{profile.following_count} following</span>
            <span>Joined {new Date(profile.date_joined).toLocaleDateString()}</span>
          </div>

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
        </>
      )}
    </div>
  );
}

function DangerZone() {
  const { logout } = useAuth();
  const [confirming, setConfirming] = useState(false);
  const [confirmText, setConfirmText] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState("");

  const deleteAccount = async () => {
    setDeleting(true);
    setError("");
    try {
      await api.delete("/api/players/me/");
      await logout();
    } catch (err) {
      setError(err.message || "Could not delete your account.");
      setDeleting(false);
    }
  };

  return (
    <div className="glass rounded-2xl border border-destructive/30 p-6 sm:p-8">
      <div className="flex items-center gap-2 mb-1">
        <AlertTriangle className="w-5 h-5 text-destructive" />
        <h2 className="font-display font-bold text-xl text-destructive">Danger zone</h2>
      </div>
      <p className="text-sm text-muted-foreground mb-6">
        Permanently delete your account and all associated data. This cannot be undone.
      </p>

      {error && (
        <div className="mb-4 text-sm text-destructive bg-destructive/10 border border-destructive/30 rounded-lg px-3 py-2">
          {error}
        </div>
      )}

      {!confirming ? (
        <button
          onClick={() => setConfirming(true)}
          className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-heading font-semibold text-destructive border border-destructive/40 hover:bg-destructive/10"
        >
          <Trash2 className="w-4 h-4" /> Delete my account
        </button>
      ) : (
        <div className="space-y-3">
          <label className="block text-xs font-heading font-bold uppercase tracking-wider text-muted-foreground">
            Type DELETE to confirm
          </label>
          <input
            value={confirmText}
            onChange={(e) => setConfirmText(e.target.value)}
            placeholder="DELETE"
            className="w-full max-w-xs px-3.5 py-2.5 rounded-xl bg-muted/40 border border-destructive/40 text-sm outline-none focus:border-destructive"
          />
          <div className="flex gap-2">
            <button
              onClick={deleteAccount}
              disabled={confirmText !== "DELETE" || deleting}
              className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-heading font-semibold bg-destructive text-destructive-foreground disabled:opacity-50"
            >
              {deleting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Trash2 className="w-4 h-4" />}
              Permanently delete
            </button>
            <button
              onClick={() => { setConfirming(false); setConfirmText(""); }}
              className="px-4 py-2 rounded-lg text-sm font-heading font-semibold text-muted-foreground hover:text-foreground"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default function AccountSettings() {
  const { user } = useAuth();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);

  const getPasswordError = (value) => {
    if (value.length < 8) return "Password must be at least 8 characters.";
    if (!/[A-Z]/.test(value)) return "Password must include an uppercase letter.";
    if (!/[a-z]/.test(value)) return "Password must include a lowercase letter.";
    if (!/[0-9]/.test(value)) return "Password must include a number.";
    if (!/[^A-Za-z0-9]/.test(value)) return "Password must include a special character.";
    return "";
  };

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    setSuccess(false);
    const pwError = getPasswordError(newPassword);
    if (pwError) {
      setError(pwError);
      return;
    }
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
    <div className="max-w-lg mx-auto px-4 sm:px-6 py-12 sm:py-16 space-y-6">
      <div>
        <h1 className="font-display font-extrabold text-3xl gradient-text mb-1">Account Settings</h1>
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
          <p className="text-[11px] text-muted-foreground -mt-2 px-1">
            At least 8 characters, with uppercase, lowercase, a number and a special character.
          </p>
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

      <DangerZone />
    </div>
  );
}
