// Layout is in local CSS pixels. Data coordinates and valid EQ values never
// move to make room for controls; the caller draws leaders to displaced dots.
export interface EqHandlePoint {readonly x: number; readonly y: number}
export type EqHandlePoints = readonly [EqHandlePoint, EqHandlePoint, EqHandlePoint];

const MARGIN = 22.125; // Contains the outward-rounded 44px hit ellipse.
const PITCH = 46;
export const EQ_PLOT_MIN_WIDTH = 45;

export function minimumEqPlotHeight(width: number): number {
  const columns = Math.max(1, Math.min(3, 1 + Math.floor((width - 2 * MARGIN) / PITCH)));
  return 2 * MARGIN + (Math.ceil(3 / columns) - 1) * PITCH;
}

const distance = (a: EqHandlePoint, b: EqHandlePoint) => (a.x - b.x) ** 2 + (a.y - b.y) ** 2;
const separate = (a: EqHandlePoint, b: EqHandlePoint) =>
  Math.abs(a.x - b.x) >= PITCH - 1e-7 || Math.abs(a.y - b.y) >= PITCH - 1e-7;

export function layoutEqHandles(
  preferred: EqHandlePoints, width: number, height: number, activeIndex?: number,
): EqHandlePoints {
  const clampX = (x: number) => Math.max(MARGIN, Math.min(width - MARGIN, x));
  const clampY = (y: number) => Math.max(MARGIN, Math.min(height - MARGIN, y));
  const bounded = (p: EqHandlePoint) => ({x: clampX(p.x), y: clampY(p.y)});
  const desired: EqHandlePoints = [bounded(preferred[0]), bounded(preferred[1]), bounded(preferred[2])];
  if (separate(desired[0]!, desired[1]!) && separate(desired[0]!, desired[2]!) &&
      separate(desired[1]!, desired[2]!)) return desired;

  // A nearest legal position lies at its preferred coordinate, a canvas edge,
  // or one footprint away from a fixed neighbour. Only three handles exist.
  const candidates = (point: EqHandlePoint, fixed: readonly EqHandlePoint[]) => {
    const xs = new Set([clampX(point.x), MARGIN, width - MARGIN,
      ...fixed.flatMap(p => [clampX(p.x - PITCH), clampX(p.x + PITCH)])]);
    const ys = new Set([clampY(point.y), MARGIN, height - MARGIN,
      ...fixed.flatMap(p => [clampY(p.y - PITCH), clampY(p.y + PITCH)])]);
    return [...xs].flatMap(x => [...ys].map(y => ({x, y})))
      .filter(p => fixed.every(other => separate(p, other)))
      .sort((a, b) => distance(a, point) - distance(b, point) || a.x - b.x || a.y - b.y);
  };
  const firsts = activeIndex === undefined ? [0, 1, 2] : [activeIndex];
  const orders = firsts.flatMap(first => {
    const rest = [0, 1, 2].filter(i => i !== first);
    return [[first, rest[0]!, rest[1]!] as const, [first, rest[1]!, rest[0]!] as const];
  });
  let best: EqHandlePoints | null = null, bestCost = Infinity;
  const search = (order: readonly [number, number, number], first: EqHandlePoint) => {
    const [a, b, c] = order;
    const firstCost = distance(first, desired[a]!);
    for (const second of candidates(desired[b]!, [first])) {
      const cost = firstCost + distance(second, desired[b]!);
      if (cost >= bestCost) continue;
      for (const third of candidates(desired[c]!, [first, second])) {
        const total = cost + distance(third, desired[c]!);
        if (total >= bestCost) continue;
        const placed: [EqHandlePoint, EqHandlePoint, EqHandlePoint] = [...desired];
        placed[a] = first; placed[b] = second; placed[c] = third;
        best = placed; bestCost = total;
        break; // Third candidates are ordered by displacement.
      }
    }
  };
  // Keep one normal marker, or the grabbed marker, at its preferred point
  // whenever feasible. Other markers yield without changing their data.
  for (const order of orders) search(order, desired[order[0]!]!);
  if (best !== null) return best;
  // Very narrow canvases can require moving even the first marker. Their
  // minimum height supplies three cells; edge candidates keep that feasible.
  for (const order of orders) for (const x of [MARGIN, width - MARGIN]) {
    for (const y of [MARGIN, height - MARGIN]) search(order, {x, y});
  }
  if (best === null) throw new RangeError("EQ plot cannot contain three 44px targets");
  return best;
}
