import React, { createContext, useContext, useState, useEffect, useCallback } from "react";
import { api, tokenStorage, refreshToken } from "./api";

const AuthContext = createContext(null);
export const useAuth = () => useContext(AuthContext);

export function AppAuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchMe = useCallback(async () => {
    // The access token lives in memory only, so it's gone on every page
    // reload even for an already-logged-in user — attempt a silent refresh
    // against the httpOnly refresh cookie before concluding they're logged
    // out. This is what keeps "stay logged in across a reload" working now
    // that nothing token-related is in localStorage anymore.
    if (!tokenStorage.get()) {
      const refreshed = await refreshToken();
      if (!refreshed) {
        setUser(null);
        setLoading(false);
        return;
      }
    }
    try {
      const me = await api.get("/api/auth/me/");
      setUser(me);
    } catch {
      tokenStorage.clear();
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchMe();
  }, [fetchMe]);

  const login = async (email, password) => {
    const data = await api.post("/api/auth/login/", { email, password }, { withCredentials: true });
    tokenStorage.set(data.access || data.access_token);
    const me = data.user || (await api.get("/api/auth/me/"));
    setUser(me);
    return me;
  };

  const register = async (payload, opts) => {
    const data = await api.post("/api/auth/register/", payload, { ...opts, withCredentials: true });
    if (data.access || data.access_token) {
      tokenStorage.set(data.access || data.access_token);
      setUser(data.user || (await api.get("/api/auth/me/").catch(() => null)));
    }
    return data;
  };

  const googleLogin = async (idToken, state) => {
    const data = await api.post(
      "/api/auth/google-login/", { id_token: idToken, state }, { withCredentials: true },
    );
    tokenStorage.set(data.access || data.access_token);
    setUser(data.user);
    return data.user;
  };

  const logout = async () => {
    try {
      // Backend now reads the refresh token from the httpOnly cookie
      // itself — nothing to send in the body anymore.
      await api.post("/api/auth/logout/", {}, { withCredentials: true });
    } catch {
      /* ignore — logout proceeds locally either way */
    }
    tokenStorage.clear();
    setUser(null);
    window.location.href = "/login";
  };

  // Blacklists every refresh token for this account (core.tokens.revoke_all_sessions),
  // not just this browser's — for a user who suspects a device they're not
  // holding right now (a shared computer, a stolen laptop) still has a
  // valid session. This browser's own tokens are cleared the same as a
  // normal logout since its refresh token is blacklisted too. Unlike
  // logout(), a failure here is surfaced rather than swallowed — if the
  // call didn't succeed, the user's other sessions weren't actually
  // revoked, and silently redirecting to /login would hide that.
  const logoutAllSessions = async () => {
    await api.post("/api/auth/logout-all/", {}, { withCredentials: true });
    tokenStorage.clear();
    setUser(null);
    window.location.href = "/login";
  };

  const value = {
    user, loading, login, register, googleLogin, logout, logoutAllSessions, refreshUser: fetchMe, setUser,
  };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}