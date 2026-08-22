import React, { useState, useEffect } from "react";
import { useNavigate, useLocation, Link } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { useAuth } from "@/lib/appauth";
import { api } from "@/lib/api";
import { startGoogleSignIn } from "@/lib/googleAuth";
import { routeAfterLogin } from "@/lib/routeAfterLogin";
import { Gamepad2, Mail, Lock, User, Eye, EyeOff, ArrowRight, ArrowLeft, Shield, Swords, CheckCircle2, Circle, Loader2 } from "lucide-react";
import Logo from "@/components/Logo";

const NAME_REGEX = /^[A-Za-z]+(?:[ '-][A-Za-z]+)*$/;
const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

// Mirrors backend/core/otp.py's OTP_TTL / OTP_RESEND_COOLDOWN — purely for
// the client-side countdown display. The backend is the actual source of
// truth for expiry; this can drift a few seconds without being a problem.
const OTP_TTL_MS = 10 * 60 * 1000;
const OTP_RESEND_COOLDOWN_MS = 60 * 1000;

function formatMMSS(totalSeconds) {
  const m = Math.floor(totalSeconds / 60);
  const s = totalSeconds % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

function getNameError(value, label) {
  const trimmed = value.trim();
  if (!trimmed) return `${label} is required.`;
  if (trimmed.length < 2 || trimmed.length > 50) return `${label} must be 2–50 characters.`;
  if (!NAME_REGEX.test(trimmed)) return `${label} can only contain letters, spaces, hyphens, and apostrophes.`;
  return "";
}

function getEmailError(value) {
  const trimmed = value.trim();
  if (!trimmed) return "Email is required.";
  if (!EMAIL_REGEX.test(trimmed)) return "Enter a valid email address.";
  return "";
}

const PASSWORD_CHECKS = [
  { key: "length", label: "8+ characters", test: (p) => p.length >= 8 && p.length <= 128 },
  { key: "upper", label: "Uppercase letter", test: (p) => /[A-Z]/.test(p) },
  { key: "lower", label: "Lowercase letter", test: (p) => /[a-z]/.test(p) },
  { key: "number", label: "Number", test: (p) => /[0-9]/.test(p) },
  { key: "special", label: "Special character", test: (p) => /[^A-Za-z0-9]/.test(p) },
];

export default function Auth() {
  const { login, register } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [mode, setMode] = useState("login"); // login | signup
  const [role, setRole] = useState("user"); // user | organizer
  const [showPw, setShowPw] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [info, setInfo] = useState(location.state?.info || "");
  const [form, setForm] = useState({ first_name: "", last_name: "", email: "", password: "", confirm: "" });
  const [submitted, setSubmitted] = useState(false);
  const [orgStep, setOrgStep] = useState(1); // 1: account details, 2: organizer application

  // Post-registration OTP entry — shown in place of the login/signup form
  // until the emailed code is verified (or the user backs out).
  const [otpMode, setOtpMode] = useState(false);
  const [otpEmail, setOtpEmail] = useState("");
  const [otpValue, setOtpValue] = useState("");
  const [otpError, setOtpError] = useState("");
  const [otpInfo, setOtpInfo] = useState("");
  const [otpAttemptsLeft, setOtpAttemptsLeft] = useState(null);
  const [otpLoading, setOtpLoading] = useState(false);
  const [otpResending, setOtpResending] = useState(false);
  const [otpExpiresAt, setOtpExpiresAt] = useState(null);
  const [resendCooldownUntil, setResendCooldownUntil] = useState(null);
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    if (!otpMode) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [otpMode]);

  const otpSecondsLeft = otpExpiresAt ? Math.max(0, Math.ceil((otpExpiresAt - now) / 1000)) : 0;
  const otpExpired = otpExpiresAt !== null && otpSecondsLeft <= 0;
  const resendSecondsLeft = resendCooldownUntil ? Math.max(0, Math.ceil((resendCooldownUntil - now) / 1000)) : 0;
  const canResend = resendSecondsLeft <= 0;
  const emptyOrgForm = {
    company_name: "", phone_number: "", address: "",
    cnic_number: "", cnic_document: null,
    company_registration_number: "", company_document: null,
    payout_method: "jazzcash", jazzcash_number: "", bank_name: "", bank_account_title: "", bank_account_number: "",
  };
  const [orgForm, setOrgForm] = useState(emptyOrgForm);

  const from = location.state?.from || "/";

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const setOrg = (k) => (e) => setOrgForm((f) => ({ ...f, [k]: e.target.value }));
  const setOrgFile = (k) => (e) => setOrgForm((f) => ({ ...f, [k]: e.target.files?.[0] || null }));

  const getPasswordError = (password) => {
    const failed = PASSWORD_CHECKS.find((c) => !c.test(password));
    if (!failed) return "";
    if (password.length > 128) return "Password must be at most 128 characters.";
    return `Password must include: ${failed.label.toLowerCase()}.`;
  };

  const firstNameError = mode === "signup" ? getNameError(form.first_name, "First name") : "";
  const lastNameError = mode === "signup" ? getNameError(form.last_name, "Last name") : "";
  const emailError = getEmailError(form.email);
  const passwordError = mode === "signup" ? getPasswordError(form.password) : "";
  const confirmError = mode === "signup" && form.confirm && form.password !== form.confirm ? "Passwords do not match." : "";

  const isOrgStep2 = mode === "signup" && role === "organizer" && orgStep === 2;
  const showAccountFields = !isOrgStep2;

  const companyNameError = !orgForm.company_name.trim() ? "Company / organization name is required." : "";
  const cnicDocumentError = !orgForm.cnic_document ? "Please upload your CNIC document." : "";
  const companyDocumentError = !orgForm.company_document ? "Please upload a company document." : "";
  const jazzcashNumberError =
    orgForm.payout_method === "jazzcash" && !orgForm.jazzcash_number.trim() ? "JazzCash number is required." : "";
  const bankNameError = orgForm.payout_method === "bank" && !orgForm.bank_name.trim() ? "Bank name is required." : "";
  const bankAccountTitleError =
    orgForm.payout_method === "bank" && !orgForm.bank_account_title.trim() ? "Account title is required." : "";
  const bankAccountNumberError =
    orgForm.payout_method === "bank" && !orgForm.bank_account_number.trim() ? "Account number is required." : "";

  const orgInputClass = (hasError) =>
    `w-full px-3.5 py-2.5 rounded-xl bg-muted/40 border text-sm outline-none focus:border-primary placeholder:text-muted-foreground/70 ${
      hasError ? "border-destructive focus:border-destructive" : "border-border"
    }`;

  const getOrganizerFormError = () =>
    companyNameError || cnicDocumentError || companyDocumentError || jazzcashNumberError ||
    bankNameError || bankAccountTitleError || bankAccountNumberError;

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    setInfo("");
    setSubmitted(true);
    if (mode === "signup") {
      const firstError = firstNameError || lastNameError || emailError || passwordError || confirmError;
      if (firstError) {
        setError(firstError);
        return;
      }
      if (role === "organizer") {
        if (orgStep === 1) {
          setError("");
          setSubmitted(false);
          setOrgStep(2);
          return;
        }
        const orgError = getOrganizerFormError();
        if (orgError) {
          setError(orgError);
          return;
        }
      }
    }
    const email = form.email.trim().toLowerCase();
    const first_name = form.first_name.trim();
    const last_name = form.last_name.trim();
    setLoading(true);
    try {
      if (mode === "login") {
        const loggedInUser = await login(email, form.password);
        await routeAfterLogin(navigate, loggedInUser, from);
      } else {
        if (role === "organizer") {
          const fd = new FormData();
          fd.append("first_name", first_name);
          fd.append("last_name", last_name);
          fd.append("email", email);
          fd.append("password", form.password);
          fd.append("confirm_password", form.confirm);
          fd.append("role", "organizer");
          fd.append("company_name", orgForm.company_name.trim());
          if (orgForm.phone_number.trim()) fd.append("phone_number", orgForm.phone_number.trim());
          if (orgForm.address.trim()) fd.append("address", orgForm.address.trim());
          if (orgForm.cnic_number.trim()) fd.append("cnic_number", orgForm.cnic_number.trim());
          fd.append("cnic_document", orgForm.cnic_document);
          if (orgForm.company_registration_number.trim()) {
            fd.append("company_registration_number", orgForm.company_registration_number.trim());
          }
          fd.append("company_document", orgForm.company_document);
          fd.append("payout_method", orgForm.payout_method);
          if (orgForm.payout_method === "jazzcash") {
            fd.append("jazzcash_number", orgForm.jazzcash_number.trim());
          } else {
            fd.append("bank_name", orgForm.bank_name.trim());
            fd.append("bank_account_title", orgForm.bank_account_title.trim());
            fd.append("bank_account_number", orgForm.bank_account_number.trim());
          }
          await register(fd, { formData: true });
        } else {
          await register({
            first_name, last_name, email,
            password: form.password, confirm_password: form.confirm,
            role: "user",
          });
        }
        setForm((f) => ({ ...f, password: "", confirm: "" }));
        setOrgForm(emptyOrgForm);
        setSubmitted(false);
        setOrgStep(1);
        setOtpEmail(email);
        setOtpValue("");
        setOtpError("");
        setOtpAttemptsLeft(null);
        setOtpInfo(
          role === "organizer"
            ? "Once verified, your organizer application will be submitted for review."
            : "",
        );
        setOtpExpiresAt(Date.now() + OTP_TTL_MS);
        setResendCooldownUntil(Date.now() + OTP_RESEND_COOLDOWN_MS);
        setOtpMode(true);
      }
    } catch (err) {
      setError(err.message || "Something went wrong. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const submitOtp = async (e) => {
    e.preventDefault();
    setOtpError("");
    setOtpLoading(true);
    try {
      await api.post("/api/auth/verify-email/", { email: otpEmail, otp: otpValue }, { auth: false });
      setOtpMode(false);
      setOtpValue("");
      setMode("login");
      setError("");
      setInfo("Account created and email verified. You can sign in now.");
    } catch (err) {
      const data = err.data || {};
      const otpMsg = Array.isArray(data.otp) ? data.otp[0] : data.otp;
      setOtpError(otpMsg || err.message || "Invalid or expired code.");
      setOtpAttemptsLeft(data.attempts_remaining != null ? Number(data.attempts_remaining) : null);
    } finally {
      setOtpLoading(false);
    }
  };

  const resendOtp = async () => {
    setOtpResending(true);
    setOtpError("");
    try {
      await api.post("/api/auth/resend-verification/", { email: otpEmail }, { auth: false });
      setOtpValue("");
      setOtpAttemptsLeft(null);
      setOtpInfo("A new code has been sent — check your inbox.");
      setOtpExpiresAt(Date.now() + OTP_TTL_MS);
      setResendCooldownUntil(Date.now() + OTP_RESEND_COOLDOWN_MS);
    } finally {
      setOtpResending(false);
    }
  };

  return (
    <div className="min-h-screen flex">
      {/* LEFT VISUAL */}
      <div className="hidden lg:flex lg:w-1/2 relative overflow-hidden">
        <div className="absolute inset-0 mesh-bg animate-gradient" />
        <div className="absolute inset-0 grid-overlay opacity-30" />
        <div className="absolute inset-0 bg-gradient-to-tr from-background via-background/40 to-transparent" />

        <motion.div
          className="absolute top-1/4 left-1/4 w-72 h-72 rounded-full bg-secondary/30 blur-3xl"
          animate={{ y: [0, -40, 0], x: [0, 20, 0] }}
          transition={{ duration: 9, repeat: Infinity }}
        />
        <motion.div
          className="absolute bottom-1/4 right-1/4 w-80 h-80 rounded-full bg-accent/20 blur-3xl"
          animate={{ y: [0, 30, 0], x: [0, -20, 0] }}
          transition={{ duration: 11, repeat: Infinity }}
        />

        <div className="relative z-10 flex flex-col justify-between p-12 w-full">
          <Link to="/" className="flex items-center gap-3">
            <Logo className="h-11 w-auto" />
            <div>
              <div className="font-display font-extrabold tracking-wider text-lg">ESPORTS</div>
              <div className="font-display font-bold text-xs gradient-text tracking-[0.3em]">PAKISTAN</div>
            </div>
          </Link>

          <div>
            <motion.h1
              initial={{ opacity: 0, y: 30 }}
              animate={{ opacity: 1, y: 0 }}
              className="font-display font-extrabold text-5xl xl:text-6xl leading-[0.95] tracking-tight"
            >
              ENTER THE<br />
              <span className="gradient-text animate-gradient">ARENA</span>
            </motion.h1>
            <p className="mt-5 text-muted-foreground max-w-md text-lg leading-relaxed">
              Where Pakistan's elite gamers compete, conquer and connect. Your journey to the top starts here.
            </p>
            <div className="mt-8 flex gap-6">
              {[
                { icon: Swords, label: "Compete" },
                { icon: Shield, label: "Verify" },
                { icon: CheckCircle2, label: "Win" },
              ].map((f) => (
                <div key={f.label} className="flex items-center gap-2">
                  <div className="w-9 h-9 rounded-lg glass grid place-items-center">
                    <f.icon className="w-4 h-4 text-primary" />
                  </div>
                  <span className="font-heading font-semibold text-sm">{f.label}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="flex items-center gap-6 text-sm text-muted-foreground">
            <span>15K+ Players</span>
            <span className="w-1 h-1 rounded-full bg-muted-foreground/50" />
            <span>120+ Tournaments</span>
            <span className="w-1 h-1 rounded-full bg-muted-foreground/50" />
            <span>Rs. 5M Prize Pool</span>
          </div>
        </div>
      </div>

      {/* RIGHT FORM */}
      <div className="w-full lg:w-1/2 flex items-center justify-center p-6 sm:p-12 relative">
        <div className="absolute inset-0 mesh-bg opacity-20 lg:hidden" />
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="relative w-full max-w-md"
        >
          <Link to="/" className="lg:hidden flex items-center gap-2.5 mb-8">
            <Logo className="h-10 w-auto" />
            <div className="font-display font-extrabold tracking-wider">ESPORTS <span className="gradient-text">PK</span></div>
          </Link>

          <div className="glass rounded-2xl border border-border/60 p-6 sm:p-8">
            {otpMode ? (
              <>
                <div className="w-14 h-14 rounded-full bg-primary/10 grid place-items-center mx-auto mb-4">
                  <Mail className="w-7 h-7 text-primary" />
                </div>
                <h2 className="font-display font-bold text-2xl mb-1 text-center">Verify your email</h2>
                <p className="text-sm text-muted-foreground mb-6 text-center">
                  Enter the 6-digit code we sent to <span className="text-foreground font-medium">{otpEmail}</span>.
                </p>

                <form onSubmit={submitOtp} noValidate className="space-y-4">
                  <div>
                    <input
                      type="text"
                      inputMode="numeric"
                      autoComplete="one-time-code"
                      maxLength={6}
                      placeholder="000000"
                      value={otpValue}
                      onChange={(e) => setOtpValue(e.target.value.replace(/\D/g, "").slice(0, 6))}
                      className="w-full text-center tracking-[0.5em] text-2xl font-heading font-bold px-4 py-3.5 rounded-xl bg-muted/40 border border-border outline-none focus:border-primary focus:neon-border transition-all placeholder:text-muted-foreground/40"
                      autoFocus
                    />
                    <div className="mt-2 text-xs text-muted-foreground text-center">
                      {otpExpired ? (
                        <span className="text-destructive">Code expired — request a new one.</span>
                      ) : (
                        <>Code expires in {formatMMSS(otpSecondsLeft)}</>
                      )}
                    </div>
                  </div>

                  {otpError && (
                    <motion.div
                      initial={{ opacity: 0, y: -5 }}
                      animate={{ opacity: 1, y: 0 }}
                      className="text-sm text-destructive bg-destructive/10 border border-destructive/30 rounded-lg px-3 py-2"
                    >
                      {otpError}
                      {otpAttemptsLeft !== null && ` (${otpAttemptsLeft} attempt${otpAttemptsLeft === 1 ? "" : "s"} left)`}
                    </motion.div>
                  )}

                  {otpInfo && !otpError && (
                    <motion.div
                      initial={{ opacity: 0, y: -5 }}
                      animate={{ opacity: 1, y: 0 }}
                      className="text-sm text-primary bg-primary/10 border border-primary/30 rounded-lg px-3 py-2"
                    >
                      {otpInfo}
                    </motion.div>
                  )}

                  <button
                    type="submit"
                    disabled={otpLoading || otpValue.length !== 6 || otpExpired}
                    className="w-full flex items-center justify-center gap-2 py-3.5 rounded-xl font-heading font-bold text-base bg-primary text-primary-foreground hover:shadow-[0_0_28px_hsl(186_100%_50%/0.5)] transition-shadow disabled:opacity-60"
                  >
                    {otpLoading ? (
                      <Loader2 className="w-5 h-5 animate-spin" />
                    ) : (
                      <>
                        Verify & Create Account
                        <ArrowRight className="w-4 h-4" />
                      </>
                    )}
                  </button>

                  <button
                    type="button"
                    onClick={resendOtp}
                    disabled={!canResend || otpResending}
                    className="w-full text-sm font-heading font-semibold text-primary hover:underline disabled:opacity-50 disabled:no-underline disabled:cursor-not-allowed"
                  >
                    {otpResending ? "Sending…" : canResend ? "Resend code" : `Resend code in ${formatMMSS(resendSecondsLeft)}`}
                  </button>

                  <button
                    type="button"
                    onClick={() => { setOtpMode(false); setMode("login"); setOtpError(""); setOtpInfo(""); }}
                    className="w-full text-xs text-muted-foreground hover:text-primary text-center transition-colors"
                  >
                    Back to sign in
                  </button>
                </form>

                <p className="mt-5 text-center text-xs text-muted-foreground">
                  Lost this screen?{" "}
                  <Link
                    to={`/verify-email?email=${encodeURIComponent(otpEmail)}`}
                    className="text-primary hover:underline"
                  >
                    Enter your code here
                  </Link>
                  .
                </p>
              </>
            ) : (
              <>
            {/* Toggle */}
            <div className="relative flex p-1 rounded-xl bg-muted/50 mb-6">
              <motion.div
                className="absolute top-1 bottom-1 w-[calc(50%-4px)] rounded-lg bg-primary"
                animate={{ x: mode === "login" ? 0 : "100%" }}
                transition={{ type: "spring", damping: 26, stiffness: 300 }}
              />
              <button
                onClick={() => { setMode("login"); setError(""); setInfo(""); setOrgStep(1); setSubmitted(false); }}
                className={`relative flex-1 py-2.5 text-sm font-heading font-bold transition-colors ${mode === "login" ? "text-primary-foreground" : "text-muted-foreground"}`}
              >
                Sign In
              </button>
              <button
                onClick={() => { setMode("signup"); setError(""); setInfo(""); setOrgStep(1); setSubmitted(false); }}
                className={`relative flex-1 py-2.5 text-sm font-heading font-bold transition-colors ${mode === "signup" ? "text-primary-foreground" : "text-muted-foreground"}`}
              >
                Sign Up
              </button>
            </div>

            <h2 className="font-display font-bold text-2xl mb-1">
              {mode === "login" ? "Welcome back, player" : "Join the arena"}
            </h2>
            <p className="text-sm text-muted-foreground mb-6">
              {mode === "login" ? "Sign in to continue your journey." : "Create your account in seconds."}
            </p>

            {/* Role selector for signup */}
            <AnimatePresence>
              {mode === "signup" && showAccountFields && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: "auto" }}
                  exit={{ opacity: 0, height: 0 }}
                  className="overflow-hidden mb-5"
                >
                  <div className="flex items-center justify-between mb-2">
                    <div className="text-xs font-heading font-bold uppercase tracking-wider text-muted-foreground">
                      I am a…
                    </div>
                    {role === "organizer" && (
                      <div className="text-[11px] font-heading font-semibold text-muted-foreground">Step 1 of 2</div>
                    )}
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <RoleCard active={role === "user"} onClick={() => setRole("user")} icon={Gamepad2} label="Player" desc="Compete & follow" />
                    <RoleCard active={role === "organizer"} onClick={() => setRole("organizer")} icon={Shield} label="Organizer" desc="Host events" />
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            <form onSubmit={submit} noValidate className="space-y-4">
              {showAccountFields && (
                <>
                  {mode === "signup" && (
                    <div className="grid grid-cols-2 gap-3">
                      <Field
                        icon={User}
                        placeholder="First name"
                        value={form.first_name}
                        onChange={set("first_name")}
                        error={submitted ? firstNameError : ""}
                        required
                      />
                      <Field
                        icon={User}
                        placeholder="Last name"
                        value={form.last_name}
                        onChange={set("last_name")}
                        error={submitted ? lastNameError : ""}
                        required
                      />
                    </div>
                  )}
                  <Field
                    icon={Mail}
                    type="email"
                    placeholder="Email address"
                    value={form.email}
                    onChange={set("email")}
                    error={submitted ? emailError : ""}
                    required
                  />
                  <Field
                    icon={Lock}
                    type={showPw ? "text" : "password"}
                    placeholder="Password"
                    value={form.password}
                    onChange={set("password")}
                    required
                    trailing={
                      <button type="button" onClick={() => setShowPw((v) => !v)} className="text-muted-foreground hover:text-primary">
                        {showPw ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                      </button>
                    }
                  />
                  {mode === "signup" && (
                    <>
                      <PasswordChecklist password={form.password} />
                      <Field
                        icon={Lock}
                        type={showPw ? "text" : "password"}
                        placeholder="Confirm password"
                        value={form.confirm}
                        onChange={set("confirm")}
                        error={submitted ? confirmError : ""}
                        required
                      />
                    </>
                  )}
                </>
              )}

              {isOrgStep2 && (
                <div className="space-y-4">
                  <div className="text-xs font-heading font-bold uppercase tracking-wider text-muted-foreground">
                    Organizer application <span className="text-muted-foreground/60 normal-case font-normal">— step 2 of 2</span>
                  </div>

                  <div>
                    <input
                      required
                      value={orgForm.company_name}
                      onChange={setOrg("company_name")}
                      placeholder="Company / organization name"
                      className={orgInputClass(submitted && companyNameError)}
                    />
                    {submitted && companyNameError && (
                      <p className="mt-1.5 text-[11px] text-destructive px-1">{companyNameError}</p>
                    )}
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <input
                      value={orgForm.phone_number}
                      onChange={setOrg("phone_number")}
                      placeholder="Phone (optional)"
                      className="w-full px-3.5 py-2.5 rounded-xl bg-muted/40 border border-border text-sm outline-none focus:border-primary placeholder:text-muted-foreground/70"
                    />
                    <input
                      value={orgForm.address}
                      onChange={setOrg("address")}
                      placeholder="Address (optional)"
                      className="w-full px-3.5 py-2.5 rounded-xl bg-muted/40 border border-border text-sm outline-none focus:border-primary placeholder:text-muted-foreground/70"
                    />
                  </div>

                  <div className="pt-2 border-t border-border/60 space-y-2">
                    <input
                      value={orgForm.cnic_number}
                      onChange={setOrg("cnic_number")}
                      placeholder="CNIC number (optional)"
                      className="w-full px-3.5 py-2.5 rounded-xl bg-muted/40 border border-border text-sm outline-none focus:border-primary placeholder:text-muted-foreground/70"
                    />
                    <label className="block text-xs font-heading font-bold uppercase tracking-wider text-muted-foreground">
                      CNIC document
                    </label>
                    <input
                      type="file"
                      required
                      onChange={setOrgFile("cnic_document")}
                      className="w-full text-xs text-muted-foreground file:mr-3 file:px-3 file:py-1.5 file:rounded-lg file:border-0 file:bg-primary file:text-primary-foreground file:text-xs file:font-heading file:font-semibold"
                    />
                    {submitted && cnicDocumentError && (
                      <p className="text-[11px] text-destructive px-1">{cnicDocumentError}</p>
                    )}
                  </div>

                  <div className="pt-2 border-t border-border/60 space-y-2">
                    <input
                      value={orgForm.company_registration_number}
                      onChange={setOrg("company_registration_number")}
                      placeholder="Company registration number (optional)"
                      className="w-full px-3.5 py-2.5 rounded-xl bg-muted/40 border border-border text-sm outline-none focus:border-primary placeholder:text-muted-foreground/70"
                    />
                    <label className="block text-xs font-heading font-bold uppercase tracking-wider text-muted-foreground">
                      Company document
                    </label>
                    <input
                      type="file"
                      required
                      onChange={setOrgFile("company_document")}
                      className="w-full text-xs text-muted-foreground file:mr-3 file:px-3 file:py-1.5 file:rounded-lg file:border-0 file:bg-primary file:text-primary-foreground file:text-xs file:font-heading file:font-semibold"
                    />
                    {submitted && companyDocumentError && (
                      <p className="text-[11px] text-destructive px-1">{companyDocumentError}</p>
                    )}
                  </div>

                  <div className="pt-2 border-t border-border/60">
                    <label className="block text-xs font-heading font-bold uppercase tracking-wider text-muted-foreground mb-2">
                      Payout method
                    </label>
                    <div className="flex gap-1 p-1 rounded-xl bg-muted/30 border border-border w-fit mb-3">
                      {[{ value: "jazzcash", label: "JazzCash" }, { value: "bank", label: "Bank Account" }].map((opt) => (
                        <button
                          key={opt.value}
                          type="button"
                          onClick={() => setOrgForm((f) => ({ ...f, payout_method: opt.value }))}
                          className={`px-3.5 py-1.5 rounded-lg text-sm font-heading font-semibold transition-colors ${
                            orgForm.payout_method === opt.value
                              ? "bg-primary text-primary-foreground"
                              : "text-muted-foreground hover:text-foreground"
                          }`}
                        >
                          {opt.label}
                        </button>
                      ))}
                    </div>

                    {orgForm.payout_method === "jazzcash" ? (
                      <div>
                        <input
                          required
                          value={orgForm.jazzcash_number}
                          onChange={setOrg("jazzcash_number")}
                          placeholder="JazzCash number, e.g. 03001234567"
                          className={orgInputClass(submitted && jazzcashNumberError)}
                        />
                        {submitted && jazzcashNumberError && (
                          <p className="mt-1.5 text-[11px] text-destructive px-1">{jazzcashNumberError}</p>
                        )}
                      </div>
                    ) : (
                      <div className="space-y-3">
                        <div>
                          <input
                            required
                            value={orgForm.bank_name}
                            onChange={setOrg("bank_name")}
                            placeholder="Bank name"
                            className={orgInputClass(submitted && bankNameError)}
                          />
                          {submitted && bankNameError && (
                            <p className="mt-1.5 text-[11px] text-destructive px-1">{bankNameError}</p>
                          )}
                        </div>
                        <div>
                          <input
                            required
                            value={orgForm.bank_account_title}
                            onChange={setOrg("bank_account_title")}
                            placeholder="Account title"
                            className={orgInputClass(submitted && bankAccountTitleError)}
                          />
                          {submitted && bankAccountTitleError && (
                            <p className="mt-1.5 text-[11px] text-destructive px-1">{bankAccountTitleError}</p>
                          )}
                        </div>
                        <div>
                          <input
                            required
                            value={orgForm.bank_account_number}
                            onChange={setOrg("bank_account_number")}
                            placeholder="Account number / IBAN"
                            className={orgInputClass(submitted && bankAccountNumberError)}
                          />
                          {submitted && bankAccountNumberError && (
                            <p className="mt-1.5 text-[11px] text-destructive px-1">{bankAccountNumberError}</p>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {error && (
                <motion.div
                  initial={{ opacity: 0, y: -5 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="text-sm text-destructive bg-destructive/10 border border-destructive/30 rounded-lg px-3 py-2"
                >
                  {error}
                </motion.div>
              )}

              {info && (
                <motion.div
                  initial={{ opacity: 0, y: -5 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="text-sm text-primary bg-primary/10 border border-primary/30 rounded-lg px-3 py-2"
                >
                  {info}
                </motion.div>
              )}

              {mode === "login" && (
                <div className="flex justify-end">
                  <button
                    type="button"
                    onClick={() => navigate("/forgot-password")}
                    className="text-xs font-heading font-semibold text-primary hover:underline"
                  >
                    Forgot password?
                  </button>
                </div>
              )}

              <div className="flex gap-3">
                {isOrgStep2 && (
                  <button
                    type="button"
                    onClick={() => { setOrgStep(1); setError(""); setSubmitted(false); }}
                    className="flex items-center justify-center gap-2 px-4 py-3.5 rounded-xl font-heading font-bold text-base border border-border hover:border-primary/60 transition-colors"
                  >
                    <ArrowLeft className="w-4 h-4" />
                    Back
                  </button>
                )}
                <button
                  type="submit"
                  disabled={loading}
                  className="flex-1 flex items-center justify-center gap-2 py-3.5 rounded-xl font-heading font-bold text-base bg-primary text-primary-foreground hover:shadow-[0_0_28px_hsl(186_100%_50%/0.5)] transition-shadow disabled:opacity-60"
                >
                  {loading ? (
                    <Loader2 className="w-5 h-5 animate-spin" />
                  ) : (
                    <>
                      {mode === "login" ? "Sign In" : role === "organizer" && orgStep === 1 ? "Next" : "Create Account"}
                      <ArrowRight className="w-4 h-4" />
                    </>
                  )}
                </button>
              </div>
            </form>

            {/* Divider */}
            <div className="flex items-center gap-3 my-5">
              <div className="flex-1 h-px bg-border" />
              <span className="text-xs text-muted-foreground font-heading">OR</span>
              <div className="flex-1 h-px bg-border" />
            </div>

            <button
              type="button"
              onClick={() => startGoogleSignIn(from).catch((err) => setError(err.message))}
              className="w-full flex items-center justify-center gap-3 py-3 rounded-xl font-heading font-semibold text-sm glass hover:neon-border transition-all border border-border"
            >
              <GoogleIcon />
              Continue with Google
            </button>

            <p className="mt-5 text-center text-xs text-muted-foreground">
              By continuing you agree to our{" "}
              <span className="text-primary hover:underline cursor-pointer">Terms</span> &{" "}
              <span className="text-primary hover:underline cursor-pointer">Privacy Policy</span>.
            </p>
              </>
            )}
          </div>
        </motion.div>
      </div>
    </div>
  );
}

function RoleCard({ active, onClick, icon: Icon, label, desc }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex flex-col items-start gap-1 p-3 rounded-xl border text-left transition-all ${
        active ? "border-primary bg-primary/10 neon-border" : "border-border bg-muted/30 hover:border-border/80"
      }`}
    >
      <Icon className={`w-5 h-5 ${active ? "text-primary" : "text-muted-foreground"}`} />
      <div className="font-heading font-bold text-sm">{label}</div>
      <div className="text-[11px] text-muted-foreground">{desc}</div>
    </button>
  );
}

function Field({ icon: Icon, trailing = null, type = "text", error = "", ...props }) {
  return (
    <div>
      <div className="relative">
        <Icon className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
        <input
          type={type}
          {...props}
          className={`w-full pl-11 pr-11 py-3 rounded-xl bg-muted/40 border text-sm outline-none focus:neon-border transition-all placeholder:text-muted-foreground/70 ${
            error ? "border-destructive focus:border-destructive" : "border-border focus:border-primary"
          }`}
        />
        {trailing && <div className="absolute right-3.5 top-1/2 -translate-y-1/2">{trailing}</div>}
      </div>
      {error && <p className="mt-1.5 text-[11px] text-destructive px-1">{error}</p>}
    </div>
  );
}

function PasswordChecklist({ password }) {
  return (
    <div className="grid grid-cols-2 gap-x-3 gap-y-1 -mt-1 px-1">
      {PASSWORD_CHECKS.map((c) => {
        const ok = c.test(password);
        return (
          <div key={c.key} className={`flex items-center gap-1.5 text-[11px] transition-colors ${ok ? "text-primary" : "text-muted-foreground"}`}>
            {ok ? <CheckCircle2 className="w-3 h-3 shrink-0" /> : <Circle className="w-3 h-3 shrink-0" />}
            {c.label}
          </div>
        );
      })}
    </div>
  );
}

function GoogleIcon() {
  return (
    <svg className="w-5 h-5" viewBox="0 0 24 24">
      <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
      <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
      <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z" />
      <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
    </svg>
  );
}