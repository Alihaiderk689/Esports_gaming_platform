import { lazy, Suspense } from "react";
import { Toaster } from "@/components/ui/toaster";
import { BrowserRouter as Router, Route, Routes } from "react-router-dom";
import PageNotFound from "@/lib/pagenotfound";
import { AppAuthProvider, useAuth } from "@/lib/appauth";
import ScrollToTop from "@/components/scrolltotop";
import ProtectedRoute from "@/lib/protectedroute";
import GuestRoute from "@/lib/guestroute";
import AdminRoute from "@/lib/adminroute";
import NotAdminRoute from "@/lib/notadminroute";
import OrganizerOrAdminRoute from "@/lib/organizerroute";
import AppLayout from "@/components/layout/applayout";
import AdminLayout from "@/components/layout/adminlayout";

// Route-level code splitting — each page is only fetched when its route is
// actually visited, instead of every page's code (and its dependencies —
// recharts, react-quill, jspdf, ...) being bundled into the single chunk
// loaded on first visit to any route, including /login.
const Landing = lazy(() => import("@/pages/landing"));
const Auth = lazy(() => import("@/pages/auth"));
const GoogleCallback = lazy(() => import("@/pages/googlecallback"));
const ForgotPassword = lazy(() => import("@/pages/forgotpassword"));
const ResetPassword = lazy(() => import("@/pages/resetpassword"));
const VerifyEmail = lazy(() => import("@/pages/verifyemail"));
const AccountSettings = lazy(() => import("@/pages/accountsettings"));
const AdminOverview = lazy(() => import("@/pages/adminoverview"));
const AdminUsers = lazy(() => import("@/pages/adminusers"));
const AdminOrganizers = lazy(() => import("@/pages/adminorganizers"));
const AdminTournaments = lazy(() => import("@/pages/admintournaments"));
const AdminReviewRequests = lazy(() => import("@/pages/adminreviewrequests"));
const AdminDisputes = lazy(() => import("@/pages/admindisputes"));
const AdminGames = lazy(() => import("@/pages/admingames"));
const AdminPartners = lazy(() => import("@/pages/adminpartners"));
const AdminRulebooks = lazy(() => import("@/pages/adminrulebooks"));
const AdminSettings = lazy(() => import("@/pages/adminsettings"));
const Players = lazy(() => import("@/pages/players"));
const PlayerDetail = lazy(() => import("@/pages/playerdetail"));
const Tournaments = lazy(() => import("@/pages/tournaments"));
const TournamentDetail = lazy(() => import("@/pages/tournamentdetail"));
const BracketPage = lazy(() => import("@/pages/bracketpage"));
const CreateTournament = lazy(() => import("@/pages/createtournament"));
const CreateHub = lazy(() => import("@/pages/createhub"));
const MyTournaments = lazy(() => import("@/pages/mytournaments"));
const EditTournament = lazy(() => import("@/pages/edittournament"));
const Organizer = lazy(() => import("@/pages/organizer"));
const Games = lazy(() => import("@/pages/games"));
const GameDetail = lazy(() => import("@/pages/gamedetail"));
const About = lazy(() => import("@/pages/about"));
const Dashboard = lazy(() => import("@/pages/dashboard"));

const RouteFallback = () => (
  <div className="fixed inset-0 flex items-center justify-center">
    <div className="w-8 h-8 border-4 border-slate-200 border-t-slate-800 rounded-full animate-spin"></div>
  </div>
);

const AuthenticatedApp = () => {
  const { loading } = useAuth();

  if (loading) {
    return <RouteFallback />;
  }

  return (
    <Suspense fallback={<RouteFallback />}>
    <Routes>
      <Route element={<GuestRoute />}>
        <Route path="/login" element={<Auth />} />
        <Route path="/auth/google/callback" element={<GoogleCallback />} />
      </Route>
      <Route path="/forgot-password" element={<ForgotPassword />} />
      <Route path="/reset-password" element={<ResetPassword />} />
      <Route path="/verify-email" element={<VerifyEmail />} />
      <Route element={<AppLayout />}>
        <Route element={<NotAdminRoute />}>
          <Route path="/games" element={<Games />} />
          <Route path="/games/:slug" element={<GameDetail />} />
          <Route path="/about" element={<About />} />
          {/* Public browsing, same tier as /games — the backing API
              (/api/tournaments/) is already unauthenticated-readable, and this
              page already degrades gracefully with no session. */}
          <Route path="/tournaments" element={<Tournaments />} />
          <Route element={<ProtectedRoute />}>
            {/* Landing ("/") is the authenticated home — an unauthenticated
                visitor is bounced to /login instead of seeing it. */}
            <Route path="/" element={<Landing />} />
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/account" element={<AccountSettings />} />
            {/* Any authenticated non-staff user (player or organizer) can browse
                and follow other players/organizers — not organizer/admin-only. */}
            <Route path="/players" element={<Players />} />
            <Route path="/players/:id" element={<PlayerDetail />} />
            <Route element={<OrganizerOrAdminRoute />}>
              <Route path="/create" element={<CreateHub />} />
              <Route path="/my-tournaments" element={<MyTournaments />} />
              <Route path="/tournaments/:id/edit" element={<EditTournament />} />
            </Route>
            <Route element={<OrganizerOrAdminRoute requireOrganizer redirectTo="/organizer" />}>
              <Route path="/tournaments/create" element={<CreateTournament />} />
            </Route>
            <Route path="/tournaments/:id" element={<TournamentDetail />} />
            <Route path="/tournaments/:id/bracket" element={<BracketPage />} />
            <Route path="/organizer" element={<Organizer />} />
          </Route>
        </Route>
        <Route element={<AdminRoute />}>
          <Route path="/admin" element={<AdminLayout />}>
            <Route index element={<AdminOverview />} />
            <Route path="users" element={<AdminUsers />} />
            <Route path="organizers" element={<AdminOrganizers />} />
            <Route path="tournaments" element={<AdminTournaments />} />
            <Route path="review-requests" element={<AdminReviewRequests />} />
            <Route path="disputes" element={<AdminDisputes />} />
            <Route path="games" element={<AdminGames />} />
            <Route path="partners" element={<AdminPartners />} />
            <Route path="rulebooks" element={<AdminRulebooks />} />
            <Route path="settings" element={<AdminSettings />} />
          </Route>
        </Route>
      </Route>
      <Route path="*" element={<PageNotFound />} />
    </Routes>
    </Suspense>
  );
};

function App() {
  return (
    <AppAuthProvider>
      <Router>
        <ScrollToTop />
        <AuthenticatedApp />
      </Router>
      <Toaster />
    </AppAuthProvider>
  );
}

export default App;