import { useEffect, useState } from "react";
import { Mountain, Settings, User } from "lucide-react";

export function TopHeader() {
  const [utcTime, setUtcTime] = useState(() => new Date().toUTCString().split(" ")[4]);
  useEffect(() => {
    const interval = setInterval(() => {
      setUtcTime(new Date().toUTCString().split(" ")[4]);
    }, 1000);
    return () => clearInterval(interval);
  }, []);

  return (
    <header className="pointer-events-none absolute inset-x-0 top-0 z-30 p-4 sm:p-5">
      <div className="pointer-events-auto mx-auto flex items-center justify-between gap-3">
        {/* Logo + subtitle */}
        <div className="glass-panel flex items-center gap-3 rounded-xl px-3.5 py-2.5 sm:px-4">
          <div className="relative flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-primary/30 to-primary/5 ring-1 ring-primary/40">
            <Mountain className="h-5 w-5 text-primary" />
            <span className="absolute inset-0 rounded-lg animate-pulse-ring" />
          </div>
          <div className="leading-tight">
            <div className="flex items-center gap-2">
              <h1 className="text-sm font-semibold tracking-tight sm:text-base text-glow">
                Atlas
              </h1>
              <span className="hidden sm:inline-flex items-center rounded-full border border-primary/30 bg-primary/10 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wider text-primary">
                Live
              </span>
            </div>
            <p className="text-[11px] text-muted-foreground sm:text-xs">
              Atlas Mountains Basin · Morocco
            </p>
          </div>
        </div>

        {/* Status + actions */}
        <div className="flex items-center gap-2">
          <div className="hidden md:flex glass-panel items-center gap-2 rounded-xl px-3 py-2 text-xs text-muted-foreground">
            <span className="h-2 w-2 rounded-full bg-success animate-pulse" />
            Sync · {utcTime} UTC
          </div>
          <button
            className="glass-panel flex h-10 w-10 items-center justify-center rounded-xl text-muted-foreground transition-colors hover:text-primary"
            aria-label="Settings"
          >
            <Settings className="h-4.5 w-4.5" />
          </button>
          <button
            className="glass-panel flex h-10 w-10 items-center justify-center rounded-xl text-foreground transition-colors hover:text-primary"
            aria-label="Profile"
          >
            <User className="h-4.5 w-4.5" />
          </button>
        </div>
      </div>
    </header>
  );
}
