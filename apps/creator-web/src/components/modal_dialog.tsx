import {useEffect, useLayoutEffect, useRef, type ReactNode, type RefObject} from "react";

interface ContainedBackground {
  element: HTMLElement;
  hadInert: boolean;
  ariaHidden: string | null;
}

export interface ModalDialogProps {
  returnFocus: HTMLElement | null;
  onCancel: () => void;
  dialogClassName: string;
  labelledBy?: string;
  label?: string;
  // Resolves the control focused when the dialog opens; defaults to the first
  // focusable element (the ConfirmationDialog behaviour).
  resolveInitialFocus?: (dialog: HTMLDialogElement) => HTMLElement | null;
  // Optional escape hatch so the parent can focus the dialog itself when a
  // phase offers no primary action (the element carries tabIndex={-1}, so it
  // is programmatically focusable but never joins the Tab trap below).
  dialogRef?: RefObject<HTMLDialogElement | null>;
  // Presentation only: native top-layer ownership and the default centered
  // consumers remain unchanged. The touch rectangle may itself be rotated.
  placement?: "touch-workspace";
  children: ReactNode;
}

function focusableElements(dialog: HTMLDialogElement): HTMLElement[] {
  return Array.from(dialog.querySelectorAll<HTMLElement>(
    'button:not([disabled]), input:not([disabled]), [href], [tabindex]:not([tabindex="-1"])',
  ));
}

function validFocusTarget(element: HTMLElement | null): element is HTMLElement {
  return element !== null && element.isConnected && element.tabIndex >= 0 &&
    !element.matches(":disabled") &&
    element.closest('[inert], [aria-hidden="true"]') === null;
}

function restoreModalFocus(returnFocus: HTMLElement | null): void {
  if (validFocusTarget(returnFocus)) {
    returnFocus.focus();
    return;
  }
  const fallback = Array.from(document.querySelectorAll<HTMLElement>(
    'button:not([disabled]), input:not([disabled]), [href], [tabindex]:not([tabindex="-1"])',
  )).find((element) => validFocusTarget(element) &&
    element.closest(".sample-modal-backdrop") === null);
  fallback?.focus();
}

