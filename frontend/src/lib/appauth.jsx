import React, { createContext, useContext, useState, useEffect, useCallback } from "react";
import { api, tokenStorage } from "./api";

const AuthContext = createContext(null);
export const useAuth = () => useContext(AuthContext);

export function AppAuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchMe = useCallback(async () => {
    if (!tokenStorage.get()) {
      setUser(null);
      setLoading(false);
      return;
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
    const data = await api.post("/api/auth/login/", { email, password });
    tokenStorage.set(data.access || data.access_token, data.refresh);
    const me = data.user || (await api.get("/api/auth/me/"));
    setUser(me);
    return me;
  };

  const register = async (payload, opts) => {
    const data = await api.post("/api/auth/register/", payload, opts);
    if (data.access || data.access_token) {
      tokenStorage.set(data.access || data.access_token, data.refresh);
      setUser(data.user || (await api.get("/api/auth/me/").catch(() => null)));
    }
    return data;
  };

  const googleLogin = async (idToken, state) => {
    const data = await api.post("/api/auth/google-login/", { id_token: idToken, state });
    tokenStorage.set(data.access || data.access_token, data.refresh);
    setUser(data.user);
    return data.user;
  };

  const logout = async () => {
    try {
      const refresh = tokenStorage.getRefresh();
      if (refresh) await api.post("/api/auth/logout/", { refresh });
    } catch {
      /* ignore */
    }
    tokenStorage.clear();
    setUser(null);
    window.location.href = "/login";
  };

  // Blacklists every refresh token for this account (core.tokens.revoke_all_sessions),
  // not just this browser's — for a user who suspects a device they're not
  // holding right now (a shared computer, a stolen laptop) still has a
  // valid session. This browser's own tokens are cleared the same as a
  // normal logout since its refresh token is blacklisted too.
  const logoutAllSessions = async () => {
    await api.post("/api/auth/logout-all/");
    tokenStorage.clear();
    setUser(null);
    window.location.href = "/login";
  };

  const value = {
    user, loading, login, register, googleLogin, logout, logoutAllSessions, refreshUser: fetchMe, setUser,
  };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}