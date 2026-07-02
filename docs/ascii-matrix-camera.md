# ASCII Matrix Camera Prototype

`ascii-matrix-camera/` is the current validated visual prototype for LMDJ web interaction.

## Confirmed Direction

- Use a black background with green ASCII characters.
- Use falling ASCII rain as the ambient system state.
- Build the central subject from characters only; do not fill character-cell backgrounds.
- Keep character color green; use character density, glyph choice, and opacity for image detail.
- Use a single `CAM` control to request camera access.
- When camera access is active, render the live camera feed as centered ASCII while preserving aspect ratio.
- When camera access is unavailable, fall back to the cat ASCII image.

## Run

```bash
cd ascii-matrix-camera
python3 -m http.server 4173
```

Then open `http://localhost:4173`.

## Notes

The prototype is intentionally static and dependency-free. Camera support depends on browser and OS permission state.
