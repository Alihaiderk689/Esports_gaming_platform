import { useEffect, useState } from "react";
import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "./appauth";
import { api } from "./api";

export default function OrganizerOrAdminRoute() {
  const { user, loading } = useAuth();
  const [checking, setChecking] = useState(true);
  const [allowed, setAllowed] = useState(false);

  useEffect(() => {
    if (loading || !user) {
      setChecking(false);
      return;
    }
    if (user.is_staff) {
      setAllowed(true);
      setChecking(false);
      return;
    }
    api
      .get("/api/organizer/status/")
      .then((data) => setAllowed(data.status === "approved"))
      .catch(() => setAllowed(false))
      .finally(() => setChecking(false));
  }, [user, loading]);

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
    return <Navigate to="/tournaments" replace />;
  }

  return <Outlet />;
}
