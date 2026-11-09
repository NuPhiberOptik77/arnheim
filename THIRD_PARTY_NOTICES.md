# Third-party notices

Arnheim builds on three projects and uses four free photo sets. Their licences are below, as they
came.

## House Control

`src/three/kit.js` and `src/three/furniture.js` are House Control's modelling kit and furniture
library, changed lightly (a per-room lamp, decals, merging). `src/building.js` and
`src/three/rooms.js` adapt its lighting, cut-away walls, camera rig and render-on-demand loop.
House Control is at https://github.com/0xProbabillity/house-control.

MIT License

Copyright (c) 2026 0xProbability

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## Three.js

`vendor/three/three.module.js` and `vendor/three/three.core.js` are Three.js 0.186.1, copied
unchanged. `vendor/three/addons/` holds its postprocessing, RoundedBoxGeometry and
BufferGeometryUtils add-ons from the same version, changed only so their `three` imports are
relative paths to the vendored file. Their licence is `vendor/three/LICENSE`, also MIT, copyright
the three.js authors.

## Lucide

`src/icons.js` holds icon shapes copied from Lucide 0.544.0 (from House Control's `web/node_modules/lucide`), wrapped in a small function.

```
ISC License

Copyright (c) for portions of Lucide are held by Cole Bemis 2013-2023 as part of Feather (MIT). All other copyright (c) for Lucide are held by Lucide Contributors 2025.

Permission to use, copy, modify, and/or distribute this software for any
purpose with or without fee is hereby granted, provided that the above
copyright notice and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.

---

The MIT License (MIT) (for portions derived from Feather)

Copyright (c) 2013-2023 Cole Bemis

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Kokoro, Whisper and their helpers (the voice and the ear, not in this repository)

The walk's voice (`voice/`, `src/voice.js`) runs Kokoro, an open text-to-speech model, and listens
with Whisper, an open speech recognition model, on the computer that serves the page. None of it
is copied here: whoever turns the voice on installs the Python packages and fetches the models,
under their own licences.

- The model and voices, `hexgrad/Kokoro-82M` on Hugging Face: Apache License 2.0.
- The `kokoro` and `misaki` Python packages, which run it and turn words into sounds: Apache
  License 2.0.
- Whisper, the `openai-whisper` Python package and its `base.en` model, by OpenAI: MIT License.
- PyTorch, which runs both models: BSD 3-Clause License.
- espeak-ng, which `misaki` uses for words it doesn't know, through `espeakng-loader`: GNU General
  Public License, version 3. It runs as a separate library on that computer and is not part of
  Arnheim.

## Poly Haven

`vendor/polyhaven/` holds files from four Poly Haven assets, unchanged, at 1K: the light probe
`entrance_hall_1k.hdr`; the surface (OpenGL normal) and roughness pictures of `terrazzo_tiles`,
`white_oak_veneer` and `white_plaster_02`; and the colour pictures of the first two. Walk mode
loads them only once someone starts walking (`src/three/photo.js`).

They are CC0 1.0 (https://creativecommons.org/publicdomain/zero/1.0/): their authors gave them to
the public domain, so they may be used for anything, with no credit needed. Arnheim credits them
anyway. Each asset's page names its author, and Poly Haven's licence page is
https://polyhaven.com/license.

- https://polyhaven.com/a/entrance_hall
- https://polyhaven.com/a/terrazzo_tiles
- https://polyhaven.com/a/white_oak_veneer
- https://polyhaven.com/a/white_plaster_02