// The proven modal machinery behind ConfirmationDialog, generalized so other
// modal surfaces (the Pad Capture panel) reuse the exact same behaviour:
// inert + aria-hidden background walk, non-dismissible backdrop, focus on
// open, Tab trap, Escape -> onCancel, and the returnFocus restore contract.
export function ModalDialog({
  returnFocus,
  onCancel,
  dialogClassName,
  labelledBy,
  label,
  resolveInitialFocus,
  dialogRef: externalDialogRef,
  placement,
  children,
}: ModalDialogProps) {
  const dialogRef = useRef<HTMLDialogElement | null>(null);
  const cancelRef = useRef(onCancel);
  cancelRef.current = onCancel;
  const initialFocusRef = useRef(resolveInitialFocus);
  initialFocusRef.current = resolveInitialFocus;

  useLayoutEffect(() => {
    const dialog = dialogRef.current;
    if (placement !== "touch-workspace" || dialog === null) return;
    const anchor = dialog.closest<HTMLElement>('[data-testid="touch-workspace"]');
    if (anchor === null) return;
    const workspace = anchor.closest<HTMLElement>(".hardware-workspace");
    const previousStyle = dialog.style.cssText;
    const update = () => {
      const rect = anchor.getBoundingClientRect();
      if (rect.width <= 0 || rect.height <= 0 || anchor.offsetWidth <= 0 || anchor.offsetHeight <= 0) return;
      const viewportWidth = document.documentElement.clientWidth || window.innerWidth;
      const viewportHeight = document.documentElement.clientHeight || window.innerHeight;
      const availableWidth = Math.max(1, viewportWidth - 16);
      const availableHeight = Math.max(1, viewportHeight - 16);
      // Preserve upright clientX trim gestures in a rotated console. Native
      // dialogs escape ancestor transforms, so only reproduce its scale.
      // Smaller available space reflows/scrolls instead of shrinking 44px hits.
      const width = Math.min(anchor.offsetWidth, availableWidth);
      const height = Math.min(anchor.offsetHeight, availableHeight);
      const scale = Math.max(1, Math.min(rect.width / anchor.offsetWidth,
        rect.height / anchor.offsetHeight, availableWidth / width, availableHeight / height));
      Object.assign(dialog.style, {
        position: "fixed",
        left: `${Math.max(8, Math.min(rect.left, viewportWidth - width * scale - 8))}px`,
        top: `${Math.max(8, Math.min(rect.top, viewportHeight - height * scale - 8))}px`,
        right: "auto", bottom: "auto", margin: "0",
        width: `${width}px`, height: `${height}px`,
        maxWidth: "none", maxHeight: "none",
        transform: `scale(${scale})`, transformOrigin: "0 0",
      });
    };
    update();
    window.addEventListener("resize", update);
    window.addEventListener("scroll", update, true);
    const resize = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(update);
    resize?.observe(anchor);
    if (workspace !== null) resize?.observe(workspace);
    // Stage fitting writes the transform after React's commit, without always
    // changing the anchor's natural size. Observe that exact owner only.
    const transform = workspace === null ? null : new MutationObserver(update);
    if (workspace !== null) transform?.observe(workspace, {attributes: true, attributeFilter: ["style"]});
    return () => {
      window.removeEventListener("resize", update);
      window.removeEventListener("scroll", update, true);
      resize?.disconnect();
      transform?.disconnect();
      dialog.style.cssText = previousStyle;
    };
  }, [placement]);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (dialog === null) return;
    const contained: ContainedBackground[] = [];
    let branch: HTMLElement = dialog;
    let parent = branch.parentElement;
    while (parent !== null && parent !== document.body) {
      for (const sibling of parent.children) {
        if (sibling === branch || !(sibling instanceof HTMLElement)) continue;
        contained.push({
          element: sibling,
          hadInert: sibling.hasAttribute("inert"),
          ariaHidden: sibling.getAttribute("aria-hidden"),
        });
        sibling.setAttribute("inert", "");
        sibling.setAttribute("aria-hidden", "true");
      }
      branch = parent;
      parent = parent.parentElement;
    }

    if (typeof dialog.showModal === "function") {
      if (dialog.open && typeof dialog.close === "function") dialog.close();
      dialog.showModal();
    }
    (initialFocusRef.current?.(dialog) ?? focusableElements(dialog)[0])?.focus();

    return () => {
      for (const {element, hadInert, ariaHidden} of contained) {
        if (!hadInert) element.removeAttribute("inert");
        if (ariaHidden === null) element.removeAttribute("aria-hidden");
        else element.setAttribute("aria-hidden", ariaHidden);
      }
      restoreModalFocus(returnFocus);
    };
  }, [returnFocus]);

  return (
    <div
      className="sample-modal-backdrop"
      onPointerDown={(event) => {
        // The backdrop is never a dismiss control: a modal session (a Reset
        // confirmation, an in-progress recording) must not be closable by a
        // misclick outside the dialog.
        if (event.target === event.currentTarget) event.preventDefault();
      }}
    >
      <dialog
        ref={(element) => {
          dialogRef.current = element;
          if (externalDialogRef !== undefined) {
            externalDialogRef.current = element;
          }
        }}
        open
        tabIndex={-1}
        className={dialogClassName}
        aria-labelledby={labelledBy}
        aria-label={label}
        aria-modal="true"
        onCancel={(event) => {
          event.preventDefault();
          cancelRef.current();
        }}
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            event.preventDefault();
            event.stopPropagation();
            cancelRef.current();
            return;
          }
          if (event.key !== "Tab") return;
          const focusable = focusableElements(event.currentTarget);
          if (focusable.length === 0) {
            event.preventDefault();
            return;
          }
          const first = focusable[0]!;
          const last = focusable.at(-1)!;
          if ((event.shiftKey && document.activeElement === first) ||
            (!event.shiftKey && document.activeElement === last) ||
            !event.currentTarget.contains(document.activeElement)) {
            event.preventDefault();
            (event.shiftKey ? last : first).focus();
          }
        }}
      >
        {children}
      </dialog>
    </div>
  );
}
