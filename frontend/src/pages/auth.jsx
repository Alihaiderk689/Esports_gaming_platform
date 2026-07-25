import React, { useState, useEffect, useRef } from "react";
import { useNavigate, useLocation, Link } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { useAuth } from "@/lib/appauth";
import { api } from "@/lib/api";
import { Gamepad2, Mail, Lock, User, Eye, EyeOff, ArrowRight, Shield, Swords, CheckCircle2, Loader2 } from "lucide-react";

export default function Auth() {
  const { login, register, googleLogin } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const googleBtnRef = useRef(null);
  const [mode, setMode] = useState("login"); // login | signup
  const [role, setRole] = useState("user"); // user | organizer
  const [showPw, setShowPw] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [info, setInfo] = useState(location.state?.info || "");
  const [justRegistered, setJustRegistered] = useState(false);
  const [form, setForm] = useState({ full_name: "", email: "", password: "", confirm: "" });
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
    if (password.length < 8) return "Password must be at least 8 characters.";
    if (!/[A-Z]/.test(password)) return "Password must include an uppercase letter.";
    if (!/[a-z]/.test(password)) return "Password must include a lowercase letter.";
    if (!/[0-9]/.test(password)) return "Password must include a number.";
    if (!/[^A-Za-z0-9]/.test(password)) return "Password must include a special character.";
    return "";
  };

  const getOrganizerFormError = () => {
    if (!orgForm.company_name.trim()) return "Company / organization name is required.";
    if (!orgForm.cnic_document) return "Please upload your CNIC document.";
    if (!orgForm.company_document) return "Please upload a company document.";
    if (orgForm.payout_method === "jazzcash") {
      if (!orgForm.jazzcash_number.trim()) return "JazzCash number is required.";
    } else if (!orgForm.bank_name.trim() || !orgForm.bank_account_title.trim() || !orgForm.bank_account_number.trim()) {
      return "Bank name, account title, and account number are required.";
    }
    return "";
  };

  // Organizers (any application status) always land on their dashboard, never the
  // public landing page — only a non-organizer's own redirect-origin ("from") wins.
  const routeAfterLogin = async (loggedInUser) => {
    if (loggedInUser?.is_staff) {
      navigate("/admin", { replace: true });
      return;
    }
    try {
      await api.get("/api/organizer/status/");
      navigate("/dashboard", { replace: true });
    } catch {
      navigate(from, { replace: true });
    }
  };

  useEffect(() => {
    let cancelled = false;
    const tryInit = () => {
      if (cancelled) return;
      if (window.google?.accounts?.id) {
        window.google.accounts.id.initialize({
          client_id: import.meta.env.VITE_GOOGLE_CLIENT_ID,
          callback: async (response) => {
            setError("");
            try {
              const loggedInUser = await googleLogin(response.credential);
              await routeAfterLogin(loggedInUser);
            } catch (err) {
              setError(err.message || "Google sign-in failed. Please try again.");
            }
          },
        });
        if (googleBtnRef.current) {
          window.google.accounts.id.renderButton(googleBtnRef.current, {
            theme: "filled_black",
            size: "large",
            width: 400,
            text: "continue_with",
          });
        }
      } else {
        setTimeout(tryInit, 150);
      }
    };
    tryInit();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    setInfo("");
    if (mode === "signup") {
      const pwError = getPasswordError(form.password);
      if (pwError) {
        setError(pwError);
        return;
      }
      if (form.password !== form.confirm) {
        setError("Passwords do not match.");
        return;
      }
      if (role === "organizer") {
        const orgError = getOrganizerFormError();
        if (orgError) {
          setError(orgError);
          return;
        }
      }
    }
    setLoading(true);
    try {
      if (mode === "login") {
        const loggedInUser = await login(form.email, form.password);
        await routeAfterLogin(loggedInUser);
      } else {
        const [first_name, ...rest] = form.full_name.trim().split(/\s+/);
        const last_name = rest.join(" ");
        if (role === "organizer") {
          const fd = new FormData();
          fd.append("first_name", first_name);
          fd.append("last_name", last_name);
          fd.append("email", form.email);
          fd.append("password", form.password);
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
          await register({ first_name, last_name, email: form.email, password: form.password, role: "user" });
        }
        setMode("login");
        setForm((f) => ({ ...f, password: "", confirm: "" }));
        setOrgForm(emptyOrgForm);
        setInfo(
          role === "organizer"
            ? "Account created! Check your email to verify it, then sign in. Your organizer application is now under review."
            : "Account created! Check your email to verify it, then sign in.",
        );
        setJustRegistered(true);
      }
    } catch (err) {
      setError(err.message || "Something went wrong. Please try again.");
    } finally {
      setLoading(false);
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
            <div className="w-11 h-11 rounded-xl bg-gradient-to-br from-primary to-green-500 grid place-items-center neon-border">
              <Gamepad2 className="w-6 h-6 text-background" strokeWidth={2.5} />
            </div>
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
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-primary to-green-500 grid place-items-center">
              <Gamepad2 className="w-5 h-5 text-background" />
            </div>
            <div className="font-display font-extrabold tracking-wider">ESPORTS <span className="gradient-text">PK</span></div>
          </Link>

          <div className="glass rounded-2xl border border-border/60 p-6 sm:p-8">
            {/* Toggle */}
            <div className="relative flex p-1 rounded-xl bg-muted/50 mb-6">
              <motion.div
                className="absolute top-1 bottom-1 w-[calc(50%-4px)] rounded-lg bg-primary"
                animate={{ x: mode === "login" ? 0 : "100%" }}
                transition={{ type: "spring", damping: 26, stiffness: 300 }}
              />
              <button
                onClick={() => { setMode("login"); setError(""); setInfo(""); }}
                className={`relative flex-1 py-2.5 text-sm font-heading font-bold transition-colors ${mode === "login" ? "text-primary-foreground" : "text-muted-foreground"}`}
              >
                Sign In
              </button>
              <button
                onClick={() => { setMode("signup"); setError(""); setInfo(""); }}
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
              {mode === "signup" && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: "auto" }}
                  exit={{ opacity: 0, height: 0 }}
                  className="overflow-hidden mb-5"
                >
                  <div className="text-xs font-heading font-bold uppercase tracking-wider text-muted-foreground mb-2">
                    I am a…
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <RoleCard active={role === "user"} onClick={() => setRole("user")} icon={Gamepad2} label="Player" desc="Compete & follow" />
                    <RoleCard active={role === "organizer"} onClick={() => setRole("organizer")} icon={Shield} label="Organizer" desc="Host events" />
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            <form onSubmit={submit} className="space-y-4">
              {mode === "signup" && (
                <Field icon={User} placeholder="Full name" value={form.full_name} onChange={set("full_name")} required />
              )}
              <Field icon={Mail} type="email" placeholder="Email address" value={form.email} onChange={set("email")} required />
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
                  <p className="text-[11px] text-muted-foreground -mt-2 px-1">
                    At least 8 characters, with uppercase, lowercase, a number and a special character.
                  </p>
                  <Field
                    icon={Lock}
                    type={showPw ? "text" : "password"}
                    placeholder="Confirm password"
                    value={form.confirm}
                    onChange={set("confirm")}
                    required
                  />
                </>
              )}

              {mode === "signup" && role === "organizer" && (
                <div className="space-y-4 pt-4 border-t border-border/60">
                  <div className="text-xs font-heading font-bold uppercase tracking-wider text-muted-foreground">
                    Organizer application
                  </div>

                  <input
                    required
                    value={orgForm.company_name}
                    onChange={setOrg("company_name")}
                    placeholder="Company / organization name"
                    className="w-full px-3.5 py-2.5 rounded-xl bg-muted/40 border border-border text-sm outline-none focus:border-primary placeholder:text-muted-foreground/70"
                  />
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
                      <input
                        required
                        value={orgForm.jazzcash_number}
                        onChange={setOrg("jazzcash_number")}
                        placeholder="JazzCash number, e.g. 03001234567"
                        className="w-full px-3.5 py-2.5 rounded-xl bg-muted/40 border border-border text-sm outline-none focus:border-primary placeholder:text-muted-foreground/70"
                      />
                    ) : (
                      <div className="space-y-3">
                        <input
                          required
                          value={orgForm.bank_name}
                          onChange={setOrg("bank_name")}
                          placeholder="Bank name"
                          className="w-full px-3.5 py-2.5 rounded-xl bg-muted/40 border border-border text-sm outline-none focus:border-primary placeholder:text-muted-foreground/70"
                        />
                        <input
                          required
                          value={orgForm.bank_account_title}
                          onChange={setOrg("bank_account_title")}
                          placeholder="Account title"
                          className="w-full px-3.5 py-2.5 rounded-xl bg-muted/40 border border-border text-sm outline-none focus:border-primary placeholder:text-muted-foreground/70"
                        />
                        <input
                          required
                          value={orgForm.bank_account_number}
                          onChange={setOrg("bank_account_number")}
                          placeholder="Account number / IBAN"
                          className="w-full px-3.5 py-2.5 rounded-xl bg-muted/40 border border-border text-sm outline-none focus:border-primary placeholder:text-muted-foreground/70"
                        />
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
                  {justRegistered && (
                    <>
                      {" "}
                      <Link to="/verify-email" className="underline hover:no-underline">
                        Didn't get it? Resend.
                      </Link>
                    </>
                  )}
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

              <button
                type="submit"
                disabled={loading}
                className="w-full flex items-center justify-center gap-2 py-3.5 rounded-xl font-heading font-bold text-base bg-primary text-primary-foreground hover:shadow-[0_0_28px_hsl(186_100%_50%/0.5)] transition-shadow disabled:opacity-60"
              >
                {loading ? (
                  <Loader2 className="w-5 h-5 animate-spin" />
                ) : (
                  <>
                    {mode === "login" ? "Sign In" : "Create Account"}
                    <ArrowRight className="w-4 h-4" />
                  </>
                )}
              </button>
            </form>

            {/* Divider */}
            <div className="flex items-center gap-3 my-5">
              <div className="flex-1 h-px bg-border" />
              <span className="text-xs text-muted-foreground font-heading">OR</span>
              <div className="flex-1 h-px bg-border" />
            </div>

            {/* Google — a real (invisible) Google Identity button is stacked on top of
                this styled one so clicks land on Google's actual iframe while the
                visible UI stays consistent with the rest of the app. */}
            <div className="relative w-full h-[46px]">
              <button
                type="button"
                className="absolute inset-0 w-full flex items-center justify-center gap-3 py-3 rounded-xl font-heading font-semibold text-sm glass hover:neon-border transition-all border border-border pointer-events-none"
              >
                <GoogleIcon />
                Continue with Google
              </button>
              <div ref={googleBtnRef} className="absolute inset-0 overflow-hidden rounded-xl opacity-0" />
            </div>

            <p className="mt-5 text-center text-xs text-muted-foreground">
              By continuing you agree to our{" "}
              <span className="text-primary hover:underline cursor-pointer">Terms</span> &{" "}
              <span className="text-primary hover:underline cursor-pointer">Privacy Policy</span>.
            </p>
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

function Field({ icon: Icon, trailing, type = "text", ...props }) {
  return (
    <div className="relative">
      <Icon className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
      <input
        type={type}
        {...props}
        className="w-full pl-11 pr-11 py-3 rounded-xl bg-muted/40 border border-border text-sm outline-none focus:border-primary focus:neon-border transition-all placeholder:text-muted-foreground/70"
      />
      {trailing && <div className="absolute right-3.5 top-1/2 -translate-y-1/2">{trailing}</div>}
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