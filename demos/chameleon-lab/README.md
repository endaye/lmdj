# Chameleon Lab

Chameleon Lab is a product-neutral generative-art web experiment: a single-page
site that draws a living-looking chameleon from pure mathematics. It is an
original, code-only homage inspired by the concept of generative creature sites
(such as kumaleon.com) — every pixel, curve, palette, and line of copy here is
original to this repository. No assets, text, or code were copied from any
existing site.

Like `web-runtime-lab`, this app is an experimental static lab. It does not use
Product Assembly or the Application Facade, and it does not change Core
behavior.

## What it does

- A full-viewport canvas renders a procedural chameleon: spiral tail, dorsal
  spikes, head casque, three-toed feet, and a seeded skin pattern (`spots`,
  `stripes`, or `mesh`).
- Every creature is a pure function of its seed (`src/rng.js`,
  `src/palette.js`, `src/chameleon.js` are deterministic and Node-testable).
- Four trait icons re-roll the palette, the skin pattern, the seed, and the
  motion speed — "click icons to change". The Hatch section rolls a brand-new
  creature.
- The eye tracks, blinks, and the body breathes; `prefers-reduced-motion`
  renders a single static frame instead.
- An overlay menu links to Theory / About / Artist / Playground / History /
  Hatch sections, in the spirit of a generative-art landing page.

## Local operation

Run the test gate from the repository root:

```bash
scripts/chameleon-lab.sh test
```

Start the loopback-only server:

```bash
scripts/chameleon-lab.sh serve --port 4175
```

or, from `demos/chameleon-lab`:

```bash
npm run dev
```

Then open <http://127.0.0.1:4175>. The server sets COOP, COEP, CORP, and
`no-store` headers, refuses non-loopback binding without TLS, and exposes a
`/health.json` probe.

## Tests

- `npm test` runs the Node test suite over the deterministic generative engine
  (`test/generative.test.mjs`).
- `python3 test/server_test.py` boots the server on an ephemeral port and
  checks the health probe, isolation headers, static file serving, and path
  traversal containment.
