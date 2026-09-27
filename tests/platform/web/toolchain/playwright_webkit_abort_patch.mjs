import {readFile, writeFile} from "node:fs/promises";
import {dirname, join, resolve} from "node:path";
import {fileURLToPath, pathToFileURL} from "node:url";

// Playwright 1.62.1 drops a WebKit provisional-load failure that arrives
// before the document request it belongs to (#1570). WebKit r2361 on Linux
// sometimes cancels the provisional new-process load of a fresh page's COOP
// navigation, and its UI-process `Playwright.provisionalLoadFailed` can reach
// the client before the old process's `Network.requestWillBeSent`. At that
// moment the main frame has no pending document, so `frameAbortedNavigation`
// returns early and `page.goto` waits for a commit that never comes.
//
// This edit remembers such an early failure and replays it when the matching
// document request starts, so `goto` rejects with the engine's own error. It
// is bound to the exact locked client bundle and fails closed on any other.
export const PLAYWRIGHT_VERSION = "1.62.1";

const EDITS = [
  {
    name: "defer an early provisional-load failure",
    original: `          errorText += "; maybe frame was detached?";
        this._page.frameManager.frameAbortedNavigation(this._page.mainFrame()._id, errorText, event.loaderId);
      }
      handleWindowOpen(event) {`,
    patched: `          errorText += "; maybe frame was detached?";
        const lmdjPendingDocument = this._page.mainFrame().pendingDocument();
        if (event.loaderId && lmdjPendingDocument?.documentId !== event.loaderId) {
          // LMDJ #1570: replay once the document request for this loader starts.
          this._lmdjEarlyProvisionalLoadFailure = { loaderId: event.loaderId, errorText };
          return;
        }
        this._page.frameManager.frameAbortedNavigation(this._page.mainFrame()._id, errorText, event.loaderId);
      }
      handleWindowOpen(event) {`,
  },
  {
    name: "replay it at the document request",
    original: `        const request2 = new WKInterceptableRequest(session2, frame, event, redirectedFrom, documentId);
        let route2;
        if (intercepted) {
          route2 = new WKRouteImpl(session2, event.requestId);
          request2.request.setRawRequestHeaders(null);
        }
        this._requestIdToRequest.set(event.requestId, request2);
        this._page.frameManager.requestStarted(request2.request, route2);
      }`,
    patched: `        const request2 = new WKInterceptableRequest(session2, frame, event, redirectedFrom, documentId);
        let route2;
        if (intercepted) {
          route2 = new WKRouteImpl(session2, event.requestId);
          request2.request.setRawRequestHeaders(null);
        }
        this._requestIdToRequest.set(event.requestId, request2);
        this._page.frameManager.requestStarted(request2.request, route2);
        const lmdjEarlyFailure = this._lmdjEarlyProvisionalLoadFailure;
        if (lmdjEarlyFailure && isNavigationRequest && frame === this._page.mainFrame() &&
            documentId === lmdjEarlyFailure.loaderId) {
          this._lmdjEarlyProvisionalLoadFailure = void 0;
          this._page.frameManager.frameAbortedNavigation(frame._id, lmdjEarlyFailure.errorText, lmdjEarlyFailure.loaderId);
        }
      }`,
  },
];

// Neither text may contain the other, so each state is counted unambiguously.
const occurrences = (source, text) => source.split(text).length - 1;

function editState(source, edit) {
  const original = occurrences(source, edit.original);
  const patched = occurrences(source, edit.patched);
  if (original === 1 && patched === 0) return "original";
  if (original === 0 && patched === 1) return "patched";
  throw new Error(`why: the Playwright ${PLAYWRIGHT_VERSION} WebKit client does not contain exactly one ` +
    `"${edit.name}" site (original ${original}, patched ${patched}); remedy: reinstall the locked ` +
    "client with `npm --prefix tests/platform/web ci`, or re-derive this patch for the new client");
}

export function isPatched(source) {
  return EDITS.every(edit => editState(source, edit) === "patched");
}

export function patchBundle(source) {
  return EDITS.reduce((text, edit) =>
    editState(text, edit) === "original" ? text.replace(edit.original, () => edit.patched) : text, source);
}

export function unpatchBundle(source) {
  return EDITS.reduce((text, edit) =>
    editState(text, edit) === "patched" ? text.replace(edit.patched, () => edit.original) : text, source);
}

export async function clientBundle(webRoot) {
  const packageRoot = join(webRoot, "node_modules", "playwright-core");
  const {version} = JSON.parse(await readFile(join(packageRoot, "package.json"), "utf8"));
  if (version !== PLAYWRIGHT_VERSION) {
    throw new Error(`why: the WebKit early-abort patch is bound to Playwright ${PLAYWRIGHT_VERSION}, ` +
      `found ${version}; remedy: reinstall the locked client, or re-derive this patch for ${version}`);
  }
  return join(packageRoot, "lib", "coreBundle.js");
}

if (process.argv[1] && pathToFileURL(resolve(process.argv[1])).href === import.meta.url) {
  const mode = process.argv[2];
  const webRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
  try {
    if (mode !== "apply" && mode !== "check") {
      throw new Error("why: no mode was given; remedy: pass apply (npm postinstall) or check (proof)");
    }
    const bundle = await clientBundle(webRoot);
    const source = await readFile(bundle, "utf8");
    if (mode === "apply") {
      const patched = patchBundle(source);
      if (patched !== source) await writeFile(bundle, patched);
    } else if (!isPatched(source)) {
      throw new Error("why: the installed Playwright client still drops early WebKit provisional-load " +
        "failures (#1570); remedy: run `npm --prefix tests/platform/web ci`");
    }
  } catch (error) {
    console.error(`playwright webkit abort patch error: ${error.message}`);
    process.exitCode = 2;
  }
}
