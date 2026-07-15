import { useState } from "react";

export function UploadPanel({ onUpload }: { onUpload: (base: string, file: File) => void }) {
  const [base, setBase] = useState(
    (import.meta.env.VITE_API_BASE as string | undefined) ?? "http://localhost:8000",
  );
  const [file, setFile] = useState<File | null>(null);

  return (
    <div className="upload-panel" data-testid="api-panel">
      <div className="upload-panel-title">从 API 加载（上传歌曲）</div>
      <input
        className="api-base"
        data-testid="api-base-input"
        value={base}
        onChange={(e) => setBase(e.target.value)}
        spellCheck={false}
      />
      <input
        type="file"
        accept="audio/*"
        data-testid="api-file-input"
        onChange={(e) => setFile(e.target.files?.[0] ?? null)}
      />
      <button disabled={!file} onClick={() => file && onUpload(base, file)}>
        传歌
      </button>
    </div>
  );
}
