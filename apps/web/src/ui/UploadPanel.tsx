import { useState } from "react";

export function UploadPanel({ onUpload }: { onUpload: (base: string, file: File) => void }) {
  const [base, setBase] = useState(
    (import.meta.env.VITE_API_BASE as string | undefined) ?? "http://localhost:8000",
  );
  const [file, setFile] = useState<File | null>(null);

  return (
    <div className="upload-panel" data-testid="api-panel">
      <div className="upload-panel-title">Upload audio</div>
      <input
        className="api-base"
        data-testid="api-base-input"
        value={base}
        onChange={(e) => setBase(e.target.value)}
        spellCheck={false}
      />
      <input
        type="file"
        accept=".wav,.mp3,audio/wav,audio/mpeg"
        data-testid="api-file-input"
        onChange={(e) => setFile(e.target.files?.[0] ?? null)}
      />
      <button disabled={!file} onClick={() => file && onUpload(base, file)}>
        传歌 · 上传并制作 Patch
      </button>
    </div>
  );
}
