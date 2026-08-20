import React from "react";
import logoWhite from "@/assets/logo-white.png";
import logoBlack from "@/assets/logo-black.png";

// The site is dark-theme-only (see --background in index.css), so the white
// mark is the right default everywhere in-app; `variant="black"` exists only
// for placement on a light surface (e.g. printed/exported material).
export default function Logo({ className = "h-9 w-auto", variant = "white" }) {
  return (
    <img
      src={variant === "black" ? logoBlack : logoWhite}
      alt="Esports Pakistan"
      className={`${className} object-contain`}
    />
  );
}
