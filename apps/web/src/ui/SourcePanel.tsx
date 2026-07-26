import { ChameleonUploadStage } from "../chameleon/ChameleonUploadStage";
import { DropZone } from "./DropZone";
import { Wordmark } from "./Wordmark";

export function SourcePanel({
  onFiles,
  onExample,
  onUpload,
}: {
  onFiles: (files: Map<string, ArrayBuffer>) => void;
  onExample: () => void;
  onUpload: (base: string, file: File) => void;
}) {
  return (
    <section
      className="source-panel gallery-stage"
      data-testid="source-panel"
    >
      <header className="gallery-stage__header">
        <Wordmark />
        <span>AI MUSIC MATERIAL INSTRUMENT · STAGE 01</span>
      </header>
      <div className="gallery-stage__hero">
        <header className="gallery-stage__title">
          <span>Source · Stage 01</span>
          <h1>Feed it<br />a sound</h1>
          <p>One track enters. A playable 16-pad Patch comes back.</p>
        </header>
        <ChameleonUploadStage onUpload={onUpload} />
      </div>
      <div className="source-limits" aria-label="Upload limits">
        <strong>WAV / MP3</strong>
        <span>200 MiB max</span>
        <span>600 秒 max</span>
      </div>
      <div className="source-example">
        <span>Already have a patch package?</span>
        <DropZone onFiles={onFiles} onExample={onExample} />
      </div>
    </section>
  );
}
