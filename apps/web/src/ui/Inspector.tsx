import type { PatchBundle } from "../patch/loader";

export function Inspector({ bundle }: { bundle: PatchBundle<unknown> }) {
  const { patch, missingElementIds, warnings } = bundle;
  const meta = (patch.metadata ?? {}) as Record<string, unknown>;
  const unmapped = Array.isArray(meta.unmapped_element_ids)
    ? (meta.unmapped_element_ids as string[])
    : [];

  return (
    <div className="inspector" data-testid="inspector">
      <h3>INSPECTOR</h3>
      <div>patch_id: {patch.patch_id}</div>
      <div>schema: {patch.schema}</div>
      <div>bpm: {patch.bpm} / loop: {patch.loop_seconds}s</div>
      <div>status: {String(meta.status ?? "n/a")} / score: {String(meta.score ?? "n/a")}</div>
      <div>scene: {patch.scenes[0]?.name}</div>
      <h3>ELEMENTS</h3>
      <ul>
        {patch.elements.map((el) => (
          <li
            key={el.element_id}
            className={missingElementIds.has(el.element_id) ? "missing" : ""}
          >
            [{el.lane}] {el.name} ({el.kind}, pitch {el.pitch})
            {missingElementIds.has(el.element_id) ? " — MISSING" : ""}
          </li>
        ))}
      </ul>
      {unmapped.length > 0 && (
        <>
          <h3>UNMAPPED</h3>
          <ul>
            {unmapped.map((id) => (
              <li key={id} className="warn">{id}</li>
            ))}
          </ul>
        </>
      )}
      {warnings.length > 0 && (
        <>
          <h3>WARNINGS</h3>
          <ul>
            {warnings.map((w) => (
              <li key={w} className="warn">{w}</li>
            ))}
          </ul>
        </>
      )}
      {patch.renders.length > 0 && (
        <>
          <h3>RENDERS</h3>
          <ul>
            {patch.renders.map((r) => (
              <li key={r.path}>{r.kind}: {r.path}</li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
