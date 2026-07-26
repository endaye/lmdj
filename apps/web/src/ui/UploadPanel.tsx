import { useState } from "react";

export function UploadPanel({ onUpload }: { onUpload: (base: string, file: File) => void }) {
  const [base, setBase] = useState(
    (import.meta.env.VITE_API_BASE as string | undefined) ?? "http://localhost:8000",
  );
  const [file, setFile] = useState<File | null>(null);

  return (
    <div className="upload-panel" data-testid="api-panel">
      <div className="upload-panel-title">选择一首歌曲</div>
      {import.meta.env.DEV && (
        <details className="upload-panel__developer">
          <summary>开发者设置</summary>
          <label htmlFor="api-base-input">API Base</label>
          <input
            id="api-base-input"
            className="api-base"
            data-testid="api-base-input"
            value={base}
            onChange={(e) => setBase(e.target.value)}
            spellCheck={false}
          />
        </details>
      )}
      <label className="upload-panel__file" htmlFor="api-file-input">
        <span>{file?.name ?? "选择 WAV 或 MP3"}</span>
        <input
          id="api-file-input"
          type="file"
          accept=".wav,.mp3,audio/wav,audio/mpeg"
          data-testid="api-file-input"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
      </label>
      <button
        type="button"
        disabled={!file}
        onClick={() => file && onUpload(base, file)}
      >
        上传并制作 Patch
      </button>
    </div>
  );
}
