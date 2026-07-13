# Third-party components

The WebReader desktop build redistributes the following third-party software.
WebReader itself is MIT licensed (see the repository root `LICENSE`).

## Tesseract OCR

- Project: https://github.com/tesseract-ocr/tesseract
- License: Apache License 2.0 — full text in
  `tesseract-LICENSE-Apache-2.0.txt` (in this folder)
- Bundled unmodified, including English language data (`tessdata`), to power
  the built-in OCR feature. Copyright the Tesseract authors; originally
  developed at Hewlett-Packard and Google.

How the Apache 2.0 redistribution conditions are satisfied:

1. **Include the license**: the full license text ships in this folder, which
   is distributed inside the release zip next to the executable.
2. **Retain notices**: attribution is kept in this file and in the license
   texts; any license/notice files shipped with the upstream Windows
   distribution are copied here at build time (`tesseract-dist-*`).
3. **State changes**: Tesseract is bundled unmodified, so no change
   statements are required.
4. **Trademarks**: the Tesseract name is used only to identify the bundled
   component, not to imply endorsement.

## Leptonica

- Project: http://www.leptonica.org/
- License: Leptonica License (BSD 2-clause style) — `leptonica-license.txt`
  is downloaded from the upstream repository at build time and included in
  the release zip.
- Bundled as a Tesseract dependency (image processing library).

## Other Tesseract build dependencies

The Windows Tesseract build links permissively licensed libraries (libpng,
libjpeg, libtiff, zlib, openjpeg, and others). Their license texts, as
shipped with the upstream Tesseract Windows distribution, are copied into
this folder at build time when available.
