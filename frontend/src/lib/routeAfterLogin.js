import { api } from "@/lib/api";

// Organizers (any application status) always land on their dashboard, never the
// public landing page — only a non-organizer's own redirect-origin ("from") wins.
export async function routeAfterLogin(navigate, loggedInUser, from = "/") {
  if (loggedInUser?.is_staff) {
    navigate("/admin", { replace: true });
    return;
  }
  try {
    await api.get("/api/organizer/status/");
    navigate("/dashboard", { replace: true });
  } catch {
    navigate(from, { replace: true });
  }
}
