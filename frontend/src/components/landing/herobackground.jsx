import React from "react";
import { motion } from "framer-motion";

export default function HeroBackground() {
  return (
    <div className="absolute inset-0 overflow-hidden">
      <div className="absolute inset-0 bg-background" />

      {/* animated mesh blobs */}
      <motion.div
        className="absolute -top-20 -left-10 w-[40rem] h-[40rem] rounded-full blur-3xl"
        style={{ background: "radial-gradient(circle, hsl(72 100% 50% / 0.30), transparent 60%)" }}
        animate={{ x: [0, 60, 0], y: [0, 40, 0], scale: [1, 1.15, 1] }}
        transition={{ duration: 16, repeat: Infinity, ease: "easeInOut" }}
      />
      <motion.div
        className="absolute top-1/3 -right-24 w-[36rem] h-[36rem] rounded-full blur-3xl"
        style={{ background: "radial-gradient(circle, hsl(140 80% 45% / 0.25), transparent 60%)" }}
        animate={{ x: [0, -50, 0], y: [0, 30, 0], scale: [1.1, 1, 1.1] }}
        transition={{ duration: 20, repeat: Infinity, ease: "easeInOut" }}
      />
      <motion.div
        className="absolute -bottom-40 left-1/3 w-[44rem] h-[44rem] rounded-full blur-3xl"
        style={{ background: "radial-gradient(circle, hsl(96 100% 50% / 0.18), transparent 60%)" }}
        animate={{ x: [0, 40, 0], y: [0, -30, 0], scale: [1, 1.2, 1] }}
        transition={{ duration: 24, repeat: Infinity, ease: "easeInOut" }}
      />

      {/* drifting grid + scanline */}
      <div className="absolute inset-0 grid-overlay opacity-30 animate-grid-drift" />
      <div className="absolute inset-0 overflow-hidden">
        <div className="absolute left-0 right-0 h-28 bg-gradient-to-b from-transparent via-primary/10 to-transparent animate-scan" />
      </div>

      {/* cinematic grading */}
      <div className="absolute inset-0 bg-gradient-to-b from-background/40 via-transparent to-background" />
      <div className="absolute inset-0 bg-gradient-to-r from-background/70 via-transparent to-transparent" />
    </div>
  );
}