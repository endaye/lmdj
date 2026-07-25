export interface LoadedSourceSummary {
  kind: "API Job" | "Local package" | "Example package";
  name: string;
  detail: string;
}

interface LoadedSourceFacts {
  patchId: string;
  padCount: number;
  elementCount: number;
  playableElementCount: number;
  missingElementCount: number;
}

export function LoadedSourcePanel({
  source,
  facts,
  onReplace,
}: {
  source: LoadedSourceSummary;
  facts: LoadedSourceFacts;
  onReplace: () => void;
}) {
  return (
    <section className="loaded-source-panel" data-testid="loaded-source-panel">
      <header className="state-heading">
        <span>Source · retained</span>
        <h1>已加载来源</h1>
        <p>切换模式不会卸载当前 Patch；返回 Performance 可继续演奏。</p>
      </header>
      <div className="loaded-source-card">
        <div className="loaded-source-card__identity">
          <span>{source.kind}</span>
          <strong>{source.name}</strong>
          <small>{source.detail}</small>
        </div>
        <dl className="loaded-source-facts">
          <div>
            <dt>Patch ID</dt>
            <dd>{facts.patchId}</dd>
          </div>
          <div>
            <dt>Pad contract</dt>
            <dd>{facts.padCount} 个数据 Pad</dd>
          </div>
          <div>
            <dt>Audio assets</dt>
            <dd>
              {facts.playableElementCount}/{facts.elementCount} 可播放
            </dd>
          </div>
          <div>
            <dt>Missing</dt>
            <dd>{facts.missingElementCount}</dd>
          </div>
        </dl>
      </div>
      <div className="loaded-source-actions">
        <p>更换音频会明确离开当前 Patch，并返回 Upload。</p>
        <button type="button" onClick={onReplace}>
          更换音频
        </button>
      </div>
    </section>
  );
}

export function LoadedSourceInspector({
  source,
  facts,
}: {
  source: LoadedSourceSummary;
  facts: LoadedSourceFacts;
}) {
  return (
    <section
      className="loaded-source-inspector"
      data-testid="loaded-source-inspector"
    >
      <header>
        <span>Loaded Source</span>
        <h2>{source.kind}</h2>
      </header>
      <p>{source.name}</p>
      <small>{source.detail}</small>
      <dl>
        <div>
          <dt>Patch</dt>
          <dd>{facts.patchId}</dd>
        </div>
        <div>
          <dt>Playable</dt>
          <dd>
            {facts.playableElementCount}/{facts.elementCount} assets
          </dd>
        </div>
      </dl>
      <p>Patch retained. Performance and Export remain available.</p>
    </section>
  );
}
