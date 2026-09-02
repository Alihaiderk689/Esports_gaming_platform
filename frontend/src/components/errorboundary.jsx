import React from "react";
import { AlertTriangle, RotateCw, Home } from "lucide-react";

// Error boundaries must be class components — there's no hook equivalent for
// getDerivedStateFromError/componentDidCatch. Without this, any unexpected
// render-time error anywhere in the tree unmounts the whole app to a blank
// white screen with no feedback at all.
export default class ErrorBoundary extends React.Component {
  state = { hasError: false };

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error, info) {
    console.error("Unhandled render error:", error, info?.componentStack);
  }

  render() {
    if (!this.state.hasError) return this.props.children;

    return (
      <div className="relative min-h-screen flex items-center justify-center p-6 overflow-hidden">
        <div className="absolute inset-0 mesh-bg opacity-40" />
        <div className="absolute inset-0 grid-overlay opacity-20" />

        <div className="relative max-w-md w-full text-center space-y-6">
          <div className="mx-auto w-14 h-14 rounded-2xl bg-destructive/10 border border-destructive/30 grid place-items-center">
            <AlertTriangle className="w-6 h-6 text-destructive" />
          </div>

          <div className="space-y-3">
            <h1 className="font-display font-bold text-2xl">Something went wrong</h1>
            <p className="text-muted-foreground leading-relaxed">
              An unexpected error occurred. Reloading the page usually fixes it.
            </p>
          </div>

          <div className="pt-2 flex items-center justify-center gap-3">
            <button
              onClick={() => window.location.reload()}
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl font-heading font-bold text-sm bg-primary text-primary-foreground hover:shadow-[0_0_28px_hsl(186_100%_50%/0.5)] transition-shadow"
            >
              <RotateCw className="w-4 h-4" /> Reload
            </button>
            <a
              href="/"
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl font-heading font-bold text-sm glass hover:neon-border transition-all"
            >
              <Home className="w-4 h-4 text-primary" /> Go Home
            </a>
          </div>
        </div>
      </div>
    );
  }
}
