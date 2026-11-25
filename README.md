# The world in one day — 24 November 2026

A single 1024 × 1024 newspaper image for `news-image-20261124`. A dominant date masthead and one-line day summary introduce forty numbered reports in three columns, grouped under UKRAINE, IRAN, WAR, MARKETS, ASIA, AFRICA, EU, AMERICAS, and SCIENCE. Every card contains a UTC time, source tag, one-line headline, and a small detail line.

The editorial input is the forty stories, timestamps, source labels, and day summary supplied in the build brief. Headlines are shortened for the image; each card's `data-full-headline` attribute preserves its supplied headline. The briefing item without a named outlet uses its supplied title, “Morning Briefing,” as its source label. Topic order groups related reports; the original story numbers and UTC times preserve their identity.

The exact footer is: **40 stories. One day. 24 November 2026.**

To rebuild the image:

```sh
python3 render.py
```

The renderer first tries an installed headless Chromium, then Playwright's Chromium, then a Pillow compositor. The browser path audits the actual DOM at 1024 × 1024 before accepting it: all forty cards, every one-line headline and detail, the summary, canvas boundaries, scrolling, and overlapping cards are checked. The Pillow fallback reads the same HTML copy, measures text, and composes all forty cards. The page uses inline CSS and system fonts, with no external assets.

Rendering needs a working Chromium or the optional Python `playwright` or `Pillow` package. No packages are installed and no network access is needed during rendering. Alternate paths can be exercised explicitly:

```sh
python3 render.py --backend playwright --output /tmp/playwright-entry.png
python3 render.py --backend pil --output /tmp/pil-entry.png
```

Every render checks the PNG dimensions, the 1 MiB limit, chunk checksums, complete scanlines, and end marker. It prints the selected backend, layout report, byte count, and SHA-256 digest.

The competition entrypoint is the root `main.ts`, with engine `node22`. It uses only Node's standard library to copy the committed `entry.png` into `$MAKEFUN_OUTPUT_DIR/entry.png`, defaulting to `/output/entry.png`. Run it with Node 22.18 or later:

```sh
MAKEFUN_OUTPUT_DIR=/tmp/news-image-output node main.ts
```

The committed image is the runtime artifact, so the sandbox needs no browser, Python packages, fonts, or network. Repeated entrypoint runs copy identical bytes. The image and all authored source files are released under the MIT license in `LICENSE`.
