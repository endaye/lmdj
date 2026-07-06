# ASCII Matrix Camera

Reference visual prototype for the LMDJ interaction style. This demo lives under `references/demos/` and is not part of the formal product source boundary.

The screen is a black/green ASCII matrix surface. The idle state renders a cat image as ASCII characters over a falling-character background. Pressing `CAM` requests webcam access and switches the central subject to a live ASCII camera feed.

This prototype is useful visual evidence for later LMDJ web experiments, but it does not define the final UI architecture.

## Visual Rules

- Background is black.
- ASCII characters are green only.
- The subject is built from ASCII characters, with no filled character-cell background.
- Brightness and detail are expressed through character choice and opacity.
- The background remains a falling ASCII waterfall.
- The camera feed is mirrored and scaled with preserved aspect ratio.

## Interaction

Open `index.html` directly in a browser, or serve this folder locally:

```bash
python3 -m http.server 4173
```

Then visit `http://localhost:4173`.

The `CAM` button triggers `navigator.mediaDevices.getUserMedia`. If camera permission is unavailable or denied, the page stays on the cat fallback.
