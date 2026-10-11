import { useEffect, useState } from "react";
import { getAlert, type AlertData } from "@/api/client";
import { AlertTriangle, X } from "lucide-react";

type BannerState =
  | { status: "loading" }
  | { status: "hidden" }
  | { status: "visible"; level: "orange" | "red"; data: AlertData };

export function AlertBanner() {
  const [banner, setBanner] = useState<BannerState>({ status: "loading" });
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function fetchAlert() {
      try {
        const data = await getAlert();
        if (cancelled) return;

        if (data.level === "orange" || data.level === "red") {
          setBanner({ status: "visible", level: data.level, data });
        } else {
          setBanner({ status: "hidden" });
        }
      } catch {
        if (!cancelled) setBanner({ status: "hidden" });
      }
    }

    fetchAlert();

    // Re-fetch every 5 minutes in case the alert level changes
    const interval = setInterval(fetchAlert, 300_000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  if (banner.status !== "visible" || dismissed) return null;

  const isRed = banner.level === "red";

  return (
    <div
      className={`fixed inset-x-0 top-0 z-50 border-b ${
        isRed
          ? "border-red-500/40 bg-red-600/90 text-white"
          : "border-orange-500/40 bg-orange-500/90 text-white"
      } ${isRed ? "animate-pulse" : ""}`}
    >
      <div className="mx-auto flex items-center justify-between px-4 py-2.5 sm:px-6">
        <div className="flex items-center gap-3">
          <AlertTriangle
            className={`h-5 w-5 shrink-0 ${isRed ? "animate-bounce" : ""}`}
          />
          <div className="text-sm font-medium leading-tight">
            <span className="font-bold uppercase tracking-wider">
              {isRed ? "Extreme Warning" : "Early Warning"}
            </span>
            <span className="mx-2 opacity-70">·</span>
            <span>
              Extreme storm forecast in the next 24 hours.{" "}
              <span className="hidden sm:inline">
                Evaluating critical risk.
              </span>
            </span>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {banner.data.rainfall_24h > 0 && (
            <span className="hidden text-xs font-semibold tabular-nums sm:block">
              {banner.data.rainfall_24h} mm / 24h
            </span>
          )}
          <button
            onClick={() => setDismissed(true)}
            className="flex h-7 w-7 items-center justify-center rounded-md bg-white/10 transition-colors hover:bg-white/20"
            aria-label="Dismiss alert"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
