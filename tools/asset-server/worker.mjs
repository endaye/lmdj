const CORS = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
  "Access-Control-Expose-Headers": "ETag, Content-Length", "X-Content-Type-Options": "nosniff"};
function reply(status, message, extra = {}) {
  return new Response(message, {status, headers: {...CORS, "Cache-Control": "no-store", ...extra}});
}
export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method === "OPTIONS") return reply(204, null);
    if (!["GET", "HEAD"].includes(request.method)) return reply(405, "Method not allowed", {Allow: "GET, HEAD, OPTIONS"});
    if (url.search !== "") return reply(400, "Query not supported");
    if (url.pathname === "/health") return reply(200, request.method === "HEAD" ? null : '{"service":"lmdj-default-assets","ok":true}', {"Content-Type": "application/json"});
    const catalog = url.pathname === "/catalog/index.json";
    const match = /^\/object\/(manifest|blob)\/([0-9a-f]{64})$/.exec(url.pathname);
    if (!catalog && match === null) return reply(404, "Not found");
    const target = new URL(request.url);
    target.pathname = catalog ? "/catalog/index.json" : `/${match[1]}/${match[2]}`;
    let response;
    try {response = await env.ASSETS.fetch(new Request(target, {method: request.method}));}
    catch {return reply(502, "Asset unavailable");}
    if (response.status !== 200) return reply(response.status === 404 ? 404 : 502, "Asset unavailable");
    const headers = new Headers(response.headers);
    for (const [key, value] of Object.entries(CORS)) headers.set(key, value);
    headers.set("Content-Type", catalog || match[1] === "manifest" ? "application/json" : "audio/wav");
    headers.set("Cache-Control", catalog ? "public, max-age=60, must-revalidate" : "public, max-age=31536000, immutable");
    if (!catalog) headers.set("ETag", `"${match[2]}"`);
    return new Response(request.method === "HEAD" ? null : response.body, {status: 200, headers});
  },
};
