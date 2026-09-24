"""Render the verified Recon QA quick-start flow as an animated terminal GIF."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "assets" / "demo.gif"
WIDTH, HEIGHT = 1200, 680

BACKGROUND = "#0d1117"
TITLE_BAR = "#161b22"
TEXT = "#e6edf3"
MUTED = "#8b949e"
CYAN = "#58a6ff"
GREEN = "#3fb950"
RED = "#f85149"
PURPLE = "#a371f7"


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        Path("C:/Windows/Fonts/consolab.ttf" if bold else "C:/Windows/Fonts/consola.ttf"),
        Path(
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
            if bold
            else "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
        ),
    ]
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default()


FONT = load_font(24)
BOLD = load_font(24, bold=True)
SMALL = load_font(19)


def base_frame(step: int, label: str) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    frame = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(frame)
    draw.rounded_rectangle((1, 1, WIDTH - 2, HEIGHT - 2), radius=18, outline="#30363d", width=2)
    draw.rectangle((2, 2, WIDTH - 3, 72), fill=TITLE_BAR)
    for x, color in ((32, "#ff5f56"), (70, "#ffbd2e"), (108, "#27c93f")):
        draw.ellipse((x, 25, x + 22, 47), fill=color)
    draw.text((160, 22), "recon-qa — OpenAPI to executable QA", font=BOLD, fill=MUTED)
    draw.text((930, 24), f"{step}/5  {label}", font=SMALL, fill=PURPLE)
    return frame, draw


def line(
    draw: ImageDraw.ImageDraw, y: int, text: str, color: str = TEXT, bold: bool = False
) -> None:
    draw.text((45, y), text, font=BOLD if bold else FONT, fill=color)


def build_frames() -> list[Image.Image]:
    frames: list[Image.Image] = []

    frame, draw = base_frame(1, "INSTALL")
    line(draw, 112, "$ python -m pip install recon-qa", CYAN, True)
    line(draw, 168, "Collecting recon-qa")
    line(draw, 212, "Installing collected packages ...", MUTED)
    line(draw, 270, "Successfully installed recon-qa-0.2.1", GREEN, True)
    line(draw, 350, "One command. No API key required.", TEXT)
    frames.append(frame)

    frame, draw = base_frame(2, "RUN")
    line(draw, 112, "$ recon demo", CYAN, True)
    line(draw, 174, "Starting an intentionally defective app on localhost ...", MUTED)
    line(draw, 230, "Target: http://127.0.0.1:8765")
    line(draw, 286, "AI: off    External services: none", TEXT)
    frames.append(frame)

    frame, draw = base_frame(3, "DISCOVER")
    line(draw, 112, "✓ OpenAPI document discovered", GREEN, True)
    line(draw, 168, "  /api/health          GET")
    line(draw, 212, "  /api/users           POST")
    line(draw, 256, "  /api/orders          POST")
    line(draw, 300, "  /api/admin/secrets   GET")
    line(draw, 372, "Generated 35 schema-driven checks", CYAN, True)
    line(draw, 426, "Happy path · boundary · negative · authentication", MUTED)
    frames.append(frame)

    frame, draw = base_frame(4, "TEST")
    line(draw, 112, "PASSED  GET  /api/health", GREEN, True)
    line(draw, 166, "PASSED  POST /api/users", GREEN, True)
    line(draw, 220, "FAILED  POST /api/orders — returned HTTP 500", RED, True)
    line(draw, 274, "FAILED  GET  /api/admin/secrets — accepted anonymous request", RED, True)
    line(draw, 328, "PASSED  POST /api/inventory/reserve", GREEN, True)
    line(draw, 410, "Concrete assertions decide pass/fail.", TEXT)
    line(draw, 456, "LLM analysis is optional.", MUTED)
    frames.append(frame)

    frame, draw = base_frame(5, "REPORT")
    line(draw, 112, "Recon test run completed", CYAN, True)
    line(draw, 180, "Total tests     35", TEXT)
    line(draw, 228, "Passed          33", GREEN, True)
    line(draw, 276, "Failed           2", RED, True)
    line(draw, 324, "Pass rate      94.3%", TEXT)
    line(draw, 400, "HTML report ready", PURPLE, True)
    line(draw, 452, "Run: recon report", CYAN)
    line(draw, 536, "OpenAPI → checks → defects → evidence", TEXT, True)
    frames.append(frame)

    return frames


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    frames = build_frames()
    frames[0].save(
        OUTPUT,
        save_all=True,
        append_images=frames[1:],
        duration=[1700, 1700, 2200, 2600, 2600],
        loop=0,
        optimize=True,
    )
    print(f"Wrote {OUTPUT} ({OUTPUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
