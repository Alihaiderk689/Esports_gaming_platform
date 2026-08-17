/// <reference types="vite/client" />

// Google Identity Services (frontend/index.html loads
// https://accounts.google.com/gsi/client as a global script) — no official
// types package for this, so declared loosely here.
interface Window {
  google?: any;
}
