import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AlertTriangle, Loader2 } from "lucide-react";
import { useAuth } from "@/lib/appauth";
import { consumeGoogleCallback } from "@/lib/googleAuth";
import { routeAfterLogin } from "@/lib/routeAfterLogin";

export default function GoogleCallback() {
  const { googleLogin } = useAuth();
  const navigate = useNavigate();
  const [error, setError] = useState("");
  const ran = useRef(false);

  useEffect(() => {
    if (ran.current) return;
    ran.current = true;

    (async () => {
      let idToken, state, from;
      try {
        ({ idToken, state, from } = consumeGoogleCallback());
      } catch (err) {
        setError(err.message);
        return;
      }
      try {
        const loggedInUser = await googleLogin(idToken, state);
        await routeAfterLogin(navigate, loggedInUser, from);
      } catch (err) {
        setError(err.message || "Google sign-in failed. Please try again.");
      }
    })();
  }, [googleLogin, navigate]);

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center p-6">
        <div className="max-w-md w-full text-center space-y-4">
          <div className="mx-auto w-14 h-14 rounded-2xl bg-destructive/10 border border-destructive/30 grid place-items-center">
            <AlertTriangle className="w-6 h-6 text-destructive" />
          </div>
          <h1 className="font-display font-bold text-xl">Sign-in failed</h1>
          <p className="text-muted-foreground text-sm">{error}</p>
          <button
            onClick={() => navigate("/login", { replace: true })}
            className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl font-heading font-bold text-sm bg-primary text-primary-foreground"
          >
            Back to sign in
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center">
      <Loader2 className="w-8 h-8 animate-spin text-primary" />
    </div>
  );
}
