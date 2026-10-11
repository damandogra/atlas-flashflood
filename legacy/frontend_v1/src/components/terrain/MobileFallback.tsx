import { History, Sparkles } from "lucide-react";

/** Compact bottom dock surfaced on small screens where floating panels are hidden. */
export function MobileFallback() {
  return (
    <div className="pointer-events-auto absolute inset-x-4 bottom-4 z-20 lg:hidden">
      <div className="glass-panel-strong flex items-center justify-between gap-2 rounded-2xl p-2">
        <button className="flex flex-1 items-center justify-center gap-1.5 rounded-xl bg-primary/15 px-3 py-2.5 text-xs font-semibold text-primary ring-1 ring-primary/40">
          <History className="h-3.5 w-3.5" />
          Historical
        </button>
        <button className="flex flex-1 items-center justify-center gap-1.5 rounded-xl px-3 py-2.5 text-xs font-medium text-muted-foreground">
          <Sparkles className="h-3.5 w-3.5" />
          Simulator
        </button>
        <button className="flex flex-1 items-center justify-center gap-1.5 rounded-xl px-3 py-2.5 text-xs font-medium text-muted-foreground">
          Reports
        </button>
      </div>
    </div>
  );
}
