import React, { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { ArrowLeft, UserPlus, UserMinus, Loader2, Calendar } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/appauth";

function displayName(p) {
  return [p.first_name, p.last_name].filter(Boolean).join(" ") || p.email;
}

export default function PlayerDetail() {
  const { id } = useParams();
  const { user: me } = useAuth();
  const [player, setPlayer] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setLoading(true);
    setError("");
    api
      .get(`/api/players/${id}/`)
      .then(setPlayer)
      .catch((e) => setError(e.message || "Could not load this player."))
      .finally(() => setLoading(false));
  }, [id]);

  const toggleFollow = async () => {
    setSaving(true);
    setError("");
    try {
      if (player.is_following) {
        await api.delete(`/api/players/${id}/follow/`);
        setPlayer((p) => ({ ...p, is_following: false, followers_count: p.followers_count - 1 }));
      } else {
        await api.post(`/api/players/${id}/follow/`, {});
        setPlayer((p) => ({ ...p, is_following: true, followers_count: p.followers_count + 1 }));
      }
    } catch (e) {
      setError(e.message || "Could not update follow status.");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center py-20 text-muted-foreground">
        <Loader2 className="w-6 h-6 animate-spin" />
      </div>
    );
  }

  if (error && !player) {
    return (
      <div className="max-w-lg mx-auto px-4 py-16 text-center">
        <p className="text-sm text-destructive bg-destructive/10 border border-destructive/30 rounded-lg px-3 py-2 inline-block">
          {error}
        </p>
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto px-4 sm:px-6 py-10 sm:py-14">
      <Link to="/players" className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-primary mb-6">
        <ArrowLeft className="w-4 h-4" /> Back to players
      </Link>

      <div className="glass rounded-2xl border border-border/60 p-6 sm:p-8">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-4">
            <div className="w-16 h-16 rounded-full bg-gradient-to-br from-primary to-green-500 grid place-items-center font-display font-bold text-2xl text-background">
              {displayName(player).charAt(0).toUpperCase()}
            </div>
            <div>
              <h1 className="font-display font-extrabold text-2xl">{displayName(player)}</h1>
              <p className="text-sm text-muted-foreground">{player.email}</p>
            </div>
          </div>

          {me?.id !== player.id && (
            <button
              onClick={toggleFollow}
              disabled={saving}
              className={`inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-heading font-semibold transition-colors disabled:opacity-50 ${
                player.is_following ? "bg-muted text-muted-foreground" : "bg-primary text-primary-foreground"
              }`}
            >
              {player.is_following ? <UserMinus className="w-4 h-4" /> : <UserPlus className="w-4 h-4" />}
              {player.is_following ? "Unfollow" : "Follow"}
            </button>
          )}
        </div>

        {error && (
          <div className="mt-4 text-sm text-destructive bg-destructive/10 border border-destructive/30 rounded-lg px-3 py-2">
            {error}
          </div>
        )}

        <div className="mt-6 flex items-center gap-6 text-sm">
          <div>
            <span className="font-display font-bold text-lg">{player.followers_count}</span>{" "}
            <span className="text-muted-foreground">Followers</span>
          </div>
          <div>
            <span className="font-display font-bold text-lg">{player.following_count}</span>{" "}
            <span className="text-muted-foreground">Following</span>
          </div>
          <div className="flex items-center gap-1.5 text-muted-foreground">
            <Calendar className="w-3.5 h-3.5" />
            Joined {new Date(player.date_joined).toLocaleDateString()}
          </div>
        </div>
      </div>
    </div>
  );
}
