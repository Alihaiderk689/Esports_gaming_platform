import React from "react";
import { NavLink, Outlet } from "react-router-dom";
import { LayoutDashboard, Users, Shield, Gamepad2, Handshake, BookOpen, Trophy } from "lucide-react";

const TABS = [
  { label: "Overview", to: "/admin", icon: LayoutDashboard, end: true },
  { label: "Users", to: "/admin/users", icon: Users },
  { label: "Organizers", to: "/admin/organizers", icon: Shield },
  { label: "Tournaments", to: "/admin/tournaments", icon: Trophy },
  { label: "Games", to: "/admin/games", icon: Gamepad2 },
  { label: "Partners", to: "/admin/partners", icon: Handshake },
  { label: "Rulebooks", to: "/admin/rulebooks", icon: BookOpen },
];

export default function AdminLayout() {
  return (
    <div className="mx-auto max-w-7xl px-4 sm:px-6 py-8">
      <h1 className="font-display font-extrabold text-3xl gradient-text mb-6">Admin</h1>

      <nav className="flex flex-wrap gap-1 mb-8 p-1 rounded-xl bg-muted/30 border border-border/60 w-fit">
        {TABS.map((tab) => (
          <NavLink
            key={tab.to}
            to={tab.to}
            end={tab.end}
            className={({ isActive }) =>
              `flex items-center gap-2 px-3.5 py-2 rounded-lg text-sm font-heading font-semibold transition-colors ${
                isActive ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground"
              }`
            }
          >
            <tab.icon className="w-4 h-4" />
            {tab.label}
          </NavLink>
        ))}
      </nav>

      <Outlet />
    </div>
  );
}
