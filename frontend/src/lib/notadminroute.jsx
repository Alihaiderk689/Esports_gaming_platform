import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "./appauth";

// Admins are restricted to the admin dashboard — bounce them off every
// player/organizer-facing page (including the public landing/games pages).
export default function NotAdminRoute() {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="fixed inset-0 grid place-items-center bg-background">
        <div className="w-10 h-10 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
      </div>
    );
  }

  if (user?.is_staff) {
    return <Navigate to="/admin" replace />;
  }

  return <Outlet />;
}
