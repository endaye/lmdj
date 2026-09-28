// WebKit r2361 on Linux sometimes cancels the provisional new-process load of
// a fresh page's COOP navigation (#1570). With the client patch in
// toolchain/playwright_webkit_abort_patch.mjs, `goto` rejects with the
// engine's cancellation instead of waiting out the test timeout. Only a page's
// first navigation through here, still at its initial about:blank, is repeated:
// no document ever committed, so no page script ran and no Project I/O step
// began. Any other failure, a page this helper already navigated (even one back
// at about:blank), another engine, or a second cancellation fails.
//
// The engine is read from the page itself. A caller-supplied project name is
// not the engine: `devices["Desktop Safari"]` sets `defaultBrowserType`, not
// `browserName`, so `test.info().project.use.browserName` is undefined for the
// WebKit project and a guard on it never matched a real run.
export const ENGINE_CANCELLED_LOAD = "Load request cancelled; maybe frame was detached?";

const navigatedPages = new WeakSet();

// A page with no Browser (a persistent context) has no known engine and is
// never retried.
export function pageEngine(page) {
  return page.context().browser()?.browserType().name();
}

export function isEngineCancelledFirstLoad(page, error) {
  return pageEngine(page) === "webkit" && !page.isClosed() && page.url() === "about:blank" &&
    String(error?.message ?? "").includes(ENGINE_CANCELLED_LOAD);
}

export async function gotoRetryingCancelledFirstLoad(page, url, options, {onRetry}) {
  const firstNavigation = !navigatedPages.has(page);
  navigatedPages.add(page);
  try {
    return await page.goto(url, options);
  } catch (error) {
    if (!firstNavigation || !isEngineCancelledFirstLoad(page, error)) throw error;
    onRetry(error);
    return await page.goto(url, options);
  }
}
