#!/usr/bin/env python3
"""Render the authored newspaper using Chromium, Playwright, or a PIL compositor."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import zlib
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SIZE = 1024
LIMIT = 1_048_576
DATE = "TUESDAY 24 NOVEMBER 2026"
FOOTER = "40 stories. One day. 24 November 2026."
COLORS = {
    "UKRAINE": "#a7432d", "IRAN": "#9b5530", "WAR": "#805653",
    "MARKETS": "#22675c", "ASIA": "#2f6285", "AFRICA": "#8b6831",
    "EU": "#395ba0", "AMERICAS": "#745572", "SCIENCE": "#287e85",
}


class LayoutError(RuntimeError):
    """A composition error must be fixed rather than hidden by another backend."""


@dataclass
class Story:
    number: int
    original: str
    timestamp: str = ""
    source: str = ""
    headline: str = ""
    detail: str = ""


@dataclass
class Desk:
    tag: str
    column: int
    label: str = ""
    stories: list[Story] = field(default_factory=list)


class Newspaper(HTMLParser):
    """Read the same visible copy for both the browser and the fallback."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.desks: list[Desk] = []
        self.desk: Desk | None = None
        self.story: Story | None = None
        self.stack: list[tuple[str, str]] = []
        self.title = ""
        self.summary = ""
        self.footer = ""

    def handle_starttag(self, tag: str, attributes: list[tuple[str, str | None]]) -> None:
        attrs = dict(attributes)
        classes = (attrs.get("class") or "").split()
        if tag in {"script", "iframe", "img"} or (tag == "link" and attrs.get("href")):
            raise LayoutError("The newspaper must use inline CSS and no external assets.")
        if tag in {"meta", "br", "hr", "input", "link", "img"}:
            return
        active = self.stack[-1][1] if self.stack else ""
        if tag == "section" and "desk" in classes:
            self.desk = Desk(str(attrs["data-tag"]), int(str(attrs["data-column"])))
            self.desks.append(self.desk)
        if tag == "article":
            self.story = Story(int(str(attrs["data-number"])), str(attrs["data-full-headline"]))
        if tag == "h1":
            active = "title"
        elif tag == "footer":
            active = "footer"
        elif tag == "time":
            if not str(attrs.get("datetime", "")).startswith("2026-11-24T"):
                raise LayoutError("Every story must belong to 24 November 2026.")
            active = "timestamp"
        for css_class, target in {
            "summary-text": "summary", "source": "source", "headline": "headline",
            "detail": "detail", "desk-heading": "label",
        }.items():
            if css_class in classes:
                active = target
        self.stack.append((tag, active))

    def handle_endtag(self, tag: str) -> None:
        if tag == "article" and self.story is not None:
            if self.desk is None:
                raise LayoutError("Every card needs a topic desk.")
            self.desk.stories.append(self.story)
            self.story = None
        if tag == "section":
            self.desk = None
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break

    def handle_data(self, text: str) -> None:
        if not self.stack:
            return
        active = self.stack[-1][1]
        if active in {"title", "summary", "footer"}:
            setattr(self, active, getattr(self, active) + text)
        elif active == "label" and self.desk is not None:
            self.desk.label += text
        elif self.story is not None and active in {"timestamp", "source", "headline", "detail"}:
            setattr(self.story, active, getattr(self.story, active) + text)


def load_newspaper() -> Newspaper:
    newspaper = Newspaper()
    newspaper.feed((ROOT / "news.html").read_text(encoding="utf-8"))
    newspaper.title = " ".join(newspaper.title.split())
    newspaper.summary = " ".join(newspaper.summary.split())
    newspaper.footer = " ".join(newspaper.footer.split())
    stories = [story for desk in newspaper.desks for story in desk.stories]
    if newspaper.title != DATE or newspaper.footer != FOOTER:
        raise LayoutError("The masthead or exact footer text is missing.")
    if len(stories) != 40 or sorted(story.number for story in stories) != list(range(1, 41)):
        raise LayoutError("The page must contain exactly forty uniquely numbered stories.")
    if {desk.tag for desk in newspaper.desks} != set(COLORS):
        raise LayoutError("All nine requested topic tags must appear.")
    if not newspaper.summary:
        raise LayoutError("The day summary is empty.")
    for story in stories:
        for name in ("timestamp", "source", "headline", "detail"):
            setattr(story, name, " ".join(getattr(story, name).split()))
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\dZ", story.timestamp):
            raise LayoutError(f"Invalid UTC time on story {story.number}.")
        if not all((story.source, story.headline, story.detail, story.original)):
            raise LayoutError(f"Incomplete story {story.number}.")
    return newspaper


