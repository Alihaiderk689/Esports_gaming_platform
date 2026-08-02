import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "./appauth";

// Guest-only pages (currently just /login) — an already-authenticated visitor
// gets redirected to their own landing page instead of seeing the form again.
export default function GuestRoute() {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="fixed inset-0 grid place-items-center bg-background">
        <div className="w-10 h-10 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
      </div>
    );
  }

  if (user) {
    return <Navigate to={user.is_staff ? "/admin" : "/dashboard"} replace />;
  }

  return <Outlet />;
}
