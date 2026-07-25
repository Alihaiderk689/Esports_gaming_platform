import React, { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Lock, ArrowRight, Loader2, KeyRound, Eye, EyeOff } from "lucide-react";
import { api } from "@/lib/api";

export default function ResetPassword() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const uid = params.get("uid") || "";
  const token = params.get("token") || "";

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const missingLink = !uid || !token;

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
    const pwError = getPasswordError(password);
    if (pwError) {
      setError(pwError);
      return;
    }
    if (password !== confirm) {
      setError("Passwords do not match.");
      return;
    }
    setLoading(true);
    try {
      await api.post(
        "/api/auth/reset-password/",
        { uid, token, new_password: password },
        { auth: false }
      );
      navigate("/login", { state: { info: "Password reset. Please sign in." } });
    } catch (err) {
      setError(err.message || "This reset link is invalid or has expired.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <div className="w-full max-w-md">
        <div className="glass rounded-2xl border border-border/60 p-6 sm:p-8">
          <div className="w-11 h-11 rounded-xl bg-gradient-to-br from-primary to-green-500 grid place-items-center neon-border mb-5">
            <KeyRound className="w-6 h-6 text-background" strokeWidth={2.5} />
          </div>
          <h1 className="font-display font-bold text-2xl mb-1">Reset your password</h1>
          <p className="text-sm text-muted-foreground mb-6">Choose a new password for your account.</p>

          {missingLink ? (
            <div className="text-sm text-destructive bg-destructive/10 border border-destructive/30 rounded-lg px-3 py-2">
              This reset link is missing or malformed. Please request a new one.
            </div>
          ) : (
            <form onSubmit={submit} className="space-y-4">
              <div className="relative">
                <Lock className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                <input
                  type={showPw ? "text" : "password"}
                  autoComplete="new-password"
                  autoFocus
                  required
                  placeholder="New password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
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

              <button
                type="submit"
                disabled={loading}
                className="w-full flex items-center justify-center gap-2 py-3.5 rounded-xl font-heading font-bold text-base bg-primary text-primary-foreground hover:shadow-[0_0_28px_hsl(186_100%_50%/0.5)] transition-shadow disabled:opacity-60"
              >
                {loading ? <Loader2 className="w-5 h-5 animate-spin" /> : <>Reset password <ArrowRight className="w-4 h-4" /></>}
              </button>
            </form>
          )}

          <p className="mt-6 text-center text-sm text-muted-foreground">
            <Link to="/login" className="text-primary font-medium hover:underline">
              Back to sign in
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
