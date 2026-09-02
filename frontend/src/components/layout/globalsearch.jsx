import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Loader2, UserMinus, UserPlus } from "lucide-react";
import { Command, CommandInput, CommandList, CommandEmpty, CommandGroup, CommandItem } from "@/components/ui/command";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { api } from "@/lib/api";
import { initials, displayName } from "@/lib/playerDisplay";
import RoleBadge from "@/components/players/rolebadge";
import { toast } from "@/components/ui/use-toast";

export default function GlobalSearch({ open, onOpenChange }) {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [followingId, setFollowingId] = useState(null);

  useEffect(() => {
    if (!open) {
      setQuery("");
      setResults([]);
    }
  }, [open]);

  useEffect(() => {
    if (!query.trim()) {
      setResults([]);
      return;
    }
    setLoading(true);
    const t = setTimeout(() => {
      api
        .get("/api/players/", { query: { search: query } })
        .then(setResults)
        .catch(() => setResults([]))
        .finally(() => setLoading(false));
    }, 300);
    return () => clearTimeout(t);
  }, [query]);

  const toggleFollow = async (p, e) => {
    e.stopPropagation();
    setFollowingId(p.id);
    try {
      if (p.is_following) {
        await api.delete(`/api/players/${p.id}/follow/`);
      } else {
        await api.post(`/api/players/${p.id}/follow/`, {});
      }
      setResults((list) => list.map((x) => (x.id === p.id ? { ...x, is_following: !x.is_following } : x)));
    } catch (e) {
      toast({
        variant: "destructive",
        title: "Could not update follow status",
        description: e.message || "Please try again.",
      });
    } finally {
      setFollowingId(null);
    }
  };

  const openProfile = (p) => {
    onOpenChange(false);
    navigate(`/players/${p.id}`);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="overflow-hidden p-0">
        <Command
          shouldFilter={false}
          className="[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:font-medium [&_[cmdk-group-heading]]:text-muted-foreground [&_[cmdk-group]:not([hidden])_~[cmdk-group]]:pt-0 [&_[cmdk-group]]:px-2 [&_[cmdk-input-wrapper]_svg]:h-5 [&_[cmdk-input-wrapper]_svg]:w-5 [&_[cmdk-input]]:h-12 [&_[cmdk-item]]:px-2 [&_[cmdk-item]]:py-3"
        >
          <CommandInput
            value={query}
            onValueChange={setQuery}
            placeholder="Search players and organizers…"
          />
          <CommandList>
            {loading && (
              <div className="py-6 flex justify-center">
                <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
              </div>
            )}
            {!loading && query.trim() && (
              <CommandEmpty>No players or organizers found.</CommandEmpty>
            )}
            {!loading && !query.trim() && (
              <div className="py-6 text-center text-sm text-muted-foreground">
                Type to search players and organizers.
              </div>
            )}
            {!loading && results.length > 0 && (
              <CommandGroup heading="Results">
                {results.map((p) => (
                  <CommandItem
                    key={p.id}
                    value={String(p.id)}
                    onSelect={() => openProfile(p)}
                    className="flex items-center gap-3 cursor-pointer"
                  >
                    <div className="w-8 h-8 shrink-0 rounded-full bg-gradient-to-br from-primary to-green-500 grid place-items-center font-display font-bold text-xs text-background">
                      {initials(p)}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-heading font-semibold text-sm truncate">{displayName(p)}</span>
                        <RoleBadge role={p.role} />
                      </div>
                      <p className="text-xs text-muted-foreground">{p.followers_count} followers</p>
                    </div>
                    <button
                      onClick={(e) => toggleFollow(p, e)}
                      disabled={followingId === p.id}
                      className={`shrink-0 inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-heading font-semibold transition-colors disabled:opacity-50 ${
                        p.is_following ? "bg-muted text-muted-foreground" : "bg-primary text-primary-foreground"
                      }`}
                    >
                      {p.is_following ? <UserMinus className="w-3.5 h-3.5" /> : <UserPlus className="w-3.5 h-3.5" />}
                      {p.is_following ? "Unfollow" : "Follow"}
                    </button>
                  </CommandItem>
                ))}
              </CommandGroup>
            )}
          </CommandList>
        </Command>
      </DialogContent>
    </Dialog>
  );
}
