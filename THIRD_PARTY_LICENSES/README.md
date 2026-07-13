# Third-party components

The WebReader desktop build redistributes the following third-party software.
WebReader itself is MIT licensed.

## Tesseract OCR

- Project: https://github.com/tesseract-ocr/tesseract
- License: Apache License 2.0 (see `tesseract-LICENSE.txt`, added at build time)
- Bundled unmodified, including English language data (`tessdata`), for the
  built-in OCR feature. Copyright the Tesseract authors; originally developed
  at Hewlett-Packard and Google.

Apache 2.0 redistribution conditions satisfied here:
1. A copy of the license accompanies the distribution (this folder ships
   inside the release zip next to the executable).
2. Copyright and attribution notices are retained (this file plus the
   license texts).
3. No modifications were made to Tesseract; no NOTICE-file obligations beyond
   the license text apply.
4. The Tesseract name is used only to describe the bundled component, not to
   imply endorsement.

## Leptonica

- Project: http://www.leptonica.org/
- License: Leptonica License (BSD 2-clause style; see
  `leptonica-license.txt`, added at build time)
- Bundled as a Tesseract dependency (image processing library).

## Other Tesseract build dependencies

The Windows Tesseract build includes permissively licensed libraries
(libpng, libjpeg, libtiff, zlib, openjpeg, and others). Their license texts,
as shipped with the upstream Tesseract Windows distribution, are copied into
this folder at build time when available.
