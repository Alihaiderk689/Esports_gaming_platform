import React, { useEffect, useState } from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { useAuth } from "@/lib/appauth";
import { api } from "@/lib/api";
import { Gamepad2, Menu, X, Search, ChevronDown, LogOut, User as UserIcon, Trophy, LayoutGrid, Plus, ClipboardList, MessageSquare, Settings, ShieldCheck, Building2, Home, Info } from "lucide-react";

const PLAYER_NAV = [
  { label: "Home", to: "/", icon: Home, end: true },
  { label: "Tournaments", to: "/tournaments", icon: Trophy },
  { label: "Games", to: "/games", icon: LayoutGrid },
  { label: "About", to: "/about", icon: Info },
];

// Organizers get only these — no Home, no Players table. A tournament opened from
// My Tournaments carries state.from so it keeps "My Tournaments" highlighted instead
// of "Tournaments", even though both routes land on /tournaments/:id.
const ORGANIZER_NAV = [
  { label: "Create Tournament", to: "/create", icon: Plus },
  { label: "Tournaments", to: "/tournaments", icon: Trophy, activeTest: (path, state) => path.startsWith("/tournaments") && state?.from !== "my-tournaments" },
  { label: "My Tournaments", to: "/my-tournaments", icon: ClipboardList, activeTest: (path, state) => path.startsWith("/my-tournaments") || state?.from === "my-tournaments" },
  { label: "Games", to: "/games", icon: LayoutGrid },
];

