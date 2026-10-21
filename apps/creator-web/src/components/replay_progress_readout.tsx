import type {PerformanceReplayStatus} from "@lmdj/web-runtime-platform/runtime_types";

export function ReplayProgressReadout({replay, neutral, hold, stopping = false}: {
  readonly replay: PerformanceReplayStatus | null;
  readonly neutral: boolean;
  readonly hold?: boolean;
  readonly stopping?: boolean;
}) {
  const valid = replay !== null && Number.isSafeInteger(replay.eventCursor) &&
    Number.isSafeInteger(replay.eventCount) && replay.eventCursor >= 0 &&
    replay.eventCount >= 0 && replay.eventCursor <= replay.eventCount;
  const reset = replay !== null && replay.state !== "playing" && neutral && !stopping;
  return <section className="perform-replay-status-card" aria-label="Replay event readout"
    data-replay-id={replay?.replayId} data-resolved-revision={replay?.resolvedRevision}
    data-replay-state={replay?.state} data-neutral-confirmed={reset}>
    <h2 className="perform-take-heading">{stopping ? "Stopping Replay…"
      : replay === null ? "No replay selected" : `Replay ${replay.state}`}</h2>
    {replay !== null ? <>
      <div className="perform-replay-events">
        <span>Events</span>
        <output role="status" aria-label="Replay events" aria-live="off"
          data-event-cursor={valid ? replay.eventCursor : undefined}
          data-event-count={valid ? replay.eventCount : undefined}>
          {valid ? `${replay.eventCursor} / ${replay.eventCount} events` : "Event progress unavailable"}
        </output>
      </div>
      {valid && replay.eventCount > 0 ? <progress aria-label="Replay event progress"
        value={replay.eventCursor} max={replay.eventCount}
        aria-valuetext={`${replay.eventCursor} of ${replay.eventCount} events`} /> : null}
      <p>{reset ? `Neutral reset confirmed${hold === undefined ? "" : ` · HOLD ${hold ? "on" : "off"}`}`
        : replay.state === "playing" && !stopping ? "Replay controls active" : "Neutral reset pending"}</p>
    </> : <p>Choose a saved Take to replay.</p>}
  </section>;
}
