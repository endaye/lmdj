import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type RefObject,
  type ReactNode,
} from "react";
import { CreatorToolRail } from "./CreatorToolRail";
import type { WorkbenchMode, WorkbenchViewModel } from "./workbench/model";

type WorkbenchLayout = "wide" | "compact-wide" | "tablet" | "phone";

function layoutForWidth(width: number): WorkbenchLayout {
  if (width >= 1280) return "wide";
  if (width >= 960) return "compact-wide";
  if (width >= 600) return "tablet";
  return "phone";
}

function useContainerLayout(
  shellRef: RefObject<HTMLElement | null>,
): WorkbenchLayout {
  const [layout, setLayout] = useState<WorkbenchLayout>("wide");

  useEffect(() => {
    const shell = shellRef.current;
    if (!shell) return;
    const update = (width: number) => {
      if (width > 0) setLayout(layoutForWidth(width));
    };
    // CSS container queries and ResizeObserver.contentRect both use the inline
    // content box; clientWidth matches that here because the shell has no padding.
    update(shell.clientWidth);
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (entry) update(entry.contentRect.width);
    });
    observer.observe(shell);
    return () => observer.disconnect();
  }, [shellRef]);

  return layout;
}

/** Structural shell only: audio, loading, and playback effects stay in App and its slots. */
export function WorkbenchShell({
  model,
  shellLabel,
  mode,
  onModeChange,
  availableModes,
  appBar,
  assistant,
  assistantExpanded = false,
  onCanvasInteraction,
  instrumentCanvas,
  contextInspector,
  statusBar,
}: {
  model?: WorkbenchViewModel;
  shellLabel?: string;
  mode: WorkbenchMode;
  onModeChange: (mode: WorkbenchMode) => void;
  availableModes: WorkbenchMode[];
  appBar: ReactNode;
  assistant?: ReactNode;
  assistantExpanded?: boolean;
  onCanvasInteraction?: () => void;
  instrumentCanvas: ReactNode;
  contextInspector: ReactNode;
  statusBar: ReactNode;
}) {
  const shellRef = useRef<HTMLElement>(null);
  const inspectorRef = useRef<HTMLElement>(null);
  const layout = useContainerLayout(shellRef);
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const isWide = layout === "wide";
  const isPhone = layout === "phone";
  const modalOpen = !isWide && inspectorOpen;
  const inspectorVisible = isWide || inspectorOpen;
  const toggleRef = useRef<HTMLButtonElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const restoreToggleFocus = useRef(false);
  const padColumns = layout === "wide" || layout === "compact-wide" ? 8 : 4;
  const selectedColumn =
    model?.selectedPad === null || model?.selectedPad === undefined
      ? null
      : model.selectedPad.index % padColumns;
  const inspectorSide =
    layout === "phone"
      ? "sheet"
      : selectedColumn !== null && selectedColumn >= padColumns / 2
        ? "left"
        : "right";

  const closeInspector = useCallback(() => {
    restoreToggleFocus.current = true;
    setInspectorOpen(false);
  }, []);

  useEffect(() => {
    if (!modalOpen) return;
    closeRef.current?.focus();
    const containFocus = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        closeInspector();
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = Array.from(
        inspectorRef.current?.querySelectorAll<HTMLElement>(
          'button:not(:disabled), [href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])',
        ) ?? [],
      ).filter((element) => !element.hidden);
      if (focusable.length === 0) {
        event.preventDefault();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement;
      if (event.shiftKey && (active === first || !inspectorRef.current?.contains(active))) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (active === last || !inspectorRef.current?.contains(active))) {
        event.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", containFocus);
    return () => window.removeEventListener("keydown", containFocus);
  }, [closeInspector, modalOpen]);

  useEffect(() => {
    if (!inspectorOpen && restoreToggleFocus.current && !isWide) {
      restoreToggleFocus.current = false;
      toggleRef.current?.focus();
    }
  }, [inspectorOpen, isWide]);

  useEffect(() => {
    if (!isWide) return;
    restoreToggleFocus.current = false;
    setInspectorOpen(false);
  }, [isWide]);

  return (
    <section
      ref={shellRef}
      className="workbench-shell"
      data-testid="workbench-shell"
      data-layout={layout}
      aria-label={model ? `Patch ${model.patchId}` : shellLabel ?? "LMDJ Creator"}
    >
      <header
        className="workbench-app-bar"
        data-testid="app-bar"
        data-compact={isPhone ? "true" : "false"}
        data-assistant-open={assistantExpanded ? "true" : "false"}
        inert={modalOpen}
      >
        <div className="workbench-app-bar__main">{appBar}</div>
        {assistant && (
          <div
            className="workbench-assistant-slot"
            data-testid="assistant-slot"
          >
            {assistant}
          </div>
        )}
        <button
          ref={toggleRef}
          type="button"
          className="workbench-inspector-toggle"
          data-testid="inspector-toggle"
          aria-controls="workbench-context-inspector"
          aria-expanded={inspectorVisible}
          onClick={() => setInspectorOpen((open) => !open)}
        >
          <span aria-hidden="true">◧</span>
          <span>Inspector</span>
        </button>
      </header>
      <div className="workbench-shell__content" data-testid="workbench-content">
        <div
          className="workbench-creator-tools"
          data-testid="creator-tools"
          inert={modalOpen}
        >
          <CreatorToolRail
            mode={mode}
            onModeChange={onModeChange}
            availableModes={availableModes}
          />
        </div>
        <main
          className="workbench-instrument-canvas"
          data-testid="instrument-canvas"
          inert={modalOpen}
          onPointerDownCapture={onCanvasInteraction}
        >
          {instrumentCanvas}
        </main>
        {!isWide && inspectorOpen && (
          <button
            type="button"
            className="workbench-inspector-backdrop"
            data-testid="inspector-backdrop"
            aria-label="关闭 Inspector"
            tabIndex={-1}
            onClick={closeInspector}
          />
        )}
        <aside
          ref={inspectorRef}
          id="workbench-context-inspector"
          className={`workbench-context-inspector${inspectorOpen ? " workbench-context-inspector--open" : ""}`}
          data-testid="context-inspector"
          data-side={inspectorSide}
          aria-label="Inspector"
          aria-hidden={!inspectorVisible}
          aria-modal={!isWide && inspectorOpen ? "true" : undefined}
          role={!isWide ? "dialog" : undefined}
          inert={!inspectorVisible}
        >
          <button
            ref={closeRef}
            type="button"
            className="workbench-inspector-close"
            data-testid="inspector-close"
            onClick={closeInspector}
          >
            Close Inspector
          </button>
          {contextInspector}
        </aside>
      </div>
      <footer
        className="workbench-status-bar"
        data-testid="status-bar"
        inert={modalOpen}
      >
        {statusBar}
      </footer>
    </section>
  );
}
