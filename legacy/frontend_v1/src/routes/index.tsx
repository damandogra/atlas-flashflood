import { useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { TerrainMap } from "@/components/terrain/TerrainMap";
import { TopHeader } from "@/components/terrain/TopHeader";
import { LeftSidebar } from "@/components/terrain/LeftSidebar";
import { RightPanel } from "@/components/terrain/RightPanel";
import { MapLegend } from "@/components/terrain/MapLegend";
import { MobileFallback } from "@/components/terrain/MobileFallback";
import { AlertBanner } from "@/components/terrain/AlertBanner";
import { LayerStateProvider } from "@/components/terrain/useLayerState";

export const Route = createFileRoute("/")({
  component: TerrainTwin,
  head: () => ({
    meta: [
      { title: "Atlas Mountains Digital Twin" },
      {
        name: "description",
        content:
          "Digital twin for flood and erosion risk assessment in mountainous regions. Simulate rainfall, plan nature-based interventions, and visualize community reports.",
      },
      { property: "og:title", content: "Atlas Mountains Digital Twin" },
      {
        property: "og:description",
        content: "ClimateTech digital twin for flood and erosion risk in the Atlas Mountains.",
      },
    ],
  }),
});

function TerrainTwin() {
  const [mouseCoords, setMouseCoords] = useState<{ lat: number; lng: number } | null>(null);

  return (
    <LayerStateProvider>
      <main className="relative h-screen w-full overflow-hidden bg-background text-foreground">
        <TerrainMap onCoordsChange={(lat, lng) => setMouseCoords({ lat, lng })} />

        <AlertBanner />

        {/* Subtle top radial glow */}
        <div
          className="pointer-events-none absolute inset-0 z-10"
          style={{ background: "var(--gradient-radial-glow)" }}
        />

        <TopHeader />
        <LeftSidebar />
        <RightPanel />
        <MapLegend coordinates={mouseCoords} />
        <MobileFallback />
      </main>
    </LayerStateProvider>
  );
}
