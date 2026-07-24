import type { ReactNode } from "react";
import type { WorkbenchViewModel } from "./workbench/model";

function PatchSummary({ model }: { model: WorkbenchViewModel }) {
  return (
    <>
      <dl className="context-inspector__facts">
        <div><dt>Schema</dt><dd>{model.schema}</dd></div>
        <div><dt>Quality</dt><dd>{model.quality.status}</dd></div>
        <div><dt>Score</dt><dd>{model.quality.score ?? "n/a"}</dd></div>
        <div><dt>Readiness</dt><dd>{model.readiness}</dd></div>
      </dl>
      <section>
        <h3>Elements</h3>
        <ul>
          {model.elements.map((element) => (
            <li key={element.elementId} className={`inspector-source--${element.status}`}>
              <span>{element.name}</span>
              <small>{element.kind} · {element.status.toUpperCase()}</small>
            </li>
          ))}
        </ul>
      </section>
      {model.unmappedElementIds.length > 0 && (
        <section>
          <h3>Unmapped</h3>
          <ul>
            {model.unmappedElementIds.map((id) => <li key={id}>{id}</li>)}
          </ul>
        </section>
      )}
      {model.warnings.length > 0 && (
        <section>
          <h3>Warnings</h3>
          <ul>
            {model.warnings.map((warning) => <li key={warning}>{warning}</li>)}
          </ul>
        </section>
      )}
    </>
  );
}

function inspectorAccent(model: WorkbenchViewModel): string {
  const pad = model.selectedPad;
  if (!pad) return "patch";
  if (pad.action === "empty") return "empty";
  if (pad.index === 0) return "drums";
  if (pad.index === 1) return "bass";
  if (pad.index === 2) return "harmony";
  if (pad.index === 3) return "lead";
  return "action";
}

export function ContextInspector({
  model,
  exportContent,
}: {
  model: WorkbenchViewModel;
  exportContent?: ReactNode;
}) {
  const pad = model.selectedPad;
  return (
    <div
      className="context-inspector-content"
      data-testid="context-inspector-content"
      data-inspector-accent={exportContent ? "export" : inspectorAccent(model)}
    >
      {exportContent ?? (
        <>
          <div className="context-inspector__header" data-testid="context-inspector-header">
            <span>{pad ? "Selected Pad" : "Patch"}</span>
            <h2>
              {pad
                ? `Pad ${String(pad.index + 1).padStart(2, "0")} · ${pad.label}`
                : model.patchId}
            </h2>
          </div>
          {!pad ? (
            <PatchSummary model={model} />
          ) : (
            <>
              <dl className="context-inspector__facts">
                <div><dt>Slot</dt><dd>{pad.slot}</dd></div>
                <div><dt>Action</dt><dd>{pad.action}</dd></div>
                <div>
                  <dt>Source</dt>
                  <dd>
                    {model.selectedPadSources.length === 0
                      ? pad.action === "empty" ? "EMPTY" : "RESERVED"
                      : model.selectedPadSources.some((source) => source.status === "missing")
                        ? "MISSING"
                        : "READY"}
                  </dd>
                </div>
              </dl>
              {model.selectedPadSources.length > 0 && (
                <section>
                  <h3>Sources</h3>
                  <ul>
                    {model.selectedPadSources.map((source) => (
                      <li
                        key={source.elementId}
                        className={`inspector-source--${source.status}`}
                      >
                        <span>{source.name}</span>
                        <small>{source.elementId} · {source.status.toUpperCase()}</small>
                      </li>
                    ))}
                  </ul>
                </section>
              )}
            </>
          )}
        </>
      )}
    </div>
  );
}
