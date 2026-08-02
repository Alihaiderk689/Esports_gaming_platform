import { Link, useLocation } from 'react-router-dom';
import { Home, Gamepad2 } from 'lucide-react';

export default function PageNotFound() {
    const location = useLocation();
    const pageName = location.pathname.substring(1);

    return (
        <div className="relative min-h-screen flex items-center justify-center p-6 overflow-hidden">
            <div className="absolute inset-0 mesh-bg opacity-40" />
            <div className="absolute inset-0 grid-overlay opacity-20" />

            <div className="relative max-w-md w-full text-center space-y-6">
                <div className="space-y-2">
                    <h1 className="font-display font-extrabold text-7xl gradient-text animate-gradient">404</h1>
                    <div className="h-0.5 w-16 bg-border mx-auto" />
                </div>

                <div className="space-y-3">
                    <h2 className="font-display font-bold text-2xl">Page Not Found</h2>
                    <p className="text-muted-foreground leading-relaxed">
                        The page <span className="font-medium text-foreground">&quot;{pageName}&quot;</span> could not be found in this application.
                    </p>
                </div>

                <div className="pt-4 flex items-center justify-center gap-3">
                    <Link
                        to="/"
                        className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl font-heading font-bold text-sm bg-primary text-primary-foreground hover:shadow-[0_0_28px_hsl(186_100%_50%/0.5)] transition-shadow"
                    >
                        <Home className="w-4 h-4" /> Go Home
                    </Link>
                    <Link
                        to="/tournaments"
                        className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl font-heading font-bold text-sm glass hover:neon-border transition-all"
                    >
                        <Gamepad2 className="w-4 h-4 text-primary" /> Browse Tournaments
                    </Link>
                </div>
            </div>
        </div>
    );
}
