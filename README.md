# EmbeddedFonts

This repository contains CSS files with fonts embedded as base64-encoded
data URIs in WOFF format. The embedded fonts contain data for only the
Basic Latin and Latin-1 Supplement Unicode blocks.

The CSS files are split into 'single' and 'combined', containing
respectively a single font face or the entirety of the family.

The font face definitions in the CSS specify weight, style, and
stretch, as specified in the .woff files.

# embedder.py

A small script to generate an embedded font from a .woff file. Uses only
the standard library.

# Licenses

Not all of these fonts use the same license, and as such the specific
license for each can be found in their respective directories or CSS
files. All of the included fonts permit redistribution.
