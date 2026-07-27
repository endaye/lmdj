# Sound role icons — Sound Specimens V2

This directory contains the canonical monochrome marks for LMDJ's eight
material roles:

| Role | Icon | Family |
|---|---|---|
| Kick | `kick.svg` | drums |
| Snare | `snare.svg` | drums |
| Hat | `hat.svg` | drums |
| Percussion | `percussion.svg` | drums |
| Bass | `bass.svg` | bass |
| Melody | `melody.svg` | harmony |
| Vocal | `vocal.svg` | lead |
| Phrase | `phrase.svg` | loop |

The V2 visual language treats each sound role as an abstract exhibition
specimen rather than a literal instrument illustration. Thick silhouettes,
paper-colored cuts, asymmetric Y2K geometry, and controlled “energy cores”
combine character appeal with a disciplined Swiss grid.

All icons use a 32×32 view box, `currentColor`, and the project paper color
`#F6F2E8` for printed counter-shapes. `icons.svg` provides the same artwork as
reusable symbols. A and B slots reuse the same role mark; the UI owns the
variant badge, playback state, and accessible text.

Use role marks at 16–24px in the Pattern sidebar. On Pads they may scale to
72–112px as a low-opacity background texture. Do not encode playback state or
material quality inside the role mark.
