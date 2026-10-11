import { useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  Ban,
  Building,
  CircleHelp,
  MapPin,
  MessageSquarePlus,
  Plus,
  Waves,
  Wrench,
  X,
  Loader2,
  CheckCircle2,
  Crosshair,
  Send,
} from "lucide-react";
import {
  getCitizenObservations,
  submitObservation,
  type CitizenFeature,
  type EventType,
  type Severity,
} from "@/api/client";
import { useLayerState } from "./useLayerState";

// ─── Event type → icon mapping ────────────────────────────────────────────

const EVENT_ICONS: Record<EventType, React.ReactNode> = {
  flooding: <Waves className="h-3.5 w-3.5" />,
  road_blocked: <Ban className="h-3.5 w-3.5" />,
  structure_damage: <Building className="h-3.5 w-3.5" />,
  evacuation_needed: <AlertTriangle className="h-3.5 w-3.5" />,
  infrastructure_damage: <Wrench className="h-3.5 w-3.5" />,
  other: <CircleHelp className="h-3.5 w-3.5" />,
};

const EVENT_LABELS: Record<EventType, string> = {
  flooding: "Flooding",
  road_blocked: "Road Blocked",
  structure_damage: "Structure Damage",
  evacuation_needed: "Evacuation",
  infrastructure_damage: "Infrastructure",
  other: "Other",
};

const EVENT_BADGE_COLORS: Record<EventType, string> = {
  flooding: "border-destructive/40 bg-destructive/10 text-destructive",
  road_blocked: "border-warning/40 bg-warning/10 text-warning",
  structure_damage: "border-primary/40 bg-primary/10 text-primary",
  evacuation_needed: "border-destructive/50 bg-destructive/20 text-destructive",
  infrastructure_damage: "border-orange-400/40 bg-orange-400/10 text-orange-400",
  other: "border-glass-border bg-secondary/40 text-muted-foreground",
};

// ─── Severity helpers ──────────────────────────────────────────────────────

const SEVERITY_COLORS: Record<Severity, string> = {
  1: "bg-warning",
  2: "bg-orange-500",
  3: "bg-destructive",
};

const SEVERITY_LABELS: Record<Severity, string> = {
  1: "Minor",
  2: "Moderate",
  3: "Severe",
};

// ─── Component ─────────────────────────────────────────────────────────────

