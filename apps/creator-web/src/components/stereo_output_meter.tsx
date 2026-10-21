import {useEffect, useMemo, useState} from "react";
import type {CreatorRuntimeSession} from "../runtime/runtime_types";
import {formatDbfs, meterPercent, OUTPUT_METER_UNAVAILABLE, projectOutputMeter,
  type OutputMeterChannel, type OutputMeterView} from "../state/output_meter";

export type OutputMeterSource = Pick<CreatorRuntimeSession, "outputMeter">;

function Channel({value, name}: {value: OutputMeterChannel | null; name: "Left" | "Right"}) {
  return <div className="perform-output-meter-rail"
    role={value === null ? undefined : "meter"}
    aria-label={`${name} output level`}
    aria-valuemin={value === null ? undefined : -60}
    aria-valuemax={value === null ? undefined : 0}
    aria-valuenow={value === null ? undefined : Math.max(-60, value.dbfs)}
    aria-valuetext={value === null ? undefined
      : `${formatDbfs(value.dbfs)} dBFS; peak ${formatDbfs(value.heldDbfs)} dBFS`}
    data-peak={value?.peak} data-held-peak={value?.heldPeak}
    data-held-peak-frame={value?.heldPeakFrame}>
    {value === null ? null : <>
      <span className="perform-output-meter-fill" style={{width: `${meterPercent(value.dbfs)}%`}} />
      {value.heldPeak === 0 ? null : <span className="perform-output-meter-hold"
        style={{left: `${meterPercent(value.heldDbfs)}%`}} />}
    </>}
  </div>;
}

export function StereoOutputMeter({source, projectId, running}: {
  source?: OutputMeterSource | null;
  projectId: string | null;
  running: boolean;
}) {
  const eligible = running && projectId !== null && typeof source?.outputMeter === "function";
  // A distinct scope also covers running -> suspended -> running with the same
  // Session. Its first render cannot borrow a previous scope's measurement.
  const scope = useMemo(() => ({source, projectId, eligible}), [source, projectId, eligible]);
  const [snapshot, setSnapshot] = useState<{scope: typeof scope; view: OutputMeterView}>(
    () => ({scope, view: OUTPUT_METER_UNAVAILABLE}));
  useEffect(() => {
    if (!scope.eligible) return;
    let cancelled = false;
    let frame = 0;
    let view = OUTPUT_METER_UNAVAILABLE;
    function read() {
      if (cancelled) return;
      try { view = projectOutputMeter(view, scope.source!.outputMeter!()); }
      catch { view = projectOutputMeter(view, {state: "unavailable", reason: "protocol-error"}); }
      setSnapshot(previous => previous.scope === scope && previous.view === view
        ? previous : {scope, view});
      frame = window.requestAnimationFrame(read);
    }
    read();
    return () => {
      cancelled = true;
      window.cancelAnimationFrame(frame);
    };
  }, [scope]);
  const view = eligible && snapshot.scope === scope ? snapshot.view : OUTPUT_METER_UNAVAILABLE;
  const available = view.state === "available";
  return <div className="perform-output-meter" role="group" aria-label="Stereo output level"
    aria-live="off" data-state={view.state}
    data-owner={available ? view.owner : undefined}
    data-window-end-frame={available ? view.windowEndFrame : undefined}
    data-reason={available ? undefined : view.reason}>
    <div className="perform-output-meter-tracks">
      <Channel name="Left" value={available ? view.left : null} />
      <Channel name="Right" value={available ? view.right : null} />
    </div>
    <output aria-label="Stereo output readout" aria-live="off">
      {available ? `L ${formatDbfs(view.left.dbfs)}  R ${formatDbfs(view.right.dbfs)} dBFS` : "UNAVAILABLE"}
    </output>
  </div>;
}
