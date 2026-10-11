# Atlas - Frontend Architecture & Implementation Guide

## 1. Project Overview
We are building "Atlas", a ClimateTech Digital Twin for flood and erosion risk assessment in the High Atlas Mountains (Morocco) for an ESA hackathon. The UI must feel like a premium, high-tech ESA/NASA control room.

## 2. Tech Stack
- **Framework:** React (Vite setup)
- **Styling:** Tailwind CSS (Dark mode, Glassmorphism)
- **Icons:** `lucide-react`
- **Map:** `react-map-gl` (Mapbox GL JS wrapper) + `mapbox-gl`

## 3. UI/UX Vibe & Layout
- **Theme:** Deep space/navy backgrounds (`bg-slate-900`), with electric cyan/blue neon accents for active states, and red/orange for risk indicators.
- **Layout:** Full-screen absolute map map as the background. UI elements should be floating glassmorphic panels (`backdrop-blur-md bg-white/10 border border-white/20`) layered on top of the map using `z-index`.

## 4. Core Components to Build

### A. The 3D Map Component (`MapContainer.jsx`)
- Initialize Mapbox using a dark or satellite base style (`mapbox://styles/mapbox/satellite-v9`).
- **CRITICAL - 3D Terrain:** Enable 3D terrain exaggeration. 
  - Add source: `mapbox-dem` pointing to `mapbox://mapbox.mapbox-terrain-dem-v1`.
  - Set `terrain={{ source: 'mapbox-dem', exaggeration: 1.5 }}`.
- **Initial Viewport:** Pitch: 65, Bearing: 20, Zoom: 11, Latitude: 31.30, Longitude: -7.15. (This creates a "helicopter view" of the mountains).
- **Data Overlays (ImageSources):** Prepare raster layers for the GeoTIFF/PNG outputs from our Python backend. BBox bounds: `[[-7.31, 31.6], [-7.01, 31.6], [-7.01, 31.3], [-7.31, 31.3]]`.

### B. Left Sidebar: The Control Center (`Sidebar.jsx`)
Floating panel on the left (width: 380px). Needs a Tab system:
- **Tab 1: Risk Baseline (Historical)**
  - A dropdown to select the Return Period (T10, T50, T100, T500).
  - Toggle switches to display different risk layers: "Flood Depth", "Water Velocity", "Erosion Risk (RUSLE)", and "Water Pollution (Mud)".
- **Tab 2: Mitigation Simulator (What-If)**
  - Section title: "Nature-Based Solutions (NBS)".
  - A button "Reforest Critical Basin" (Simulates planting trees / altering NDVI).
  - A prominent "Run Simulation" button with a loading spinner state.

### C. Right Panel: Ground Truth & Impact (`CitizenScience.jsx`)
Small floating panel on the right.
- Title: "IoT & Citizen Science".
- Display 3 dummy feed items indicating local reports (e.g., "Ultrasonic sensor #4: Water level rising", "Report: Mudflow near Tighza bridge").

### D. Bottom UI Elements
- **Bottom Right:** A dynamic Legend (`Legend.jsx`) showing the color scale for the currently active layer (e.g., 0 to 15 m/s for velocity).

## 5. State Management Expectations
Use React Context or simple App-level state to manage:
- `activeReturnPeriod` (string: 'T10', 'T50', etc.)
- `visibleLayers` (array or object tracking which toggles are ON).
- `simulationLoading` (boolean).

## 6. Execution Instructions for the AI Agent
1. Scaffold the Vite React app and install dependencies (`react-map-gl`, `mapbox-gl`, `lucide-react`, `tailwindcss`).
2. Build the UI shell first (Sidebar, Right Panel) with dummy states to ensure the glassmorphism design looks stunning.
3. Implement the Mapbox component (leave a clear placeholder comment for `REACT_APP_MAPBOX_TOKEN`).
4. Wire the toggle switches in the Sidebar to the visibility property of the Mapbox raster layers.
