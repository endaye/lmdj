# P1 default asset live origin admission

Independent review of T3 source 518d873bb09f6448fefbf79e41f5a389104211fd reproduced a real readiness false positive (R13): the declared HTTPS asset origin redirected every object and health response to a different HTTPS authority; urllib followed it and reported authenticated bytes at the original origin. The actual Creator production proxy refused the same origin with HTTP 502 because it uses manual redirects and requires HTTP 200. This evidence does not assert that the deployed service currently redirects.

Use a redirect-refusing urllib opener for both object and health GETs, explicitly require HTTP 200, close refused responses, and explain the direct-origin remedy. Preserve byte, CORS, cache, rights, corpus and regeneration checks.

## Declared files

- `tools/asset-server/kit_test.py`
- `tools/asset-server/live_test.py`
- `scripts/asset-server.sh`
- `docs/operations/default-assets.md`
- `docs/plans/2026-10-02-creator-p1-assets-live-origin.md`

## Task verification

Run `scripts/asset-server.sh check` including real loopback urllib tests for direct HTTP 200, object redirect refusal without mirror access, health redirect refusal without mirror access, and refusal of another successful HTTP status. Run the staged change-scope ownership suite. Ask the independent reviewer to rerun the unchanged real HTTPS origin/mirror reproduction against the committed source in a fresh process. These checks catch false admission of a redirecting origin and ensure both live paths retain direct-origin checks.

Loopback unit tests exercise HTTP admission; the independent reproduction adds trusted localhost TLS and the actual Creator proxy. Neither proves deployment or physical browser playback. Current complete lane receipts remain bound to their actual source keys; rederive all keys after commit and rerun changed inputs.

## Version Management

Version impact: none. This fixes deployment verification without changing assets, product runtime or contract identity.

Documentation impact: none
Reason: update the standalone service operations procedure; no portal route, diagram, identity or documented product source fact changes.
