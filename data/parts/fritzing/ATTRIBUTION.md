# Fritzing part artwork

Artwork by Fritzing and the fritzing-parts contributors; PIR module artwork by
John De Cristofaro (as credited in the upstream part definition).
Source: https://github.com/fritzing/fritzing-parts
Pinned revision and individual source paths: [manifest.json](manifest.json).

These SVGs, their PNG rasterisations, colour variants and diagrams incorporating
them are licensed under **Creative Commons Attribution-ShareAlike 3.0 Unported**:
https://creativecommons.org/licenses/by-sa/3.0/
The original upstream notice is in [LICENSE.txt](LICENSE.txt).
This artwork licence does not change the licence of unrelated application code.

Changes: SVG rasterisation, LED colour variants, and resistor bands recoloured
orange/orange/brown (330Ω). Illustrations help identify the package; use the
lesson's terminal names and your actual component markings when wiring. The
four-lead RGB illustration is a package reference, not a pinout for a different
common-leg variant. The USB illustration is a connector, not a webcam.

Rebuild using `python3 tools/vendor_fritzing.py /path/to/fritzing-parts` (Inkscape
needed only by developers). All graphics are bundled: no downloads at runtime.
