// Community field reports: Supabase when configured (VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY),
// otherwise a local demo store in this browser only. Schema: docs/supabase.sql.
import { createClient, type SupabaseClient } from "@supabase/supabase-js";

export interface Report {
  id?: string;
  created_at?: string;
  lon: number;
  lat: number;
  kind: "water_level" | "road_blocked" | "damage" | "people_trapped" | "other";
  severity: 1 | 2 | 3;
  note: string;
  verified?: boolean;
}

export const REPORT_KINDS: Record<Report["kind"], string> = {
  water_level: "Water rising / flooding",
  road_blocked: "Road or ford blocked",
  damage: "Building damaged",
  people_trapped: "People need help",
  other: "Other",
};

const url = import.meta.env.VITE_SUPABASE_URL as string | undefined;
const key = import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined;
const client: SupabaseClient | null = url && key ? createClient(url, key) : null;
export const reportsShared = client !== null;
const LOCAL = "atlas-reports";

function local(): Report[] {
  try {
    return JSON.parse(localStorage.getItem(LOCAL) ?? "[]");
  } catch {
    return [];
  }
}

export async function listReports(): Promise<Report[]> {
  if (!client) return local();
  const { data, error } = await client.from("reports").select("*").order("created_at", { ascending: false }).limit(500);
  if (error) throw error;
  return data as Report[];
}

export async function addReport(r: Report): Promise<void> {
  if (!client) {
    const all = [{ ...r, id: crypto.randomUUID(), created_at: new Date().toISOString() }, ...local()];
    try {
      localStorage.setItem(LOCAL, JSON.stringify(all));
    } catch {
      /* storage unavailable: report is kept for this page view only */
    }
    return;
  }
  const { error } = await client.from("reports").insert(r);
  if (error) throw error;
}

export function subscribe(onChange: () => void): () => void {
  if (!client) return () => {};
  const ch = client.channel("reports").on("postgres_changes", { event: "*", schema: "public", table: "reports" }, onChange).subscribe();
  return () => {
    client.removeChannel(ch);
  };
}
