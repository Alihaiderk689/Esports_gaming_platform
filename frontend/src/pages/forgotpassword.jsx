import React, { useState } from "react";
import { Link } from "react-router-dom";
import { Mail, ArrowRight, Loader2, KeyRound } from "lucide-react";
import { api } from "@/lib/api";

export default function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState("");

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await api.post("/api/auth/forgot-password/", { email }, { auth: false });
    } catch (err) {
      // Backend already avoids leaking whether the email exists; only surface
      // real failures (e.g. validation, rate limit), never "not found".
      setError(err.message || "Something went wrong. Please try again.");
      setLoading(false);
      return;
    }
    setLoading(false);
    setSent(true);
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <div className="w-full max-w-md">
        <div className="glass rounded-2xl border border-border/60 p-6 sm:p-8">
          <div className="w-11 h-11 rounded-xl bg-gradient-to-br from-primary to-green-500 grid place-items-center neon-border mb-5">
            <KeyRound className="w-6 h-6 text-background" strokeWidth={2.5} />
          </div>
          <h1 className="font-display font-bold text-2xl mb-1">Forgot password?</h1>
          <p className="text-sm text-muted-foreground mb-6">
            Enter your account email and we'll send you a reset link.
          </p>

          {sent ? (
            <div className="text-sm text-primary bg-primary/10 border border-primary/30 rounded-lg px-3 py-2">
              If that email exists, a reset link has been sent. Check your inbox.
            </div>
          ) : (
            <form onSubmit={submit} className="space-y-4">
              <div className="relative">
                <Mail className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                <input
                  type="email"
                  autoComplete="email"
                  autoFocus
                  required
                  placeholder="you@example.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
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
                {loading ? <Loader2 className="w-5 h-5 animate-spin" /> : <>Send reset link <ArrowRight className="w-4 h-4" /></>}
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
