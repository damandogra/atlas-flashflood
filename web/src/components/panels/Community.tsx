import { useState } from "react";
import { REPORT_KINDS, reportsShared, type Report } from "../../lib/reports";

export default function Community({ reports, picked, onStartPick, onSubmit }: {
  reports: Report[];
  picked: [number, number] | null;
  onStartPick: () => void;
  onSubmit: (r: Report) => Promise<void>;
}) {
  const [kind, setKind] = useState<Report["kind"]>("water_level");
  const [severity, setSeverity] = useState<Report["severity"]>(2);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const submit = async () => {
    if (!picked) return;
    setBusy(true);
    try {
      await onSubmit({ lon: picked[0], lat: picked[1], kind, severity, note: note.slice(0, 500) });
      setNote("");
      setMsg("Report saved.");
    } catch (e) {
      setMsg(`Could not save: ${(e as Error).message}`);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="panel-body">
      <h3>Field reports</h3>
      <p className={`small ${reportsShared ? "muted" : "warn"}`}>{reportsShared
        ? "Reports are shared with everyone using this page and appear live."
        : "Demo mode: reports are stored in this browser only. Connect Supabase (see docs/supabase.sql) to share them."}</p>
      <section className="card">
        <b>New report</b>
        <button className="tbtn" onClick={onStartPick}>{picked ? `Location: ${picked[1].toFixed(4)}, ${picked[0].toFixed(4)} — change` : "Click the map to set the location"}</button>
        <label>What <select value={kind} onChange={(e) => setKind(e.target.value as Report["kind"])}>
          {Object.entries(REPORT_KINDS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
        <label>Severity <select value={severity} onChange={(e) => setSeverity(Number(e.target.value) as Report["severity"])}>
          <option value={1}>Minor</option><option value={2}>Serious</option><option value={3}>Severe / life-threatening</option></select></label>
        <label>Note <textarea rows={3} maxLength={500} value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. water over the ford at Tamdaght, 40 cm" /></label>
        <button className="primary" disabled={!picked || busy} onClick={submit}>{busy ? "Saving…" : "Submit report"}</button>
        {msg && <p className="small">{msg}</p>}
      </section>
      <h4>Latest ({reports.length})</h4>
      <ul className="list">
        {reports.slice(0, 50).map((r) => (
          <li key={r.id}><b>{REPORT_KINDS[r.kind]}</b> <span className={`sev s${r.severity}`}>{["", "minor", "serious", "severe"][r.severity]}</span>
            {r.verified && <span className="ok"> verified</span>}
            <span>{r.note}</span><small>{r.created_at ? new Date(r.created_at).toLocaleString() : ""}</small></li>
        ))}
      </ul>
      <p className="muted small">Reports where the model shows no flooding are the most valuable: they point to places the 30 m model misses (narrow gullies, blocked culverts).</p>
    </div>
  );
}
