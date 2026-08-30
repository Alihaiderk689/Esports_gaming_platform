import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Search, UserPlus, UserMinus, Loader2, Users as UsersIcon } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/appauth";

const TABS = [
  { key: "all", label: "All Players" },
  { key: "top", label: "Top Players" },
  { key: "following", label: "Following" },
];

function initials(p) {
  const name = [p.first_name, p.last_name].filter(Boolean).join(" ") || p.email;
  return name.charAt(0).toUpperCase();
}

function displayName(p) {
  return [p.first_name, p.last_name].filter(Boolean).join(" ") || p.email;
}

export default function Players() {
  const { user: me } = useAuth();
  const [tab, setTab] = useState("all");
  const [search, setSearch] = useState("");
  const [players, setPlayers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [followingId, setFollowingId] = useState(null);

  const load = (t, q) => {
    setLoading(true);
    setError("");
    const path = t === "top" ? "/api/players/top/" : t === "following" ? "/api/players/following/" : "/api/players/";
    const opts = t === "all" ? { query: { search: q } } : undefined;
    api
      .get(path, opts)
      .then(setPlayers)
      .catch((e) => setError(e.message || "Failed to load players."))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    if (tab !== "all") {
      load(tab);
      return;
    }
    const t = setTimeout(() => load("all", search), 300);
    return () => clearTimeout(t);
  }, [tab, search]);

  const toggleFollow = async (p) => {
    setFollowingId(p.id);
    setError("");
    try {
      if (p.is_following) {
        await api.delete(`/api/players/${p.id}/follow/`);
      } else {
        await api.post(`/api/players/${p.id}/follow/`, {});
      }
      setPlayers((list) =>
        tab === "following" && p.is_following
          ? list.filter((x) => x.id !== p.id)
          : list.map((x) => (x.id === p.id ? { ...x, is_following: !x.is_following } : x))
      );
    } catch (e) {
      setError(e.message || "Could not update follow status.");
    } finally {
      setFollowingId(null);
    }
  };

  return (
    <div className="mx-auto max-w-7xl px-4 sm:px-6 py-10 sm:py-14">
      <h1 className="font-display font-extrabold text-4xl gradient-text mb-1">Players</h1>
      <p className="text-muted-foreground mb-8">Discover and follow Pakistan's competitive gamers.</p>

      <div className="flex flex-wrap items-center justify-between gap-4 mb-6">
        <div className="flex gap-1 p-1 rounded-xl bg-muted/30 border border-border/60 w-fit">
          {TABS.map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`px-3.5 py-1.5 rounded-lg text-sm font-heading font-semibold transition-colors ${
                tab === t.key ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {tab === "all" && (
          <div className="relative max-w-xs w-full">
            <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search players…"
              className="w-full pl-10 pr-4 py-2.5 rounded-xl bg-muted/40 border border-border text-sm outline-none focus:border-primary focus:neon-border transition-all placeholder:text-muted-foreground/70"
            />
          </div>
        )}
      </div>

      {error && (
        <div className="mb-4 text-sm text-destructive bg-destructive/10 border border-destructive/30 rounded-lg px-3 py-2">
          {error}
        </div>
      )}

      {loading ? (
        <div className="flex justify-center py-20 text-muted-foreground">
          <Loader2 className="w-6 h-6 animate-spin" />
        </div>
      ) : players.length === 0 ? (
        <div className="text-center py-20 text-muted-foreground">
          <UsersIcon className="w-8 h-8 mx-auto mb-3 opacity-50" />
          {tab === "following" ? "You're not following anyone yet." : "No players found."}
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {players.map((p) => (
            <div key={p.id} className="glass rounded-xl border border-border/60 p-5 flex items-center gap-4">
              <Link to={`/players/${p.id}`} className="shrink-0">
                <div className="w-12 h-12 rounded-full bg-gradient-to-br from-primary to-green-500 grid place-items-center font-display font-bold text-lg text-background">
                  {initials(p)}
                </div>
              </Link>
              <div className="flex-1 min-w-0">
                <Link to={`/players/${p.id}`} className="font-heading font-bold text-sm hover:text-primary truncate block">
                  {displayName(p)}
                </Link>
                <p className="text-xs text-muted-foreground">{p.followers_count} followers</p>
              </div>
              {me?.id !== p.id && (
                <button
                  onClick={() => toggleFollow(p)}
                  disabled={followingId === p.id}
                  className={`shrink-0 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-heading font-semibold transition-colors disabled:opacity-50 ${
                    p.is_following ? "bg-muted text-muted-foreground" : "bg-primary text-primary-foreground"
                  }`}
                >
                  {p.is_following ? <UserMinus className="w-3.5 h-3.5" /> : <UserPlus className="w-3.5 h-3.5" />}
                  {p.is_following ? "Unfollow" : "Follow"}
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