LAYOUT_CHECK = r"""() => {
  const violations = [];
  const tolerance = 0.75;
  const elements = [...document.querySelectorAll('body *')];
  for (const element of elements) {
    const box = element.getBoundingClientRect();
    if (box.width === 0 || box.height === 0) continue;
    if (box.left < -tolerance || box.top < -tolerance ||
        box.right > 1024 + tolerance || box.bottom > 1024 + tolerance) {
      violations.push(`outside canvas: ${element.tagName}.${element.className}`);
    }
    if (element.clientWidth && element.scrollWidth > element.clientWidth + 1) {
      violations.push(`horizontal overflow: ${element.tagName}.${element.className} (${element.scrollWidth}/${element.clientWidth})`);
    }
    if (element.clientHeight && element.scrollHeight > element.clientHeight + 1) {
      violations.push(`vertical overflow: ${element.tagName}.${element.className} (${element.scrollHeight}/${element.clientHeight})`);
    }
  }
  for (const element of document.querySelectorAll('.headline, .detail, .summary-text')) {
    const range = document.createRange();
    range.selectNodeContents(element);
    const text = range.getBoundingClientRect();
    const box = element.getBoundingClientRect();
    if (text.left < box.left - tolerance || text.right > box.right + tolerance ||
        text.top < box.top - tolerance || text.bottom > box.bottom + tolerance) {
      violations.push(`text outside its line: ${element.textContent}`);
    }
    if (range.getClientRects().length !== 1) {
      violations.push(`text is not one line: ${element.textContent}`);
    }
  }
  const cards = [...document.querySelectorAll('.story')];
  const numbers = cards.map(card => Number(card.dataset.number)).sort((a, b) => a - b);
  if (cards.length !== 40 || numbers.some((number, i) => number !== i + 1)) {
    violations.push('expected forty unique numbered cards');
  }
  for (let i = 0; i < cards.length; i++) {
    const a = cards[i].getBoundingClientRect();
    for (let j = i + 1; j < cards.length; j++) {
      const b = cards[j].getBoundingClientRect();
      if (Math.min(a.right, b.right) - Math.max(a.left, b.left) > tolerance &&
          Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top) > tolerance) {
        violations.push(`overlapping cards ${cards[i].dataset.number}/${cards[j].dataset.number}`);
      }
    }
    for (const line of cards[i].querySelectorAll('.story-meta, .headline, .detail')) {
      const b = line.getBoundingClientRect();
      if (b.top < a.top - tolerance || b.bottom > a.bottom + tolerance) {
        violations.push(`line outside card ${cards[i].dataset.number}`);
      }
    }
  }
  if (document.documentElement.scrollWidth !== 1024 || document.documentElement.scrollHeight !== 1024) {
    violations.push('the document has a scrollable dimension');
  }
  if (document.querySelector('footer').textContent !== '40 stories. One day. 24 November 2026.') {
    violations.push('footer differs from the required text');
  }
  const columns = [...document.querySelectorAll('.column')].map(column => ({
    width: Number(column.getBoundingClientRect().width.toFixed(3)),
    stories: column.querySelectorAll('.story').length
  }));
  return {viewport: [innerWidth, innerHeight], columns, stories: cards.length,
    desks: document.querySelectorAll('.desk').length, violations};
}"""


def browser_page(output: Path | None, executable: str | None = None) -> dict:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        options = {"headless": True, "args": ["--no-sandbox", "--disable-dev-shm-usage"]}
        if executable:
            options["executable_path"] = executable
        browser = playwright.chromium.launch(**options)
        try:
            context = browser.new_context(
                viewport={"width": SIZE, "height": SIZE},
                device_scale_factor=1, offline=True, locale="en-GB", timezone_id="UTC",
            )
            page = context.new_page()
            page.goto((ROOT / "news.html").as_uri(), wait_until="load")
            page.evaluate("() => document.fonts.ready.then(() => true)")
            report = page.evaluate(LAYOUT_CHECK)
            if report["violations"]:
                raise LayoutError(json.dumps(report, indent=2))
            if output is not None:
                page.screenshot(path=str(output), full_page=False, animations="disabled")
            return report
        finally:
            browser.close()


