import React, { useState } from "react";
import { Outlet } from "react-router-dom";
import Navbar from "./navbar";
import ChatbotPanel from "@/components/chatbot/chatbotpanel";
import { MessageSquare } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

export default function AppLayout() {
  const [chatOpen, setChatOpen] = useState(false);

  return (
    <div className="min-h-screen flex flex-col">
      <div className="fixed inset-0 pointer-events-none border-2 border-primary/45 shadow-[inset_0_0_50px_hsl(72_100%_50%/0.06)] z-[60]" />
      <Navbar onToggleChat={() => setChatOpen((v) => !v)} />
      <main className="flex-1">
        <Outlet />
      </main>

      <ChatbotPanel open={chatOpen} onClose={() => setChatOpen(false)} />

      {/* Floating launcher */}
      <AnimatePresence>
        {!chatOpen && (
          <motion.button
            initial={{ scale: 0, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0, opacity: 0 }}
            onClick={() => setChatOpen(true)}
            className="fixed bottom-5 right-5 z-40 group"
          >
            <span className="absolute inset-0 rounded-full bg-primary/40 blur-xl animate-glow" />
            <span className="relative grid place-items-center w-14 h-14 rounded-full bg-gradient-to-br from-primary to-green-500 text-background neon-border group-hover:scale-110 transition-transform">
              <MessageSquare className="w-6 h-6" strokeWidth={2.2} />
            </span>
            <span className="absolute -top-1 -right-1 w-5 h-5 rounded-full bg-accent text-[10px] font-bold grid place-items-center text-white animate-pulse">
              AI
            </span>
          </motion.button>
        )}
      </AnimatePresence>
    </div>
  );
}