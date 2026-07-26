import { useRef, useState } from "react";
import { deriveChameleonVisualState } from "./adapter";
import { ChameleonSurface } from "./ChameleonSurface";
import { createVisualSignature } from "./visualSignature";

function isSupportedAudio(file: File): boolean {
  return (
    file.type === "audio/wav"
    || file.type === "audio/mpeg"
    || /\.(wav|mp3)$/i.test(file.name)
  );
}

export function ChameleonUploadStage({
  onUpload,
}: {
  onUpload: (base: string, file: File) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const dragDepth = useRef(0);
  const [base, setBase] = useState(
    (import.meta.env.VITE_API_BASE as string | undefined)
      ?? "http://localhost:8000",
  );
  const [dragReady, setDragReady] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  const visualState = deriveChameleonVisualState({
    appPhase: "source",
    interaction: dragReady ? "drag-ready" : "none",
  });
  const submit = (file: File) => {
    if (!isSupportedAudio(file)) {
      setLocalError("Choose one WAV or MP3 file");
      return;
    }
    setLocalError(null);
    onUpload(base, file);
  };

  return (
    <section
      className={`chameleon-upload-stage${dragReady ? " chameleon-upload-stage--over" : ""}`}
      data-testid="chameleon-upload-stage"
      onDragEnter={(event) => {
        event.preventDefault();
        dragDepth.current += 1;
        setDragReady(true);
      }}
      onDragOver={(event) => event.preventDefault()}
      onDragLeave={(event) => {
        event.preventDefault();
        dragDepth.current = Math.max(0, dragDepth.current - 1);
        if (dragDepth.current === 0) setDragReady(false);
      }}
      onDrop={(event) => {
        event.preventDefault();
        dragDepth.current = 0;
        setDragReady(false);
        const file = event.dataTransfer.files[0];
        if (file) submit(file);
      }}
    >
      <label className="chameleon-upload-stage__api">
        <span>API</span>
        <input
          className="api-base"
          data-testid="api-base-input"
          value={base}
          onChange={(event) => setBase(event.target.value)}
          spellCheck={false}
        />
      </label>
      <input
        ref={inputRef}
        type="file"
        accept=".wav,.mp3,audio/wav,audio/mpeg"
        data-testid="api-file-input"
        hidden
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) submit(file);
        }}
      />
      <ChameleonSurface
        state={visualState}
        signature={createVisualSignature("lmdj:gallery", visualState)}
        onActivate={() => {
          if (inputRef.current) inputRef.current.value = "";
          inputRef.current?.click();
        }}
        onToggle={() => undefined}
        onDismiss={() => undefined}
      />
      {localError && <p role="alert">{localError}</p>}
    </section>
  );
}
