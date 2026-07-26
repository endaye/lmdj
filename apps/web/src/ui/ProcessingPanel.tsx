import { UploadingView } from "./UploadingView";

export function ProcessingPanel({
  fileName,
  state,
  lastNonterminalState,
}: {
  fileName: string;
  state: string;
  lastNonterminalState: string;
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
      <UploadingView
        state={state}
        lastNonterminalState={lastNonterminalState}
      />
      <p className="processing-panel__hint">
        可以返回“我的歌曲”继续浏览；处理会在后台继续。
      </p>
    </section>
  );
}
