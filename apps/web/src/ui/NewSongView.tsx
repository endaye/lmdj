import { DropZone } from "./DropZone";
import { UploadPanel } from "./UploadPanel";

export function NewSongView({
  onFiles,
  onExample,
  onUpload,
}: {
  onFiles: (files: Map<string, ArrayBuffer>) => void;
  onExample: () => void;
  onUpload: (base: string, file: File) => void;
}) {
  return (
    <section className="new-song-view" data-testid="new-song-view">
      <header className="state-heading">
        <span>New Song · Stage 01</span>
        <h1>上传新歌</h1>
        <p>选择一首歌曲，把它变成可以继续演奏和制作的 Patch。</p>
      </header>
      <div className="source-limits" aria-label="上传限制">
        <strong>WAV / MP3</strong>
        <span>最大 200 MiB</span>
        <span>最长 600 秒</span>
      </div>
      <UploadPanel onUpload={onUpload} />
      <details
        className="advanced-source-actions"
        data-testid="advanced-source-actions"
      >
        <summary>高级 · 导入 Patch 包</summary>
        <p>用于开发验证：导入本地 package，或打开内置示例。</p>
        <DropZone onFiles={onFiles} onExample={onExample} />
      </details>
    </section>
  );
}