export default function Navbar({ onToggleChat }) {
  const { user, logout } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);
  const [userMenu, setUserMenu] = useState(false);
  const [isOrganizer, setIsOrganizer] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    if (!user || user.is_staff) return;
    api
      .get("/api/organizer/status/")
      .then((data) => setIsOrganizer(data.status === "approved"))
      .catch(() => setIsOrganizer(false));
  }, [user]);

  // Admins are restricted to the admin dashboard — no player/organizer-facing nav for them.
  const NAV = user?.is_staff ? [] : isOrganizer ? ORGANIZER_NAV : PLAYER_NAV;

  return (
    <header className="sticky top-0 z-40 glass border-b border-border/60">
      <div className="mx-auto max-w-7xl px-4 sm:px-6">
        <div className="flex h-16 items-center justify-between gap-4">
          {/* Logo */}
          <Link
            to={user?.is_staff ? "/admin" : isOrganizer ? "/dashboard" : "/"}
            className="flex items-center gap-2.5 shrink-0 group"
          >
            <div className="relative">
              <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-primary to-green-500 grid place-items-center neon-border animate-glow">
                <Gamepad2 className="w-5 h-5 text-background" strokeWidth={2.5} />
              </div>
            </div>
            <div className="leading-none">
              <div className="font-display font-extrabold tracking-wider text-sm sm:text-base">
                ESPORTS
              </div>
              <div className="font-display font-bold text-[10px] sm:text-xs gradient-text tracking-[0.3em]">
                PAKISTAN
              </div>
            </div>
          </Link>

          {/* Desktop nav */}
          <nav className="hidden lg:flex items-center gap-1">
            {NAV.map((item) => {
              const active = item.activeTest
                ? item.activeTest(location.pathname, location.state)
                : item.end ? location.pathname === item.to : location.pathname.startsWith(item.to);
              return (
                <Link
                  key={item.to}
                  to={item.to}
                  className={`relative px-4 py-2 rounded-lg text-sm font-heading font-semibold tracking-wide transition-colors ${
                    active ? "text-primary" : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {item.label}
                  {active && (
                    <motion.div layoutId="nav-active" className="absolute inset-0 -z-10 rounded-lg bg-primary/10 neon-border" />
                  )}
                </Link>
              );
            })}
          </nav>

          {/* Right actions */}
          <div className="flex items-center gap-2">
            {!user?.is_staff && (
              <>
                <button className="hidden sm:grid place-items-center w-9 h-9 rounded-lg text-muted-foreground hover:text-primary hover:bg-muted transition-colors">
                  <Search className="w-5 h-5" />
                </button>

                <button
                  onClick={onToggleChat}
                  className="grid place-items-center w-9 h-9 rounded-lg text-muted-foreground hover:text-accent hover:bg-muted transition-colors relative"
                  title="Ask the Esports AI"
                >
                  <MessageSquare className="w-5 h-5" />
                  <span className="absolute top-1 right-1 w-2 h-2 rounded-full bg-accent animate-pulse" />
                </button>
              </>
            )}

            {user ? (
              <div className="relative">
                <button
                  onClick={() => setUserMenu((v) => !v)}
                  className="flex items-center gap-2 pl-1 pr-2 py-1 rounded-lg glass hover:neon-border transition-all"
                >
                  <div className="w-7 h-7 rounded-md bg-gradient-to-br from-primary to-green-500 grid place-items-center text-xs font-bold">
                    {(user.full_name || user.email || "U").charAt(0).toUpperCase()}
                  </div>
                  <ChevronDown className="w-3.5 h-3.5 text-muted-foreground" />
                </button>
                <AnimatePresence>
                  {userMenu && (
                    <motion.div
                      initial={{ opacity: 0, y: 8 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: 8 }}
                      className="absolute right-0 mt-2 w-52 glass rounded-xl p-1.5 shadow-2xl border border-border"
                    >
                      <div className="px-3 py-2 border-b border-border/60 mb-1">
                        <div className="text-sm font-semibold truncate">
                          {[user.first_name, user.last_name].filter(Boolean).join(" ") || user.email}
                        </div>
                        <div className="text-xs text-muted-foreground truncate">{user.email}</div>
                        <span className="inline-block mt-1 text-[10px] font-heading font-bold uppercase tracking-wider text-primary">
                          {user.is_staff ? "Admin" : isOrganizer ? "Organizer" : "Player"}
                        </span>
                      </div>
                      {user.is_staff ? (
                        <>
                          <MenuItem icon={ShieldCheck} label="Admin Dashboard" onClick={() => { setUserMenu(false); navigate("/admin"); }} />
                          <MenuItem icon={Settings} label="Settings" onClick={() => { setUserMenu(false); navigate("/admin/settings"); }} />
                        </>
                      ) : (
                        <>
                          <MenuItem icon={UserIcon} label="My Dashboard" onClick={() => { setUserMenu(false); navigate("/dashboard"); }} />
                          <MenuItem icon={Building2} label="Organizer" onClick={() => { setUserMenu(false); navigate("/organizer"); }} />
                          <MenuItem icon={Settings} label="Account Settings" onClick={() => { setUserMenu(false); navigate("/account"); }} />
                        </>
                      )}
                      <MenuItem icon={LogOut} label="Sign out" onClick={logout} danger />
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            ) : (
              <Link
                to="/login"
                className="hidden sm:inline-flex items-center px-4 py-2 rounded-lg font-heading font-semibold text-sm bg-primary text-primary-foreground hover:shadow-[0_0_24px_hsl(186_100%_50%/0.5)] transition-shadow"
              >
                Sign In
              </Link>
            )}

            <button
              onClick={() => setMenuOpen((v) => !v)}
              className="lg:hidden grid place-items-center w-9 h-9 rounded-lg text-foreground hover:bg-muted"
            >
              {menuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
            </button>
          </div>
        </div>
      </div>

      {/* Mobile menu */}
      <AnimatePresence>
        {menuOpen && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="lg:hidden overflow-hidden border-t border-border/60 glass"
          >
            <div className="px-4 py-3 space-y-1">
              {NAV.map((item) => (
                <Link
                  key={item.to}
                  to={item.to}
                  onClick={() => setMenuOpen(false)}
                  className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-heading font-semibold text-muted-foreground hover:text-primary hover:bg-muted"
                >
                  <item.icon className="w-4 h-4" />
                  {item.label}
                </Link>
              ))}
              {!user && (
                <Link
                  to="/login"
                  onClick={() => setMenuOpen(false)}
                  className="block mt-2 text-center px-4 py-2.5 rounded-lg font-heading font-semibold bg-primary text-primary-foreground"
                >
                  Sign In
                </Link>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </header>
  );
}

function MenuItem({ icon: Icon, label, onClick, danger }) {
  return (
    <button
      onClick={onClick}
      className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
        danger ? "text-destructive hover:bg-destructive/10" : "text-foreground hover:bg-muted"
      }`}
    >
      <Icon className="w-4 h-4" />
      {label}
    </button>
  );
}