import { DropZone } from "./DropZone";
import { UploadPanel } from "./UploadPanel";

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
    <section className="source-panel" data-testid="source-panel">
      <header className="state-heading">
        <span>Source · Stage 01</span>
        <h1>Feed it a sound</h1>
        <p>Upload one supported audio file or open the included example.</p>
      </header>
      <div className="source-limits" aria-label="Upload limits">
        <strong>WAV / MP3</strong>
        <span>200 MiB max</span>
        <span>600 秒 max</span>
      </div>
      <UploadPanel onUpload={onUpload} />
      <div className="source-example">
        <span>Already have a patch package?</span>
        <DropZone onFiles={onFiles} onExample={onExample} />
      </div>
    </section>
  );
}