def render_chromium(output: Path, executable: str) -> dict:
    # Use the system browser directly when one is available.
    with tempfile.TemporaryDirectory(prefix="ni24-chromium-") as profile:
        command = [
            executable, "--headless=new", "--no-sandbox", "--disable-gpu",
            "--disable-dev-shm-usage", "--disable-background-networking", "--disable-sync",
            "--no-first-run", "--hide-scrollbars", "--force-device-scale-factor=1",
            "--window-size=1024,1024", "--run-all-compositor-stages-before-draw",
            "--virtual-time-budget=1000", f"--user-data-dir={profile}",
            f"--screenshot={output}", (ROOT / "news.html").as_uri(),
        ]
        completed = subprocess.run(command, capture_output=True, text=True, timeout=45)
        if completed.returncode or not output.is_file():
            raise RuntimeError(f"Chromium could not render the page (exit {completed.returncode}).")
    try:
        return browser_page(None, executable)
    except ImportError:
        return {"viewport": [SIZE, SIZE], "layout": "fixed CSS; Playwright unavailable for DOM audit"}


def render_pil(output: Path, newspaper: Newspaper) -> dict:
    from PIL import Image, ImageDraw, ImageFont

    scale = 2
    image = Image.new("RGB", (SIZE * scale, SIZE * scale), "#f3f0e7")
    draw = ImageDraw.Draw(image)
    ink, muted, rule = "#172f36", "#607076", "#d3d6cf"
    font_roots = [Path("/usr/share/fonts/truetype/dejavu"), Path("/usr/share/fonts/TTF")]
    font_cache = {}

    def font(size: float, bold: bool = False):
        key = (round(size * scale), bold)
        if key not in font_cache:
            filename = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
            candidates = [str(folder / filename) for folder in font_roots] + [filename]
            for candidate in candidates:
                try:
                    font_cache[key] = ImageFont.truetype(candidate, key[0])
                    break
                except OSError:
                    continue
            else:
                font_cache[key] = ImageFont.load_default(size=key[0])
        return font_cache[key]

    def rectangle(box, fill):
        draw.rectangle(tuple(round(value * scale) for value in box), fill=fill)

    def text(value, x, y, width, size, color=ink, bold=False, minimum=6):
        chosen = size
        while draw.textlength(value, font=font(chosen, bold)) > width * scale:
            chosen -= 0.25
            if chosen < minimum:
                raise LayoutError(f"Fallback text cannot fit: {value}")
        selected = font(chosen, bold)
        box = draw.textbbox((round(x * scale), round(y * scale)), value, font=selected, anchor="lt")
        if box[0] < 0 or box[1] < 0 or box[2] > SIZE * scale or box[3] > SIZE * scale:
            raise LayoutError(f"Fallback text leaves the image: {value}")
        draw.text((round(x * scale), round(y * scale)), value, font=selected, fill=color, anchor="lt")

    rectangle((24, 21, 34, 31), "#b83d2b")
    text("THE WORLD IN ONE DAY", 41, 21, 350, 9, bold=True)
    text("40 DISPATCHES · 9 DESKS · ALL TIMES UTC", 718, 21, 282, 8, muted, True)
    text(newspaper.title, 24, 49, 976, 59, bold=True, minimum=50)
    rectangle((24, 108, 1000, 111), ink)
    rectangle((24, 121, 1000, 155), ink)
    text("DAY SUMMARY", 33, 134, 76, 8, "#fffdf5", True)
    text(newspaper.summary, 119, 135, 872, 6.5, "#fffdf5", minimum=5.5)

    column_width = (976 - 24) / 3
    for column in range(3):
        x = 24 + column * (column_width + 12)
        y = 165
        card_height = 50 if column == 1 else 53
        for desk in (desk for desk in newspaper.desks if desk.column == column):
            accent = COLORS[desk.tag]
            rectangle((x, y, x + column_width, y + 3), accent)
            text(desk.tag, x, y + 9, 105, 12, accent, True)
            # The visible heading includes a compact descriptor and the card count.
            descriptor = " ".join(desk.label.split())[len(desk.tag):].strip()
            text(descriptor, x + 109, y + 11, column_width - 109, 7, accent, True)
            y += 26
            for index, story in enumerate(desk.stories):
                fill = "#f6f4ed" if index % 2 == 0 else "#f9f8f2"
                rectangle((x, y, x + column_width, y + card_height - 1), fill)
                rectangle((x, y + card_height - 1, x + column_width, y + card_height), rule)
                text(f"{story.number:02d}", x + 4, y + 6, 18, 10, accent, True)
                text(story.timestamp, x + 29, y + 7, 42, 8, ink, True)
                rectangle((x + 76, y + 6, x + 76.5, y + 15), rule)
                text(story.source.upper(), x + 83, y + 8, column_width - 87, 7, muted, True)
                text(story.headline, x + 4, y + 20, column_width - 8, 11.1, ink, True, 9)
                text(story.detail, x + 4, y + 36, column_width - 8, 8.2, "#53636a", minimum=7)
                y += card_height
            y += 12
        if y - 12 > 968:
            raise LayoutError(f"Fallback column {column} reaches the footer.")
    rectangle((24, 978, 1000, 981), ink)
    footer_font = font(12, True)
    footer_width = draw.textlength(newspaper.footer, font=footer_font) / scale
    text(newspaper.footer, (SIZE - footer_width) / 2, 989, footer_width + 1, 12, ink, True)
    image.resize((SIZE, SIZE), Image.Resampling.LANCZOS).save(output, optimize=True)
    return {"viewport": [SIZE, SIZE], "stories": 40, "desks": 9, "violations": [], "layout": "PIL measured text"}


