import React, { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { CheckCircle2, Mail } from "lucide-react";
import { api } from "@/lib/api";

// Fallback, standalone version of the inline OTP step on the auth page
// (src/pages/auth.jsx) — for someone who closed that tab after registering,
// or opened this link on a different device. Verification codes are never
// linked from the email itself (see backend/core/emails.py); this is just a
// manual email + code entry form, not a token-in-the-URL flow.
export default function VerifyEmail() {
  const [params] = useSearchParams();
  const [email, setEmail] = useState(params.get("email") || "");
  const [otp, setOtp] = useState("");
  const [status, setStatus] = useState("form"); // form | success
  const [error, setError] = useState("");
  const [attemptsLeft, setAttemptsLeft] = useState(null);
  const [verifying, setVerifying] = useState(false);
  const [resendSent, setResendSent] = useState(false);
  const [resending, setResending] = useState(false);

  const verify = async (e) => {
    e.preventDefault();
    setError("");
    setVerifying(true);
    try {
      await api.post("/api/auth/verify-email/", { email: email.trim().toLowerCase(), otp }, { auth: false });
      setStatus("success");
    } catch (err) {
      const data = err.data || {};
      const otpMsg = Array.isArray(data.otp) ? data.otp[0] : data.otp;
      setError(otpMsg || err.message || "Invalid or expired code.");
      setAttemptsLeft(data.attempts_remaining != null ? Number(data.attempts_remaining) : null);
    } finally {
      setVerifying(false);
    }
  };

  const resend = async (e) => {
    e.preventDefault();
    setError("");
    setResendSent(false);
    setResending(true);
    try {
      await api.post("/api/auth/resend-verification/", { email: email.trim().toLowerCase() }, { auth: false });
      setResendSent(true);
    } catch (err) {
      setError(err.message || "Couldn't resend the code. Please try again.");
    } finally {
      setResending(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <div className="w-full max-w-md">
        <div className="glass rounded-2xl border border-border/60 p-6 sm:p-8 text-center">
          {status === "success" ? (
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
          ) : (
            <>
              <div className="w-14 h-14 rounded-full bg-primary/10 grid place-items-center mx-auto mb-4">
                <Mail className="w-8 h-8 text-primary" />
              </div>
              <h1 className="font-display font-bold text-2xl mb-1">Verify your email</h1>
              <p className="text-sm text-muted-foreground mb-6">
                Enter your email and the 6-digit code we sent you.
              </p>

              <form onSubmit={verify} className="space-y-4 text-left">
                <div className="relative">
                  <Mail className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                  <input
                    type="email"
                    required
                    placeholder="you@example.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="w-full pl-11 pr-4 py-3 rounded-xl bg-muted/40 border border-border text-sm outline-none focus:border-primary focus:neon-border transition-all placeholder:text-muted-foreground/70"
                  />
                </div>
                <input
                  type="text"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  maxLength={6}
                  required
                  placeholder="000000"
                  value={otp}
                  onChange={(e) => setOtp(e.target.value.replace(/\D/g, "").slice(0, 6))}
                  className="w-full text-center tracking-[0.5em] text-2xl font-heading font-bold px-4 py-3.5 rounded-xl bg-muted/40 border border-border outline-none focus:border-primary focus:neon-border transition-all placeholder:text-muted-foreground/40"
                />

                {error && (
                  <div className="text-sm text-destructive bg-destructive/10 border border-destructive/30 rounded-lg px-3 py-2 text-left">
                    {error}
                    {attemptsLeft !== null && ` (${attemptsLeft} attempt${attemptsLeft === 1 ? "" : "s"} left)`}
                  </div>
                )}

                {resendSent && (
                  <div className="text-sm text-primary bg-primary/10 border border-primary/30 rounded-lg px-3 py-2 text-left">
                    If that email exists and is unverified, a new code has been sent.
                  </div>
                )}

                <button
                  type="submit"
                  disabled={verifying || otp.length !== 6 || !email}
                  className="w-full py-3.5 rounded-xl font-heading font-bold text-base bg-primary text-primary-foreground hover:shadow-[0_0_28px_hsl(186_100%_50%/0.5)] transition-shadow disabled:opacity-60"
                >
                  {verifying ? "Verifying…" : "Verify"}
                </button>

                <button
                  type="button"
                  onClick={resend}
                  disabled={resending || !email}
                  className="w-full text-sm font-heading font-semibold text-primary hover:underline disabled:opacity-50"
                >
                  {resending ? "Sending…" : "Resend code"}
                </button>
              </form>
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
