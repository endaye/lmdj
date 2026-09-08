// Preserve the Host contract: both / and /index.html serve identical bytes.
// Other paths go directly to static assets without invoking this Worker.
export default {
  fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/") url.pathname = "/index.html";
    return env.ASSETS.fetch(new Request(url, request));
  },
};
