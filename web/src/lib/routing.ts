// Evacuation routing on the OSM road/path graph, avoiding segments unsafe at a given time.
import type { RoadFC, ScenarioImpact } from "./data";

type Node = string;
interface Edge { to: Node; seg: number; len: number }

export class RoadGraph {
  adj = new Map<Node, Edge[]>();
  coords = new Map<Node, [number, number]>();

  constructor(roads: RoadFC) {
    roads.features.forEach((f, i) => {
      const c = f.geometry.coordinates;
      const a = key(c[0]), b = key(c[c.length - 1]);
      this.coords.set(a, c[0] as [number, number]);
      this.coords.set(b, c[c.length - 1] as [number, number]);
      const len = f.properties.length_m;
      this.add(a, { to: b, seg: i, len });
      this.add(b, { to: a, seg: i, len });
    });
  }

  private add(n: Node, e: Edge) {
    if (!this.adj.has(n)) this.adj.set(n, []);
    this.adj.get(n)!.push(e);
  }

  nearest(lon: number, lat: number): Node | null {
    let best: Node | null = null, d = Infinity;
    for (const [n, [x, y]] of this.coords) {
      const dd = (x - lon) ** 2 + ((y - lat) * 1.17) ** 2;
      if (dd < d) { d = dd; best = n; }
    }
    return best;
  }

  /** Dijkstra from `from` to the closest of `targets`; segments for which blocked(seg) is true are skipped. */
  route(from: Node, targets: Set<Node>, blocked: (seg: number) => boolean) {
    const dist = new Map<Node, number>([[from, 0]]);
    const prev = new Map<Node, [Node, number]>();
    const done = new Set<Node>();
    const queue: [number, Node][] = [[0, from]];
    while (queue.length) {
      queue.sort((a, b) => a[0] - b[0]);
      const [d, n] = queue.shift()!;
      if (done.has(n)) continue;
      done.add(n);
      if (targets.has(n)) {
        const segs: number[] = [];
        let cur = n;
        while (prev.has(cur)) {
          const [p, s] = prev.get(cur)!;
          segs.push(s);
          cur = p;
        }
        return { target: n, length_m: d, segments: segs.reverse() };
      }
      for (const e of this.adj.get(n) ?? []) {
        if (blocked(e.seg)) continue;
        const nd = d + e.len;
        if (nd < (dist.get(e.to) ?? Infinity)) {
          dist.set(e.to, nd);
          prev.set(e.to, [n, e.seg]);
          queue.push([nd, e.to]);
        }
      }
    }
    return null;
  }
}

const key = (c: number[]) => `${c[0].toFixed(5)},${c[1].toFixed(5)}`;

/** Unsafe for people on foot / in vehicles at time t (null = at any time during the event). */
export function unsafeAt(imp: ScenarioImpact, seg: number, t: number | null) {
  const s = imp.segments;
  if (t === null) return s.status[seg] >= 1;
  return s.car_from[seg] >= 0 && t >= s.car_from[seg] && t < s.car_to[seg];
}