export function RightPanel() {
  const {
    observations,
    setObservations,
    selectionMode,
    setSelectionMode,
    pendingLocation,
    setPendingLocation,
    highlightedId,
    setHighlightedId,
    fused,
  } = useLayerState();

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitSuccess, setSubmitSuccess] = useState(false);

  // ── Form state ──────────────────────────────────────────────────────────
  const [formEventType, setFormEventType] = useState<EventType>("flooding");
  const [formSeverity, setFormSeverity] = useState<Severity>(2);
  const [formDescription, setFormDescription] = useState("");
  const [formReporter, setFormReporter] = useState("");
  const [formError, setFormError] = useState<string | null>(null);

  const cardRefs = useRef<Map<number, HTMLElement>>(new Map());

  // ── Fetch observations ──────────────────────────────────────────────────
  const fetchObservations = async () => {
    try {
      const data = await getCitizenObservations();
      setObservations(data.features as CitizenFeature[]);
      setError(null);
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Failed to load community reports",
      );
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchObservations();
    const interval = setInterval(fetchObservations, 5_000);
    return () => clearInterval(interval);
  }, []);

  // ── Scroll to highlighted card ──────────────────────────────────────────
  useEffect(() => {
    if (highlightedId !== null) {
      const el = cardRefs.current.get(highlightedId);
      el?.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [highlightedId]);

  // ── Enter selection mode ────────────────────────────────────────────────
  const handleStartReport = () => {
    setSelectionMode(true);
    setShowForm(false);
    setPendingLocation(null);
    setSubmitSuccess(false);
  };

  // ── Cancel selection mode ──────────────────────────────────────────────
  const handleCancelSelection = () => {
    setSelectionMode(false);
    setPendingLocation(null);
  };

  // ── Proceed to form (when pendingLocation is set by map click) ──────────
  useEffect(() => {
    if (pendingLocation) {
      setShowForm(true);
    }
  }, [pendingLocation]);

  // ── Submit form ─────────────────────────────────────────────────────────
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!pendingLocation) {
      setFormError("Please click on the map to set a location first.");
      return;
    }

    setFormError(null);
    setSubmitting(true);

    try {
      await submitObservation({
        lat: pendingLocation.lat,
        lon: pendingLocation.lon,
        event_type: formEventType,
        severity: formSeverity,
        description: formDescription || "",
        reporter: formReporter || "anonymous",
      });

      setSubmitSuccess(true);
      setSubmitting(false);
      setFormEventType("flooding");
      setFormSeverity(2);
      setFormDescription("");
      setFormReporter("");
      setSelectionMode(false);
      setPendingLocation(null);
      setShowForm(false);

      // Refresh
      await fetchObservations();

      // Show success briefly
      setTimeout(() => setSubmitSuccess(false), 3000);
    } catch (err) {
      setFormError(
        err instanceof Error ? err.message : "Failed to submit report",
      );
      setSubmitting(false);
    }
  };

  const handleCancelForm = () => {
    setShowForm(false);
    setSelectionMode(false);
    setPendingLocation(null);
    setFormError(null);
  };

  // ── Render ──────────────────────────────────────────────────────────────
  return (
    <>
      <aside className="pointer-events-auto absolute right-4 top-24 z-20 hidden w-[320px] max-w-[calc(100vw-2rem)] xl:block">
        <div className="glass-panel-strong flex max-h-[calc(100vh-12rem)] flex-col overflow-hidden rounded-2xl">
          {/* Header */}
          <div className="flex items-center justify-between border-b border-glass-border bg-background/30 px-4 py-3">
            <div className="flex items-center gap-2">
              <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary/15 ring-1 ring-primary/30">
                <MessageSquarePlus className="h-3.5 w-3.5 text-primary" />
              </div>
              <div>
                <h2 className="text-sm font-semibold text-foreground">
                  Community Reports
                </h2>
                <p className="text-[10px] text-muted-foreground">
                  {loading
                    ? "Loading…"
                    : `Live feed · ${observations.length} report${observations.length !== 1 ? "s" : ""}`}
                </p>
              </div>
            </div>
            <span className="flex h-2 w-2 rounded-full bg-success animate-pulse" />
          </div>

          {/* Selection mode hint */}
          {selectionMode && !showForm && (
            <div className="flex items-center gap-2 border-b border-primary/30 bg-primary/10 px-4 py-2.5">
              <Crosshair className="h-3.5 w-3.5 shrink-0 text-primary animate-pulse" />
              <span className="text-[11px] font-medium text-primary flex-1">
                Click on the map to mark the incident location
              </span>
              <button
                onClick={handleCancelSelection}
                className="flex h-5 w-5 items-center justify-center rounded-md text-muted-foreground hover:text-foreground"
                aria-label="Cancel report placement"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          )}

          {/* Reports list */}
          <div className="scrollbar-thin flex-1 space-y-2 overflow-y-auto p-3">
            {!fused ? (
              <div className="px-3 py-8 text-center text-[11px] text-muted-foreground">
                Citizen Intelligence is disabled. Toggle "Citizen Intel" on in the Risk
                Analytics panel to view community reports.
              </div>
            ) : loading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-5 w-5 animate-spin text-primary" />
              </div>
            ) : error ? (
              <div className="rounded-xl border border-destructive/30 bg-destructive/10 px-3 py-4 text-center text-[11px] text-destructive">
                {error}
              </div>
            ) : observations.length === 0 ? (
              <div className="px-3 py-6 text-center text-[11px] text-muted-foreground">
                No community reports yet. Be the first to report an incident.
              </div>
            ) : (
              observations.map((obs) => (
                <IncidentCard
                  key={obs.properties.id}
                  feature={obs}
                  isHighlighted={highlightedId === obs.properties.id}
                  onMouseEnter={() => setHighlightedId(obs.properties.id)}
                  onMouseLeave={() => setHighlightedId(null)}
                  ref={(el) => {
                    if (el) cardRefs.current.set(obs.properties.id, el);
                    else cardRefs.current.delete(obs.properties.id);
                  }}
                />
              ))
            )}
          </div>

          {/* Footer button */}
          <div className="border-t border-glass-border bg-background/30 p-3">
            <button
              onClick={handleStartReport}
              disabled={selectionMode}
              className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-primary/40 bg-primary/10 px-3 py-2.5 text-xs font-semibold text-primary transition-all hover:bg-primary/20 hover:ring-1 hover:ring-primary/40 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {selectionMode ? (
                <>
                  <Crosshair className="h-3.5 w-3.5 animate-pulse" />
                  Placing on map…
                </>
              ) : (
                <>
                  <Plus className="h-3.5 w-3.5" />
                  Report Incident
                </>
              )}
            </button>
          </div>
        </div>
      </aside>

      {/* ── Submit Form Modal ──────────────────────────────────────────── */}
      {showForm && pendingLocation && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
          <div className="mx-4 w-full max-w-md rounded-2xl border border-glass-border shadow-elegant"
            style={{
              background: "oklch(0.18 0.035 250 / 0.95)",
              backdropFilter: "blur(28px) saturate(180%)",
              WebkitBackdropFilter: "blur(28px) saturate(180%)",
            }}
          >
            {/* Modal header */}
            <div className="flex items-center justify-between border-b border-glass-border px-5 py-3.5">
              <div className="flex items-center gap-2">
                <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary/15 ring-1 ring-primary/30">
                  <Plus className="h-3.5 w-3.5 text-primary" />
                </div>
                <h2 className="text-sm font-semibold text-foreground">
                  Report Incident
                </h2>
              </div>
              <button
                onClick={handleCancelForm}
                className="flex h-7 w-7 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-secondary/60 hover:text-foreground"
                aria-label="Close form"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {/* Location indicator */}
            <div className="mx-5 mt-4 flex items-center gap-2 rounded-lg border border-primary/30 bg-primary/10 px-3 py-2">
              <MapPin className="h-3.5 w-3.5 shrink-0 text-primary" />
              <span className="text-[11px] font-medium text-primary">
                Location: {pendingLocation.lat.toFixed(4)}, {pendingLocation.lon.toFixed(4)}
              </span>
            </div>

            {/* Form */}
            <form onSubmit={handleSubmit} className="space-y-4 p-5 pt-4">
              {/* Event type */}
              <div>
                <label className="mb-1.5 block text-[11px] font-medium text-muted-foreground">
                  Event Type
                </label>
                <div className="grid grid-cols-2 gap-1.5">
                  {(["flooding", "road_blocked", "structure_damage", "evacuation_needed", "infrastructure_damage", "other"] as EventType[]).map((type) => (
                    <button
                      key={type}
                      type="button"
                      onClick={() => setFormEventType(type)}
                      className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-2 text-[11px] font-medium transition-all ${
                        formEventType === type
                          ? "border-primary/50 bg-primary/15 text-primary ring-1 ring-primary/30"
                          : "border-glass-border bg-secondary/30 text-muted-foreground hover:border-primary/30 hover:text-foreground"
                      }`}
                    >
                      {EVENT_ICONS[type]}
                      <span className="truncate">{EVENT_LABELS[type]}</span>
                    </button>
                  ))}
                </div>
              </div>

              {/* Severity */}
              <div>
                <label className="mb-1.5 block text-[11px] font-medium text-muted-foreground">
                  Severity
                </label>
                <div className="flex gap-2">
                  {([1, 2, 3] as Severity[]).map((sev) => (
                    <button
                      key={sev}
                      type="button"
                      onClick={() => setFormSeverity(sev)}
                      className={`flex flex-1 items-center justify-center gap-1.5 rounded-lg border px-3 py-2.5 text-[11px] font-medium transition-all ${
                        formSeverity === sev
                          ? "border-white/30 bg-white/10 text-foreground ring-1 ring-white/20"
                          : "border-glass-border bg-secondary/30 text-muted-foreground hover:border-white/20"
                      }`}
                    >
                      <span className={`h-2 w-2 rounded-full ${SEVERITY_COLORS[sev]}`} />
                      {SEVERITY_LABELS[sev]}
                    </button>
                  ))}
                </div>
              </div>

              {/* Description */}
              <div>
                <label className="mb-1.5 block text-[11px] font-medium text-muted-foreground">
                  Description
                </label>
                <textarea
                  value={formDescription}
                  onChange={(e) => setFormDescription(e.target.value)}
                  placeholder="Describe what you observed…"
                  rows={3}
                  className="w-full resize-none rounded-lg border border-glass-border bg-secondary/40 px-3 py-2 text-xs text-foreground placeholder:text-muted-foreground/50 outline-none transition-all focus:border-primary/50 focus:ring-1 focus:ring-primary/30"
                />
              </div>

              {/* Reporter */}
              <div>
                <label className="mb-1.5 block text-[11px] font-medium text-muted-foreground">
                  Your Name
                </label>
                <input
                  value={formReporter}
                  onChange={(e) => setFormReporter(e.target.value)}
                  placeholder="e.g. Yassine A."
                  className="w-full rounded-lg border border-glass-border bg-secondary/40 px-3 py-2.5 text-xs text-foreground placeholder:text-muted-foreground/50 outline-none transition-all focus:border-primary/50 focus:ring-1 focus:ring-primary/30"
                />
              </div>

              {/* Error */}
              {formError && (
                <div className="flex items-center gap-1.5 rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-[11px] text-destructive">
                  <AlertTriangle className="h-3 w-3 shrink-0" />
                  {formError}
                </div>
              )}

              {/* Submit */}
              <button
                type="submit"
                disabled={submitting}
                className="flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-primary to-primary-glow px-4 py-3 text-sm font-semibold text-primary-foreground shadow-[0_8px_24px_-8px_oklch(0.78_0.16_210/0.6)] transition-all hover:shadow-[0_12px_30px_-8px_oklch(0.78_0.16_210/0.8)] disabled:cursor-not-allowed disabled:opacity-80"
              >
                {submitting ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Submitting…
                  </>
                ) : (
                  <>
                    <Send className="h-4 w-4" />
                    Submit Report
                  </>
                )}
              </button>
            </form>
          </div>
        </div>
      )}

      {/* ── Success toast ──────────────────────────────────────────────── */}
      {submitSuccess && (
        <div className="fixed bottom-6 left-1/2 z-50 -translate-x-1/2">
          <div className="flex items-center gap-2 rounded-xl border border-success/30 bg-success/15 px-4 py-2.5 text-xs font-medium text-success backdrop-blur-md">
            <CheckCircle2 className="h-3.5 w-3.5 shrink-0" />
            Report submitted successfully
          </div>
        </div>
      )}
    </>
  );
}

// ─── Incident Card ─────────────────────────────────────────────────────────

const IncidentCard = ({
  feature,
  isHighlighted,
  onMouseEnter,
  onMouseLeave,
}: {
  feature: CitizenFeature;
  isHighlighted: boolean;
  onMouseEnter: () => void;
  onMouseLeave: () => void;
  ref: (el: HTMLElement | null) => void;
}) => {
  const { properties } = feature;
  const eventType = properties.event_type as EventType;
  const severity = properties.severity as Severity;
  const description = (properties.description as string) ?? "";
  const reporter = (properties.reporter as string) ?? "Anonymous";
  const createdAt = properties.created_at as string | undefined;

  const timeAgo = createdAt ? formatTimeAgo(createdAt) : null;

  return (
    <article
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
      className={`group cursor-pointer rounded-xl border p-3 transition-all ${
        isHighlighted
          ? "border-primary/60 bg-primary/15 ring-1 ring-primary/40"
          : "border-glass-border bg-secondary/30 hover:border-primary/40 hover:bg-secondary/60"
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <div
            className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[10px] font-bold ring-1 ${
              isHighlighted
                ? "bg-primary/30 text-primary ring-primary/50"
                : "bg-gradient-to-br from-primary/40 to-primary/10 text-primary-foreground ring-primary/30"
            }`}
          >
            {reporter.charAt(0).toUpperCase()}
          </div>
          <div className="min-w-0">
            <div className="truncate text-xs font-medium text-foreground">
              {reporter}
            </div>
            <div className="flex items-center gap-1 text-[10px] text-muted-foreground">
              <MapPin className="h-2.5 w-2.5" />
              <span className="truncate">
                {feature.geometry.coordinates[1].toFixed(4)}, {feature.geometry.coordinates[0].toFixed(4)}
              </span>
            </div>
          </div>
        </div>
        <span
          className={`flex shrink-0 items-center gap-1 rounded-full border px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider ${EVENT_BADGE_COLORS[eventType] ?? "border-glass-border bg-secondary/40 text-muted-foreground"}`}
        >
          {EVENT_ICONS[eventType]}
          {EVENT_LABELS[eventType] ?? eventType}
        </span>
      </div>

      {description && (
        <p className="mt-2 line-clamp-2 text-[11px] leading-relaxed text-muted-foreground group-hover:text-foreground/80">
          {description}
        </p>
      )}

      <div className="mt-2 flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          {([1, 2, 3] as Severity[]).map((s) => (
            <span
              key={s}
              className={`inline-block h-1.5 w-1.5 rounded-full ${
                s <= severity ? SEVERITY_COLORS[s] : "bg-secondary/60"
              }`}
            />
          ))}
          <span className="ml-1 text-[10px] text-muted-foreground">
            {SEVERITY_LABELS[severity]}
          </span>
        </div>
        {timeAgo && (
          <span className="text-[10px] text-muted-foreground">{timeAgo}</span>
        )}
      </div>
    </article>
  );
};

// ─── Helpers ───────────────────────────────────────────────────────────────

function formatTimeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return "Just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}
