import {useEffect, useRef, useState} from "react";
import type {
  CandidateJobView, CandidateProviderList, CandidateRecipe,
  CreatorCandidateRuntimeSession, CreatorRuntimeSession,
} from "../runtime/runtime_types";
import {
  activeCandidateSet, candidateJobId, candidatePlan, candidateSources,
  type CandidateSource, type CandidateTargetDraft,
} from "../state/candidate_state";

const capability = "sample.slice.v1";
const permission = "sample.slice.execute";
export function isCandidateSession(
  session: CreatorRuntimeSession | undefined,
): session is CreatorCandidateRuntimeSession {
  if (!session) return false;
  return ["listProviders", "configureProviderPermissions", "selectProvider", "runCandidateJob",
    "inspectCandidateJob", "cancelCandidateJob", "discardCandidateSet", "auditionCandidate",
    "stopCandidateAudition", "adoptCandidates"].every(name =>
    typeof (session as unknown as Record<string, unknown>)[name] === "function");
}
function errorCode(error: unknown): string {
  return typeof error === "object" && error !== null && "code" in error
    ? String(error.code) : "UNKNOWN_RESPONSE";
}
function errorCopy(error: unknown): string {
  const code = errorCode(error);
  if (code === "REVISION_CONFLICT") return "The Project or source changed. Refresh before trying again.";
  if (code === "NOT_FOUND") return "The source or slice is unavailable. Refresh to inspect it.";
  if (code === "PERMISSION_DENIED") return "Analysis permission is required. Grant it explicitly above.";
  if (code === "RESOURCE_EXHAUSTED") return "These Pads exceed the available audio capacity. Choose fewer or shorter slices.";
  return error instanceof Error ? error.message : `The request was refused (${code}).`;
}
function recipeLabel(recipe: CandidateRecipe, index: number): string {
  return `Slice ${index + 1} · ${(recipe.start_frame / recipe.frame_rate).toFixed(3)}–${
    (recipe.end_frame / recipe.frame_rate).toFixed(3)} s`;
}
interface CandidateSurfaceProps {
  session: CreatorCandidateRuntimeSession;
  projectId: string;
  projectRevision: number;
  onRefreshProject: (committedRevision?: number) => Promise<unknown>;
}

