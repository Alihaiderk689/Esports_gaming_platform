import { useEffect, useState } from "react";
import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "./appauth";
import { api } from "./api";

// `requireOrganizer` skips the is_staff bypass below — use it for actions that
// require an actual Organizer profile (e.g. creating a tournament, which the
// backend's IsApprovedOrganizer permission ties to organizer_profile, not
// is_staff), so staff without one aren't waved through the route only to hit
// a 403 on submit.
export default function OrganizerOrAdminRoute({ requireOrganizer = false, redirectTo = "/tournaments" }) {
  const { user, loading } = useAuth();
  const [checking, setChecking] = useState(true);
  const [allowed, setAllowed] = useState(false);

  useEffect(() => {
    if (loading || !user) {
      setChecking(false);
      return;
    }
    if (user.is_staff && !requireOrganizer) {
      setAllowed(true);
      setChecking(false);
      return;
    }
    api
      .get("/api/organizer/status/")
      .then((data) => setAllowed(data.status === "approved"))
      .catch(() => setAllowed(false))
      .finally(() => setChecking(false));
  }, [user, loading, requireOrganizer]);

  if (loading || checking) {
    return (
      <div className="fixed inset-0 grid place-items-center bg-background">
        <div className="w-10 h-10 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  if (!allowed) {
    return <Navigate to={redirectTo} replace />;
  }

  return <Outlet />;
}
