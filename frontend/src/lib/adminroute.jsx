import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "./appauth";

export default function AdminRoute() {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div className="fixed inset-0 grid place-items-center bg-background">
        <div className="w-10 h-10 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  }

  if (!user.is_staff) {
    return <Navigate to="/" replace />;
  }

  return <Outlet />;
}
