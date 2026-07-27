# Sound role icons — Ordered Signals V5

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

The V5 asset set treats each sound role as a responsive geometric mark
rather than an instrument illustration or character silhouette. Circles,
arches, waves, radial systems, modular grids, and nested frames create an
original signal vocabulary informed by Swiss identity systems and Y2K
geometry.

All icons use a native 256×256 view box and one `currentColor`. Transparent
negative space is allowed, but no second printed color is embedded in an icon.
`icons.svg` provides the same artwork as reusable 256×256 symbols. A and B
slots reuse the same role mark; the UI owns the variant badge, playback state,
and accessible text.

The construction system maps a 32-unit logical grid onto the 256×256 canvas at
8× scale. Its 4-unit base interval becomes 32px and its optical 2-unit primary
stroke becomes 16px. Every mark has a declared order: bilateral symmetry,
four-fold rotation, radial repetition, horizontal reflection, or diagonal
progression. Repeated units use equal spacing and equal angles.

Use role marks at 16–24px in the Pattern sidebar. On Pads they may scale to
72–112px as a low-opacity background texture. Do not encode playback state or
material quality inside the role mark.
