import React, { useState, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { X, Send, Sparkles, Bot } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api } from "@/lib/api";

// The assistant's answers come back as markdown (headings, bold, numbered/
// bulleted lists, and occasionally GFM tables via remarkGfm) — these
// overrides keep that structure but at chat-bubble scale (default
// react-markdown element spacing is sized for full-page prose, not a
// 78%-width bubble).
const markdownComponents = {
  p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
  strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
  ul: ({ children }) => <ul className="mb-2 last:mb-0 pl-4 space-y-1 list-disc">{children}</ul>,
  ol: ({ children }) => <ol className="mb-2 last:mb-0 pl-4 space-y-1 list-decimal">{children}</ol>,
  li: ({ children }) => <li className="leading-relaxed">{children}</li>,
  h1: ({ children }) => <p className="mb-1.5 font-heading font-bold text-[15px]">{children}</p>,
  h2: ({ children }) => <p className="mb-1.5 font-heading font-bold text-[15px]">{children}</p>,
  h3: ({ children }) => <p className="mb-1 font-heading font-semibold">{children}</p>,
  a: ({ children, href }) => (
    <a href={href} target="_blank" rel="noopener noreferrer" className="underline text-primary">
      {children}
    </a>
  ),
  table: ({ children }) => (
    <div className="mb-2 last:mb-0 overflow-x-auto rounded-md border border-border/60">
      <table className="w-full text-xs">{children}</table>
    </div>
  ),
  thead: ({ children }) => <thead className="bg-background/40">{children}</thead>,
  tr: ({ children }) => <tr className="border-b border-border/60 last:border-0">{children}</tr>,
  th: ({ children }) => <th className="px-2 py-1.5 text-left font-heading font-semibold">{children}</th>,
  td: ({ children }) => <td className="px-2 py-1.5 align-top">{children}</td>,
};

// The model sometimes packs multiple points into one table cell using literal
// "<br>" tags (GFM table cells can't contain real newlines) - react-markdown
// intentionally doesn't render raw HTML (rendering it unsanitized would be an
// XSS risk for LLM-sourced text), so left alone it shows up as literal "<br>"
// text. Swap it for a plain-text separator instead of reaching for
// rehype-raw, which would need a sanitizer to stay safe.
function normalizeAssistantMarkdown(content) {
  return content.replace(/<br\s*\/?>/gi, " · ");
}

export default function ChatbotPanel({ open, onClose }) {
  const [messages, setMessages] = useState([
    {
      role: "assistant",
      content: "Salam! 👋 I'm your Esports Pakistan AI assistant. Ask me about tournaments, rules, brackets, or anything esports.",
    },
  ]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const scrollRef = useRef(null);
  const lastMessageRef = useRef(null);

  useEffect(() => {
    const container = scrollRef.current;
    const lastMessage = lastMessageRef.current;
    if (!container) return;
    if (lastMessage && lastMessage.offsetHeight > container.clientHeight) {
      // A reply longer than the visible area would otherwise land the user
      // on its last line — scroll to its start so they read it top-down.
      lastMessage.scrollIntoView({ block: "start" });
    } else {
      container.scrollTop = container.scrollHeight;
    }
  }, [messages, sending]);

  const send = async () => {
    const text = input.trim();
    if (!text || sending) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", content: text }]);
    setSending(true);
    try {
      const res = await api.post("/api/chat/", { message: text });
      const reply = res?.response || res?.answer || res?.message || "Sorry, I couldn't process that.";
      setMessages((m) => [...m, { role: "assistant", content: reply }]);
    } catch (e) {
      const content =
        e.status === 401
          ? "Please sign in to chat with the Esports AI assistant."
          : "I'm having trouble connecting right now. Please try again in a moment.";
      setMessages((m) => [...m, { role: "assistant", content }]);
    } finally {
      setSending(false);
    }
  };

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            className="fixed inset-0 z-50 bg-background/60 backdrop-blur-sm lg:bg-transparent"
          />
          <motion.div
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ type: "spring", damping: 28, stiffness: 280 }}
            className="fixed top-0 right-0 z-50 h-full w-full sm:w-[400px] glass border-l border-border flex flex-col"
          >
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-3.5 border-b border-border/60">
              <div className="flex items-center gap-2.5">
                <div className="relative">
                  <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-primary to-green-500 grid place-items-center">
                    <Bot className="w-5 h-5 text-background" />
                  </div>
                  <span className="absolute -bottom-0.5 -right-0.5 w-3 h-3 rounded-full bg-green-400 border-2 border-card" />
                </div>
                <div>
                  <div className="font-heading font-bold text-sm">Esports AI</div>
                  <div className="text-[11px] text-green-400">Online · RAG-powered</div>
                </div>
              </div>
              <button
                onClick={onClose}
                className="grid place-items-center w-8 h-8 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Messages */}
            <div ref={scrollRef} className="flex-1 overflow-y-auto scrollbar-thin px-4 py-4 space-y-4">
              {messages.map((m, i) => (
                <motion.div
                  key={i}
                  ref={i === messages.length - 1 ? lastMessageRef : null}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  className={`flex gap-2.5 ${m.role === "user" ? "flex-row-reverse" : ""}`}
                >
                  {m.role === "assistant" && (
                    <div className="shrink-0 w-7 h-7 rounded-md bg-gradient-to-br from-primary to-green-500 grid place-items-center">
                      <Sparkles className="w-3.5 h-3.5 text-background" />
                    </div>
                  )}
                  <div
                    className={`max-w-[78%] px-3.5 py-2.5 rounded-2xl text-sm leading-relaxed ${
                      m.role === "user"
                        ? "bg-primary text-primary-foreground rounded-tr-sm"
                        : "bg-muted text-foreground rounded-tl-sm"
                    }`}
                  >
                    {m.role === "assistant" ? (
                      <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
                        {normalizeAssistantMarkdown(m.content)}
                      </ReactMarkdown>
                    ) : (
                      m.content
                    )}
                  </div>
                </motion.div>
              ))}
              {sending && (
                <div className="flex gap-2.5">
                  <div className="shrink-0 w-7 h-7 rounded-md bg-gradient-to-br from-primary to-green-500 grid place-items-center">
                    <Sparkles className="w-3.5 h-3.5 text-background" />
                  </div>
                  <div className="px-4 py-3 rounded-2xl rounded-tl-sm bg-muted flex gap-1">
                    {[0, 1, 2].map((d) => (
                      <span
                        key={d}
                        className="w-1.5 h-1.5 rounded-full bg-muted-foreground animate-bounce"
                        style={{ animationDelay: `${d * 0.15}s` }}
                      />
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Input */}
            <div className="p-3 border-t border-border/60">
              <div className="flex items-end gap-2 glass rounded-xl p-1.5 focus-within:neon-border transition-shadow">
                <textarea
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      send();
                    }
                  }}
                  rows={1}
                  placeholder="Ask anything…"
                  className="flex-1 bg-transparent resize-none outline-none px-2 py-2 text-sm max-h-28 scrollbar-thin"
                />
                <button
                  onClick={send}
                  disabled={!input.trim() || sending}
                  className="shrink-0 grid place-items-center w-9 h-9 rounded-lg bg-primary text-primary-foreground disabled:opacity-40 hover:shadow-[0_0_18px_hsl(186_100%_50%/0.5)] transition-shadow"
                >
                  <Send className="w-4 h-4" />
                </button>
              </div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}