export function CandidateSurface({session, projectId, projectRevision, onRefreshProject}: CandidateSurfaceProps) {
  const [sources, setSources] = useState<readonly CandidateSource[]>([]);
  const [source, setSource] = useState("");
  const [providers, setProviders] = useState<CandidateProviderList | null>(null);
  const [provider, setProvider] = useState("");
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const [error, setError] = useState<string | null>(null);
  const [uncertain, setUncertain] = useState(false);
  const [adoptionPending, setAdoptionPending] = useState(false);
  const mounted = useRef(false);
  useEffect(() => {
    mounted.current = true;
    let active = true;
    void Promise.all([session.inspectProject(), session.listProviders()]).then(([inspection, listing]) => {
      const projection = candidateSources(inspection, projectId);
      if (!active) return;
      setSources(projection.sources);
      setProviders(listing);
    }).catch(error => {if (active) setError(errorCopy(error));});
    return () => {active = false; mounted.current = false;};
  }, [session, projectId]);
  const settingsAction = async (action: () => Promise<void>) => {
    if (busyRef.current) return;
    busyRef.current = true; setBusy(true); setError(null);
    try {await action();} catch (error) {if (mounted.current) setError(errorCopy(error));}
    finally {busyRef.current = false; if (mounted.current) setBusy(false);}
  };
  const refreshProject = async (committedRevision?: number) => {
    // An unknown adoption response must be reconciled with Project Truth before
    // the user can create another command, including after a source switch.
    await onRefreshProject(committedRevision);
    const projection = candidateSources(await session.inspectProject(), projectId);
    if (!mounted.current) return;
    setSources(projection.sources);
    setUncertain(false);
  };
  return <section className="candidate-surface" aria-label="Slice">
    <header><h2>Slice</h2><p>Analyze a source, listen to slices, then choose their Pads.</p></header>
    <fieldset disabled={busy} className="candidate-settings">
      <legend>Analysis setup</legend>
      <label>Provider<select aria-label="Slice Provider" value={provider} onChange={event => {
        const chosen = event.target.value;
        if (!chosen) {setProvider(""); return;}
        void settingsAction(async () => {
          await session.selectProvider(capability, chosen);
          if (mounted.current) setProvider(chosen);
        });
      }}><option value="">Choose a Provider</option>{providers?.providers.filter(item =>
        item.capabilities.some(item => item.capability_id === capability)).map(item =>
        <option key={item.id} value={item.id}>{item.id === "local.sample.slice" ? "Local reference detector" : item.id}</option>)}</select></label>
      <p>The local reference detector runs on its registered test platform, on this device.</p>
      <button type="button" disabled={!providers || providers.granted_permissions?.includes(permission)}
        onClick={() => void settingsAction(async () => {
          const current = await session.listProviders();
          if (!Array.isArray(current.granted_permissions)) throw new Error("Current permissions are unavailable; no permissions were changed.");
          const result = await session.configureProviderPermissions([...new Set([...current.granted_permissions, permission])]);
          if (mounted.current) setProviders({...current, granted_permissions: result.granted_permissions});
        })}>{providers?.granted_permissions?.includes(permission) ? "Analysis permission granted" : "Grant analysis permission"}</button>
    </fieldset>
    <label className="candidate-source">Source<select aria-label="Slice source" value={source}
      onChange={event => {setSource(event.target.value); setError(null);}}>
      <option value="">Choose a source</option>{sources.map(item => <option key={item.assetId} value={item.assetId}>{item.label}</option>)}
    </select></label>
    {sources.length === 0 ? <p>Import or record audio in Sample to add a source.</p> : null}
    {error ? <p role="alert">{error}</p> : null}
    {source ? <CandidateJob key={`${projectId}:${source}`} session={session} projectId={projectId}
      assetId={source} revision={projectRevision} analysisReady={Boolean(provider) && !busy &&
        Boolean(providers?.granted_permissions?.includes(permission))}
      uncertain={uncertain} adoptionPending={adoptionPending}
      onAdoptionPendingChange={setAdoptionPending}
      onUncertain={() => setUncertain(true)} onRefreshProject={refreshProject} /> : null}
  </section>;
}
interface CandidateJobProps {
  session: CreatorCandidateRuntimeSession; projectId: string; assetId: string; revision: number;
  analysisReady: boolean; uncertain: boolean; adoptionPending: boolean;
  onAdoptionPendingChange: (pending: boolean) => void; onUncertain: () => void;
  onRefreshProject: (committedRevision?: number) => Promise<void>;
}
function CandidateJob({session, projectId, assetId, revision, analysisReady, uncertain,
  onUncertain, onRefreshProject, adoptionPending, onAdoptionPendingChange}: CandidateJobProps) {
  const jobId = candidateJobId(projectId, assetId);
  const [job, setJob] = useState<CandidateJobView | null>(null);
  const [publicSource, setPublicSource] = useState(false);
  const [rows, setRows] = useState<CandidateTargetDraft[]>([]);
  const [busy, setBusy] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const mounted = useRef(false);
  const locked = useRef(true);
  const active = activeCandidateSet(job);
  const plan = candidatePlan(rows, active);
  useEffect(() => {
    mounted.current = true;
    let live = true;
    void session.inspectCandidateJob(jobId).then(result => {
      if (live) setJob(result);
    }).catch(error => {if (live && errorCode(error) !== "NOT_FOUND") setError(errorCopy(error));})
      .finally(() => {if (live) {locked.current = false; setBusy(false);}});
    const stop = () => {void session.stopCandidateAudition().catch(() => {});};
    window.addEventListener("pagehide", stop);
    return () => {
      live = false; mounted.current = false;
      window.removeEventListener("pagehide", stop);
      stop();
    };
  }, [session, jobId]);
  const operation = async (action: () => Promise<void>) => {
    if (locked.current) return;
    locked.current = true; setBusy(true); setError(null); setMessage(null);
    try {await action();} catch (error) {if (mounted.current) setError(errorCopy(error));}
    finally {locked.current = false; if (mounted.current) setBusy(false);}
  };
  const acceptJob = (value: CandidateJobView) => {
    if (!mounted.current) return;
    setJob(value);
    if (value.active_set_id !== job?.active_set_id) setRows([]);
  };
  const refresh = () => operation(async () => {
    await onRefreshProject();
    if (!mounted.current) return;
    try {acceptJob(await session.inspectCandidateJob(jobId));}
    catch (error) {if (errorCode(error) !== "NOT_FOUND") throw error; setJob(null); setRows([]);}
  });
  const analyze = () => operation(async () => {
    await session.stopCandidateAudition();
    if (!mounted.current) return;
    acceptJob(await session.runCandidateJob({job_id: jobId, attempt_id: crypto.randomUUID(),
      project_id: projectId, asset_id: assetId, expected_revision: revision,
      parameters: {}, data_classification: "public", platform: "test", region: "local",
      required_permissions: [permission]}));
  });
  const audition = (candidateId: string) => operation(async () => {
    if (!active) return;
    const result = await session.auditionCandidate({project_id: projectId, expected_revision: revision,
      job_id: jobId, set_id: active.set_id, candidate_id: candidateId});
    if (!mounted.current) {await session.stopCandidateAudition(); return;}
    setMessage(result.played ? "Preview started." : "Preview was not played. Activate audio and try again.");
  });
  const adopt = () => operation(async () => {
    if (!active || plan.error || uncertain) return;
    await session.stopCandidateAudition();
    if (!mounted.current) return;
    onUncertain();
    onAdoptionPendingChange(true);
    try {
      const result = await session.adoptCandidates({project_id: projectId, expected_revision: revision,
        command_id: crypto.randomUUID(), job_id: jobId, set_id: active.set_id, selections: plan.selections});
      // Commit may have succeeded even if the subsequent projection fails.
      onUncertain();
      await onRefreshProject(result.project_revision);
      if (mounted.current) {setRows([]); setMessage(`Adopted ${result.adopted.length} slices.`);}
    } catch (error) {
      // A refusal is safe to present, but no failed response is silently retried.
      // Inspect for every failure, covering transport loss and malformed replies.
      onUncertain();
      throw error;
    } finally {
      onAdoptionPendingChange(false);
    }
  });
  const changeRow = (key: string, field: "candidateId" | "bank" | "pad", value: string) => {
    setRows(current => current.map(row => row.key === key ? {...row, [field]: value} : row));
  };
  const pending = job?.history.findLast(item => item.status === "pending" || item.status === "interrupted");
  return <div className="candidate-job" aria-busy={busy}>
    <label className="candidate-classification">
      <input type="checkbox" checked={publicSource} disabled={busy}
        onChange={event => setPublicSource(event.target.checked)} />
      Use this source as public audio for local analysis
    </label>
    <p>The current analysis policy accepts public audio. Processing runs locally.</p>
    <div className="candidate-actions">
      <button type="button" disabled={busy || !analysisReady || !publicSource || uncertain} onClick={() => void analyze()}>{job ? "Retry analysis" : "Analyze"}</button>
      <button type="button" disabled={busy || adoptionPending} onClick={() => void refresh()}>Refresh slices and Project</button>
      {pending ? <button type="button" disabled={busy} onClick={() => void operation(async () => {
        acceptJob(await session.cancelCandidateJob(jobId, pending.intent.attempt_id));
      })}>Cancel analysis</button> : null}
      <button type="button" onClick={() => {
        void session.stopCandidateAudition().then(() => {if (mounted.current) setMessage("Preview stopped.");},
          error => {if (mounted.current) setError(errorCopy(error));});
      }}>Stop preview</button>
    </div>
    {error ? <p role="alert">{error}</p> : null}
    {message ? <p role="status">{message}</p> : null}
    {uncertain ? <p role="alert">Inspect the Project with Refresh before confirming another adoption. The previous request may have committed.</p> : null}
    {job?.history.at(-1)?.status === "failed" ? <p role="status">Analysis failed. Any earlier active slices remain available.</p> : null}
    {job?.history.at(-1)?.status === "cancelled" ? <p role="status">Analysis cancelled. Any earlier active slices remain available.</p> : null}
    {job?.history.at(-1)?.status === "interrupted" ? <p role="status">Analysis was interrupted. Retry explicitly to analyze again.</p> : null}
    {job && !active ? <p role="status">No active slices. Retry analysis to create a new result.</p> : null}
    {active ? <>
      <header className="candidate-result-header"><h3>Detected slices</h3>
        <button type="button" disabled={busy} onClick={() => void operation(async () => {
          await session.stopCandidateAudition();
          if (mounted.current) acceptJob(await session.discardCandidateSet(jobId, active.set_id));
        })}>Discard slices</button></header>
      {active.recipes.length === 0 ? <p role="status">Analysis complete. No slices detected.</p> : null}
      <ol className="candidate-recipes" aria-label="Detected slices">
        {active.recipes.map((recipe, index) => <li key={recipe.candidate_id}>
          <span>{recipeLabel(recipe, index)}</span>
          <span className="candidate-interval">Frames [{recipe.start_frame}, {recipe.end_frame}) · {recipe.frame_rate} Hz</span>
          <button type="button" disabled={busy} onClick={() => void audition(recipe.candidate_id)} aria-label={`Preview slice ${index + 1}`}>Preview</button>
        </li>)}
      </ol>
      {active.recipes.length ? <fieldset disabled={busy || uncertain} className="candidate-plan"><legend>Choose target Pads</legend>
        <p>Each row writes one Pad, replacing its current sound. The source and recorded Pattern stay intact.</p>
        {rows.map((row, index) => <div className="candidate-target" key={row.key}>
          <label>Slice<select aria-label={`Target ${index + 1} slice`} value={row.candidateId} onChange={event => changeRow(row.key, "candidateId", event.target.value)}>
            <option value="">Choose slice</option>{active.recipes.map((recipe, index) => <option key={recipe.candidate_id} value={recipe.candidate_id}>{recipeLabel(recipe, index)}</option>)}
          </select></label>
          <label>Bank<select aria-label={`Target ${index + 1} Bank`} value={row.bank} onChange={event => changeRow(row.key, "bank", event.target.value)}>
            <option value="">Choose Bank</option>{["A", "B", "C", "D"].map((bank, index) => <option key={bank} value={index}>{bank}</option>)}
          </select></label>
          <label>Pad<select aria-label={`Target ${index + 1} Pad`} value={row.pad} onChange={event => changeRow(row.key, "pad", event.target.value)}>
            <option value="">Choose Pad</option>{Array.from({length: 16}, (_, pad) => <option key={pad} value={pad}>{pad + 1}</option>)}
          </select></label>
          <button type="button" aria-label={`Remove target ${index + 1}`} onClick={() => setRows(current => current.filter(item => item.key !== row.key))}>Remove</button>
        </div>)}
        <button type="button" onClick={() => setRows(current => [...current, {key: crypto.randomUUID(), candidateId: "", bank: "", pad: ""}])}>Add target</button>
        {plan.error ? <p role="status">{plan.error}</p> : null}
        <button type="button" disabled={plan.error !== null} onClick={() => void adopt()}>Adopt selected slices</button>
      </fieldset> : null}
    </> : null}
  </div>;
}
