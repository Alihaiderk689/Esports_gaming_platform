import React, { useState } from "react";
import { Outlet } from "react-router-dom";
import Navbar from "./navbar";
import ChatbotPanel from "@/components/chatbot/chatbotpanel";

export default function AppLayout() {
  const [chatOpen, setChatOpen] = useState(false);

  return (
    <div className="min-h-screen flex flex-col">
      <div className="fixed inset-0 pointer-events-none border-2 border-primary/45 shadow-[inset_0_0_50px_hsl(72_100%_50%/0.06)] z-[60]" />
      <Navbar onToggleChat={() => setChatOpen((v) => !v)} />
      <main className="flex-1">
        <Outlet />
      </main>

      {/* Navbar's chat icon is the only entry point now — a second floating
          launcher button for the same panel was redundant and has been removed. */}
      <ChatbotPanel open={chatOpen} onClose={() => setChatOpen(false)} />
    </div>
  );
}