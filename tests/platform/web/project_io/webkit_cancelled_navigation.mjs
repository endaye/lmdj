// WebKit r2361 on Linux sometimes cancels the provisional new-process load of
// a fresh page's COOP navigation (#1570). With the client patch in
// toolchain/playwright_webkit_abort_patch.mjs, `goto` rejects with the
// engine's cancellation instead of waiting out the test timeout. The document
// never committed, so no page script ran and no Project I/O step began: one
// fresh attempt repeats the same journey step. Any other failure, a page that
// already holds a document, another engine, or a second cancellation fails.
export const ENGINE_CANCELLED_LOAD = "Load request cancelled; maybe frame was detached?";

export function isEngineCancelledFirstLoad(page, error, browserName) {
  return browserName === "webkit" && !page.isClosed() && page.url() === "about:blank" &&
    String(error?.message ?? "").includes(ENGINE_CANCELLED_LOAD);
}

export async function gotoRetryingCancelledFirstLoad(page, url, options, {browserName, onRetry}) {
  try {
    return await page.goto(url, options);
  } catch (error) {
    if (!isEngineCancelledFirstLoad(page, error, browserName)) throw error;
    onRetry(error);
    return await page.goto(url, options);
  }
}
