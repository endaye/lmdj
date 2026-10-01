import {useEffect, useRef, useState, type ReactNode} from "react";
import type {CreatorCandidateRuntimeSession, CandidateProviderList} from "../runtime/runtime_types";

export function ProviderSettings({session}: {session: CreatorCandidateRuntimeSession}) {
  const [listing, setListing] = useState<CandidateProviderList | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const generation = useRef(0);
  useEffect(() => {
    const token = ++generation.current;
    void session.listProviders().then(value => {
      if (generation.current === token) setListing(value);
    }, () => {if (generation.current === token) setError("Provider settings unavailable. Try opening System again.");});
    return () => {generation.current++;};
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
          void session.listProviders().then(current => session.configureProviderPermissions(
            current.granted_permissions.filter(value => value !== permission),
          )).then(result => {
            if (generation.current === token) setListing({...listing, granted_permissions: result.granted_permissions});
          }, () => {if (generation.current === token) setError("Permission was not changed. Refresh System before trying again.");})
            .finally(() => {if (generation.current === token) setBusy(false);});
        }}>Revoke {permission}</button>)}
    </>}
    {error !== null && <p role="alert">{error}</p>}
  </section>;
}

export function SystemSurface({children, onBack}: {children: ReactNode; onBack(): void}) {
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {heading.current?.focus();}, []);
  return <section className="system-surface" aria-label="System">
    <header><h2 tabIndex={-1} ref={heading}>System</h2>
      <button type="button" onClick={onBack}>Back to music</button></header>
    {children}
  </section>;
}
