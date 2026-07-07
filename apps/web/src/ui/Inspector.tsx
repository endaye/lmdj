import type { PatchBundle } from "../patch/loader";

export function Inspector(_props: { bundle: PatchBundle<unknown> }) {
  return <div className="inspector" data-testid="inspector" />;
}
