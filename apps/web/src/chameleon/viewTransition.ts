import { flushSync } from "react-dom";

type TransitionDocument = Document & {
  startViewTransition?: (update: () => void) => unknown;
};

export function runChameleonViewTransition(update: () => void): void {
  const reduced =
    typeof matchMedia === "function"
    && matchMedia("(prefers-reduced-motion: reduce)").matches;
  const start = (document as TransitionDocument).startViewTransition;
  if (reduced || typeof start !== "function") {
    update();
    return;
  }
  start.call(document, () => flushSync(update));
}
