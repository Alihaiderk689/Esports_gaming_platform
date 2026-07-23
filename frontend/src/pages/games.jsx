import React, { useEffect, useMemo, useState } from "react";
import { Search, Loader2, Gamepad2 } from "lucide-react";
import { api } from "@/lib/api";

export default function Games() {
  const [games, setGames] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");

  useEffect(() => {
    api
      .get("/api/games/")
      .then(setGames)
      .catch((e) => setError(e.message || "Failed to load games."))
      .finally(() => setLoading(false));
  }, []);

  const visible = useMemo(() => {
    const q = search.trim().toLowerCase();
    return games
      .filter((g) => g.is_active)
      .filter((g) => !q
        || g.name.toLowerCase().includes(q)
        || g.genre.toLowerCase().includes(q)
        || g.platform.toLowerCase().includes(q)
        || g.categories.some((c) => c.name.toLowerCase().includes(q)));
  }, [games, search]);

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 py-10 sm:py-14">
      <h1 className="font-display font-extrabold text-4xl gradient-text mb-3">Games</h1>
      <p className="text-muted-foreground max-w-2xl mb-8">
        Every title tournaments are run on this platform. Browse the full roster.
      </p>

      <div className="relative max-w-sm mb-8">
        <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search games…"
          className="w-full pl-10 pr-4 py-2.5 rounded-xl bg-muted/40 border border-border text-sm outline-none focus:border-primary"
        />
      </div>

      {loading && (
        <div className="flex justify-center py-16 text-muted-foreground">
          <Loader2 className="w-6 h-6 animate-spin" />
        </div>
      )}

      {error && (
        <div className="text-sm text-destructive bg-destructive/10 border border-destructive/30 rounded-lg px-3 py-2 inline-block">
          {error}
        </div>
      )}

      {!loading && !error && visible.length === 0 && (
        <p className="text-sm text-muted-foreground">No games match your search.</p>
      )}

      {!loading && !error && visible.length > 0 && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 sm:gap-6">
          {visible.map((g) => (
            <div
              key={g.id}
              className="group relative aspect-[3/4] rounded-2xl overflow-hidden glass border border-border/60"
            >
              <img
                src={g.logo_url || `https://placehold.co/600x800/11131F/00F0FF?text=${encodeURIComponent(g.name)}`}
                alt={g.name}
                className="absolute inset-0 w-full h-full object-cover opacity-60 group-hover:opacity-80 group-hover:scale-110 transition-all duration-700"
              />
              <div className="absolute inset-0 bg-gradient-to-t from-background via-background/40 to-transparent" />
              <div className="relative h-full flex flex-col justify-end p-4 sm:p-5">
                {(g.genre || g.categories.length > 0) && (
                  <div className="flex flex-wrap gap-1 mb-2">
                    {g.genre && (
                      <span className="text-[10px] font-heading font-bold uppercase tracking-wider text-primary px-2 py-0.5 rounded-full bg-primary/10 border border-primary/30">
                        {g.genre}
                      </span>
                    )}
                    {g.categories.map((c) => (
                      <span
                        key={c.id}
                        className="text-[10px] font-heading font-bold uppercase tracking-wider text-muted-foreground px-2 py-0.5 rounded-full bg-muted/40 border border-border"
                      >
                        {c.name}
                      </span>
                    ))}
                  </div>
                )}
                <h3 className="font-display font-bold text-lg sm:text-xl group-hover:text-primary transition-colors flex items-center gap-1.5">
                  <Gamepad2 className="w-4 h-4 shrink-0" /> {g.name}
                </h3>
                {(g.platform || g.description) && (
                  <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">
                    {g.platform}{g.platform && g.description ? " · " : ""}{g.description}
                  </p>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
