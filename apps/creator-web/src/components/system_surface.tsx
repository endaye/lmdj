import {useEffect, useRef, useState, type ReactNode} from "react";
import type {CreatorCandidateRuntimeSession, CandidateProviderList} from "../runtime/runtime_types";
import {changeProviderPermission, subscribeProviderPermissions} from "../state/provider_permissions";
import type {CreatorState} from "../state/creator_state";
import type {PadCaptureSource} from "../capture/pad_capture";
import {midiLabel, type MidiStatus} from "./midi_status";
import {TouchSegment} from "./touch_kit";
import "./system_surface.css";

export function SystemStatus({audio, midi}: {
  audio: CreatorState["audio"]["phase"];
  midi: MidiStatus | null;
}) {
  return <dl className="system-status" aria-label="Device status">
    <div><dt>Audio</dt><dd><output aria-label="System audio status">{audio}</output></dd></div>
    <div><dt>MIDI</dt><dd><output aria-label="System MIDI status">{midiLabel(midi)}</output></dd></div>
  </dl>;
}

export function PadRecordingSource({source, disabled, onChange}: {
  source: PadCaptureSource;
  disabled: boolean;
  onChange(source: PadCaptureSource): void;
}) {
  return <section className="system-recording-source" aria-label="Pad recording settings">
    <h3>Empty Pad recording source</h3>
    <TouchSegment label="Pad recording source" value={source} disabled={disabled}
      options={[{value: "microphone", label: "Microphone"},
        {value: "master", label: "Internal playback"}]}
      onChange={value => {if (value !== source) onChange(value);}} />
    <p>{disabled ? "Finish the current Pad recording before changing its source."
      : "Hold an empty Pad to record. Release to save."}</p>
  </section>;
}

export function ProviderSettings({session}: {session: CreatorCandidateRuntimeSession}) {
  const [listing, setListing] = useState<CandidateProviderList | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const generation = useRef(0);
  useEffect(() => {
    const token = ++generation.current;
    let changed = false;
    const unsubscribe = subscribeProviderPermissions(session, value => {
      changed = true; setListing(value); setError(null);
    });
    void session.listProviders().then(value => {
      if (generation.current === token && !changed) setListing(value);
    }, () => {if (generation.current === token && !changed) setError("Provider settings unavailable. Try opening System again.");});
    return () => {generation.current++; unsubscribe();};
  }, [session]);
  return <section aria-label="Provider management">
    <h3>Providers</h3>
    {listing === null ? <p role="status">Loading Providers…</p> : <>
      <ul>{listing.providers.map(provider => <li key={provider.id}>
        {provider.id} · {provider.capabilities.map(capability => capability.capability_id).join(", ")}
      </li>)}</ul>
      <p>Choose the analysis Provider and grant permission beside the analysis action.</p>
      {listing.granted_permissions.map(permission => <button key={permission} type="button" disabled={busy}
        onClick={() => {
          const token = generation.current; setBusy(true); setError(null);
          void changeProviderPermission(session, permission, false)
            .catch(() => {if (generation.current === token) setError("Permission was not changed. Refresh System before trying again.");})
            .finally(() => {if (generation.current === token) setBusy(false);});
        }}>Revoke {permission}</button>)}
    </>}
    {error !== null && <p role="alert">{error}</p>}
  </section>;
}

export function SystemSurface({children, onBack, active = true}: {
  children: ReactNode;
  onBack(): void;
  active?: boolean;
}) {
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {if (active) heading.current?.focus();}, [active]);
  return <section className="system-surface" aria-label="System" hidden={!active}>
    <header><h2 tabIndex={-1} ref={heading}>System</h2>
      <span>Device settings</span></header>
    <button type="button" className="system-back is-primary" onClick={onBack}>Back to music</button>
    {children}
  </section>;
}