def finish_png(path: Path) -> tuple[int, str]:
    # RGB removes screenshot metadata and makes the result compact and repeatable.
    try:
        from PIL import Image
    except ImportError:
        pass
    else:
        with Image.open(path) as image:
            image.convert("RGB").save(path, format="PNG", optimize=True)
    data = path.read_bytes()
    if len(data) > LIMIT or data[:8] != b"\x89PNG\r\n\x1a\n":
        raise LayoutError("The output must be a PNG within the 1 MiB limit.")
    cursor = 8
    chunks = []
    pixels = bytearray()
    while cursor < len(data):
        if cursor + 12 > len(data):
            raise LayoutError("Truncated PNG chunk.")
        length = struct.unpack_from(">I", data, cursor)[0]
        end = cursor + 12 + length
        if end > len(data):
            raise LayoutError("Incomplete PNG data.")
        kind = data[cursor + 4:cursor + 8]
        content = data[cursor + 8:cursor + 8 + length]
        checksum = struct.unpack_from(">I", data, cursor + 8 + length)[0]
        if zlib.crc32(kind + content) & 0xFFFFFFFF != checksum:
            raise LayoutError("PNG chunk checksum mismatch.")
        if kind == b"IHDR":
            width, height, depth, color, compression, filtering, interlace = struct.unpack(">IIBBBBB", content)
            if (width, height, depth, color, compression, filtering, interlace) != (SIZE, SIZE, 8, 2, 0, 0, 0):
                # Browser screenshots without PIL normalization can use RGBA.
                if (width, height, depth, color, compression, filtering, interlace) != (SIZE, SIZE, 8, 6, 0, 0, 0):
                    raise LayoutError("Expected a noninterlaced 1024 by 1024 RGB/RGBA PNG.")
        if kind == b"IDAT":
            pixels.extend(content)
        chunks.append(kind)
        cursor = end
        if kind == b"IEND":
            break
    if not chunks or chunks[0] != b"IHDR" or chunks[-1] != b"IEND" or cursor != len(data):
        raise LayoutError("PNG must have a complete header, image data, and end marker.")
    decoded = zlib.decompress(pixels)
    stride = SIZE * (3 if color == 2 else 4) + 1
    if len(decoded) != SIZE * stride or any(decoded[row * stride] > 4 for row in range(SIZE)):
        raise LayoutError("PNG scanlines are incomplete or invalid.")
    return len(data), hashlib.sha256(data).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("auto", "chromium", "playwright", "pil"), default="auto")
    parser.add_argument("--output", type=Path, default=ROOT / "entry.png")
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.parent.is_dir():
        raise RuntimeError(f"The output parent must already exist: {output.parent}")
    newspaper = load_newspaper()
    executable = next((found for name in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable")
                       if (found := shutil.which(name))), None)
    backends = [args.backend] if args.backend != "auto" else ["chromium", "playwright", "pil"]
    failures = []
    for backend in backends:
        try:
            if backend == "chromium":
                if not executable:
                    raise RuntimeError("No system Chromium executable is available.")
                report = render_chromium(output, executable)
            elif backend == "playwright":
                report = browser_page(output)
            else:
                report = render_pil(output, newspaper)
            byte_count, digest = finish_png(output)
            print(json.dumps({"backend": backend, "output": str(output), "bytes": byte_count,
                              "sha256": digest, "layout": report}, indent=2))
            return
        except LayoutError:
            raise
        except Exception as error:
            if args.backend != "auto":
                raise
            failures.append(f"{backend}: {type(error).__name__}: {error}")
    raise RuntimeError("No rendering backend succeeded. " + "; ".join(failures))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Render failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
