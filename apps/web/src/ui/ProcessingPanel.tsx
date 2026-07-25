import { UploadingView } from "./UploadingView";

export function ProcessingPanel({
  fileName,
  state,
}: {
  fileName: string;
  state: string;
}) {
  return (
    <section className="processing-panel" data-testid="processing-panel">
      <header className="state-heading">
        <span>Processing · live evidence</span>
        <h1>Building your Patch</h1>
        <p>
          Source retained · <strong>{fileName}</strong>
        </p>
      </header>
      <UploadingView state={state} />
    </section>
  );
}
