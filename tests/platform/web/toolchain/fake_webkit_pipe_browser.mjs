#!/usr/bin/env node
import {createReadStream, createWriteStream} from "node:fs";

// A minimal browser on Playwright's WebKit inspector pipe (fd 3 in, fd 4 out,
// NUL-delimited JSON). It creates one page and answers every navigation with
// the COOP process-swap exchange retained from batch run 36320748849 (#1570):
// the provisional new-process target is created, its load is cancelled, and
// it is destroyed. FAKE_WEBKIT_ORDER=early delivers the old process's document
// request after that failure, as recorded; `late` delivers it before; `none`
// never delivers it.
const order = ["late", "none"].includes(process.env.FAKE_WEBKIT_ORDER) ? process.env.FAKE_WEBKIT_ORDER : "early";
const output = createWriteStream(null, {fd: 4});
const send = message => output.write(`${JSON.stringify(message)}\0`);
const destroyedTargets = new Set();
let pages = 0;

const fromTarget = (pageProxyId, targetId, message) => send({method: "Target.dispatchMessageFromTarget",
  pageProxyId, params: {targetId, message: JSON.stringify(message)}});

function navigate({id, params: {pageProxyId, frameId, url}}) {
  const loaderId = "82";
  const documentRequest = () => fromTarget(pageProxyId, "old", {method: "Network.requestWillBeSent",
    params: {requestId: "17.12", frameId, loaderId, documentURL: url, type: "Document", timestamp: 1,
      request: {url, method: "GET", headers: {}}, initiator: {type: "other"}}});
  fromTarget(pageProxyId, "old", {method: "Page.willCheckNavigationPolicy", params: {frameId}});
  send({id, result: {loaderId}});
  fromTarget(pageProxyId, "old", {method: "Page.didCheckNavigationPolicy", params: {frameId, cancel: false}});
  if (order === "late") documentRequest();
  send({method: "Target.targetCreated", pageProxyId,
    params: {targetInfo: {targetId: "provisional", type: "page", isProvisional: true}}});
  send({method: "Playwright.provisionalLoadFailed",
    params: {pageProxyId, loaderId, error: "Load request cancelled"}});
  destroyedTargets.add("provisional");
  send({method: "Target.targetDestroyed", pageProxyId, params: {targetId: "provisional", crashed: false}});
  if (order === "early") documentRequest();
}

function handle(message) {
  const {id, method, params, pageProxyId} = message;
  if (method === "Target.sendMessageToTarget") {
    if (destroyedTargets.has(params.targetId)) {
      send({id, pageProxyId, error: {message: "Target not found"}});
      return;
    }
    const inner = JSON.parse(params.message);
    send({id, pageProxyId, result: {}});
    const result = inner.method !== "Page.getResourceTree" ? {} : {frameTree: {resources: [],
      frame: {id: "main", loaderId: "initial", url: "about:blank", securityOrigin: "://", mimeType: "text/html"}}};
    fromTarget(pageProxyId, params.targetId, {id: inner.id, result});
  } else if (method === "Playwright.createPage") {
    const created = String(++pages);
    send({method: "Playwright.pageProxyCreated",
      params: {pageProxyId: created, browserContextId: params.browserContextId}});
    send({method: "Target.targetCreated", pageProxyId: created,
      params: {targetInfo: {targetId: "old", type: "page", isProvisional: false}}});
    send({id, result: {pageProxyId: created}});
  } else if (method === "Playwright.navigate") {
    navigate(message);
  } else if (method === "Playwright.close") {
    output.end(() => process.exit(0));
  } else {
    const result = method === "Playwright.createContext" ? {browserContextId: "context"} : {};
    send({id, ...(pageProxyId ? {pageProxyId} : {}), result});
  }
}

let buffered = "";
createReadStream(null, {fd: 3}).on("data", chunk => {
  buffered += chunk;
  for (let end = buffered.indexOf("\0"); end >= 0; end = buffered.indexOf("\0")) {
    handle(JSON.parse(buffered.slice(0, end)));
    buffered = buffered.slice(end + 1);
  }
}).on("end", () => process.exit(0));
