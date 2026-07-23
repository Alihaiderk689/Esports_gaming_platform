import React, { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { CheckCircle2, XCircle, Loader2, Mail } from "lucide-react";
import { api } from "@/lib/api";

export default function VerifyEmail() {
  const [params] = useSearchParams();
  const uid = params.get("uid") || "";
  const token = params.get("token") || "";

  const [status, setStatus] = useState(uid && token ? "verifying" : "missing");
  const [resendEmail, setResendEmail] = useState("");
  const [resendSent, setResendSent] = useState(false);
  const [resending, setResending] = useState(false);

  useEffect(() => {
    if (!(uid && token)) return;
    api
      .get("/api/auth/verify-email/", { query: { uid, token }, auth: false })
      .then(() => setStatus("success"))
      .catch(() => setStatus("failed"));
  }, [uid, token]);

  const resend = async (e) => {
    e.preventDefault();
    setResending(true);
    try {
      await api.post("/api/auth/resend-verification/", { email: resendEmail }, { auth: false });
    } finally {
      setResending(false);
      setResendSent(true);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <div className="w-full max-w-md">
        <div className="glass rounded-2xl border border-border/60 p-6 sm:p-8 text-center">
          {status === "verifying" && (
            <>
              <Loader2 className="w-10 h-10 mx-auto text-primary animate-spin mb-4" />
              <h1 className="font-display font-bold text-2xl mb-1">Verifying your email…</h1>
            </>
          )}

          {status === "success" && (
            <>
              <div className="w-14 h-14 rounded-full bg-primary/10 grid place-items-center mx-auto mb-4">
                <CheckCircle2 className="w-8 h-8 text-primary" />
              </div>
              <h1 className="font-display font-bold text-2xl mb-1">Email verified</h1>
              <p className="text-sm text-muted-foreground mb-6">Your account is ready. You can sign in now.</p>
              <Link
                to="/login"
                className="inline-flex items-center justify-center w-full py-3.5 rounded-xl font-heading font-bold text-base bg-primary text-primary-foreground hover:shadow-[0_0_28px_hsl(186_100%_50%/0.5)] transition-shadow"
              >
                Go to sign in
              </Link>
            </>
          )}

          {(status === "failed" || status === "missing") && (
            <>
              <div className="w-14 h-14 rounded-full bg-destructive/10 grid place-items-center mx-auto mb-4">
                <XCircle className="w-8 h-8 text-destructive" />
              </div>
              <h1 className="font-display font-bold text-2xl mb-1">Link invalid or expired</h1>
              <p className="text-sm text-muted-foreground mb-6">
                Enter your email and we'll send a new verification link.
              </p>

              {resendSent ? (
                <div className="text-sm text-primary bg-primary/10 border border-primary/30 rounded-lg px-3 py-2 text-left">
                  If that email exists and is unverified, a new link has been sent.
                </div>
              ) : (
                <form onSubmit={resend} className="space-y-4 text-left">
                  <div className="relative">
                    <Mail className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                    <input
                      type="email"
                      required
                      placeholder="you@example.com"
                      value={resendEmail}
                      onChange={(e) => setResendEmail(e.target.value)}
                      className="w-full pl-11 pr-4 py-3 rounded-xl bg-muted/40 border border-border text-sm outline-none focus:border-primary focus:neon-border transition-all placeholder:text-muted-foreground/70"
                    />
                  </div>
                  <button
                    type="submit"
                    disabled={resending}
                    className="w-full py-3.5 rounded-xl font-heading font-bold text-base bg-primary text-primary-foreground hover:shadow-[0_0_28px_hsl(186_100%_50%/0.5)] transition-shadow disabled:opacity-60"
                  >
                    {resending ? "Sending…" : "Resend verification email"}
                  </button>
                </form>
              )}
            </>
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
