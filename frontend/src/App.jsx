import { Toaster } from "@/components/ui/toaster";
import { QueryClientProvider } from "@tanstack/react-query";
import { queryClientInstance } from "@/lib/query-client";
import { BrowserRouter as Router, Route, Routes } from "react-router-dom";
import PageNotFound from "@/lib/pagenotfound";
import { AppAuthProvider, useAuth } from "@/lib/appauth";
import ScrollToTop from "@/components/scrolltotop";
import ProtectedRoute from "@/lib/protectedroute";
import AdminRoute from "@/lib/adminroute";
import NotAdminRoute from "@/lib/notadminroute";
import OrganizerOrAdminRoute from "@/lib/organizerroute";
import AppLayout from "@/components/layout/applayout";
import AdminLayout from "@/components/layout/adminlayout";
import Landing from "@/pages/landing";
import Auth from "@/pages/auth";
import ForgotPassword from "@/pages/forgotpassword";
import ResetPassword from "@/pages/resetpassword";
import VerifyEmail from "@/pages/verifyemail";
import AccountSettings from "@/pages/accountsettings";
import AdminOverview from "@/pages/adminoverview";
import AdminUsers from "@/pages/adminusers";
import AdminOrganizers from "@/pages/adminorganizers";
import AdminTournaments from "@/pages/admintournaments";
import AdminGames from "@/pages/admingames";
import AdminPartners from "@/pages/adminpartners";
import AdminRulebooks from "@/pages/adminrulebooks";
import AdminSettings from "@/pages/adminsettings";
import Players from "@/pages/players";
import PlayerDetail from "@/pages/playerdetail";
import Tournaments from "@/pages/tournaments";
import TournamentDetail from "@/pages/tournamentdetail";
import BracketPage from "@/pages/bracketpage";
import CreateTournament from "@/pages/createtournament";
import CreateHub from "@/pages/createhub";
import MyTournaments from "@/pages/mytournaments";
import EditTournament from "@/pages/edittournament";
import Organizer from "@/pages/organizer";
import Games from "@/pages/games";
import Dashboard from "@/pages/dashboard";

const AuthenticatedApp = () => {
  const { loading } = useAuth();

  if (loading) {
    return (
      <div className="fixed inset-0 flex items-center justify-center">
        <div className="w-8 h-8 border-4 border-slate-200 border-t-slate-800 rounded-full animate-spin"></div>
      </div>
    );
  }

  return (
    <Routes>
      <Route path="/login" element={<Auth />} />
      <Route path="/forgot-password" element={<ForgotPassword />} />
      <Route path="/reset-password" element={<ResetPassword />} />
      <Route path="/verify-email" element={<VerifyEmail />} />
      <Route element={<AppLayout />}>
        <Route element={<NotAdminRoute />}>
          <Route path="/" element={<Landing />} />
          <Route path="/games" element={<Games />} />
          <Route element={<ProtectedRoute />}>
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/account" element={<AccountSettings />} />
            <Route element={<OrganizerOrAdminRoute />}>
              <Route path="/players" element={<Players />} />
              <Route path="/players/:id" element={<PlayerDetail />} />
              <Route path="/create" element={<CreateHub />} />
              <Route path="/my-tournaments" element={<MyTournaments />} />
              <Route path="/tournaments/:id/edit" element={<EditTournament />} />
            </Route>
            <Route path="/tournaments" element={<Tournaments />} />
            <Route path="/tournaments/create" element={<CreateTournament />} />
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
            <Route path="games" element={<AdminGames />} />
            <Route path="partners" element={<AdminPartners />} />
            <Route path="rulebooks" element={<AdminRulebooks />} />
            <Route path="settings" element={<AdminSettings />} />
          </Route>
        </Route>
      </Route>
      <Route path="*" element={<PageNotFound />} />
    </Routes>
  );
};

function App() {
  return (
    <AppAuthProvider>
      <QueryClientProvider client={queryClientInstance}>
        <Router>
          <ScrollToTop />
          <AuthenticatedApp />
        </Router>
        <Toaster />
      </QueryClientProvider>
    </AppAuthProvider>
  );
}

export default App;