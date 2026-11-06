"""Generate a high-polish, production-grade animated terminal GIF of Recon QA CLI in action."""

import asyncio
from pathlib import Path

from PIL import Image
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_GIF = ROOT / "docs" / "assets" / "recon_cli_in_action.gif"
LEGACY_GIF = ROOT / "docs" / "assets" / "demo.gif"

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background: #0b0f19;
    padding: 30px;
    display: flex;
    justify-content: center;
    align-items: center;
    font-family: 'Cascadia Code', 'Fira Code', 'Consolas', 'JetBrains Mono', monospace;
    -webkit-font-smoothing: antialiased;
  }}
  .window {{
    width: 900px;
    background: #0f172a;
    border-radius: 12px;
    box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.8), 0 0 0 1px rgba(255, 255, 255, 0.08);
    overflow: hidden;
  }}
  .titlebar {{
    background: #1e293b;
    padding: 12px 18px;
    display: flex;
    align-items: center;
    gap: 8px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  }}
  .dot {{
    width: 12px;
    height: 12px;
    border-radius: 50%;
  }}
  .dot-red {{ background: #ef4444; }}
  .dot-yellow {{ background: #f59e0b; }}
  .dot-green {{ background: #10b981; }}
  .title {{
    color: #94a3b8;
    font-size: 13px;
    font-weight: 500;
    margin: 0 auto;
    padding-right: 48px;
    letter-spacing: 0.3px;
  }}
  .term {{
    padding: 24px;
    color: #e2e8f0;
    font-size: 14px;
    line-height: 1.6;
    min-height: 520px;
  }}
  .prompt-line {{
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 12px;
  }}
  .p-icon {{ color: #06b6d4; font-weight: bold; }}
  .p-path {{ color: #3b82f6; font-weight: 600; }}
  .p-branch {{ color: #8b5cf6; }}
  .p-cmd {{ color: #f8fafc; font-weight: 600; }}
  .cursor {{
    display: inline-block;
    width: 8px;
    height: 16px;
    background: #38bdf8;
    vertical-align: middle;
    animation: blink 1s step-end infinite;
  }}
  .panel {{
    border: 1px solid;
    border-radius: 8px;
    padding: 10px 16px;
    margin: 10px 0;
  }}
  .panel-cyan {{
    border-color: #0ea5e9;
    background: rgba(14, 165, 233, 0.05);
  }}
  .panel-red {{
    border-color: #ef4444;
    background: rgba(239, 68, 68, 0.05);
  }}
  .panel-yellow {{
    border-color: #f59e0b;
    background: rgba(245, 158, 11, 0.05);
  }}
  .panel-title {{
    font-weight: bold;
    margin-bottom: 4px;
  }}
  .dim {{ color: #64748b; }}
  .cyan {{ color: #38bdf8; }}
  .green {{ color: #34d399; font-weight: 600; }}
  .red {{ color: #f87171; font-weight: 600; }}
  .yellow {{ color: #fbbf24; font-weight: 600; }}
  .white {{ color: #f8fafc; }}
  .bold {{ font-weight: bold; }}

  table.term-table {{
    width: 100%;
    border-collapse: collapse;
    margin: 10px 0 14px 0;
    font-size: 13px;
  }}
  table.term-table th {{
    text-align: left;
    color: #38bdf8;
    border-bottom: 1px solid #334155;
    padding: 4px 8px;
    font-weight: 600;
  }}
  table.term-table td {{
    padding: 4px 8px;
    border-bottom: 1px solid rgba(51, 65, 85, 0.4);
  }}
  .badge {{
    display: inline-block;
    padding: 1px 6px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 700;
  }}
  .b-get {{ background: #065f46; color: #6ee7b7; }}
  .b-post {{ background: #1e3a8a; color: #93c5fd; }}
  .b-pass {{ color: #34d399; font-weight: bold; }}
  .b-fail {{ color: #f87171; font-weight: bold; }}
</style>
</head>
<body>
  <div class="window">
    <div class="titlebar">
      <span class="dot dot-red"></span>
      <span class="dot dot-yellow"></span>
      <span class="dot dot-green"></span>
      <span class="title">recon — zsh — 90×26</span>
    </div>
    <div class="term">
      {content}
    </div>
  </div>
</body>
</html>
"""

# Frames definitions
PROMPT = """
<div class="prompt-line">
  <span class="p-icon">❯</span>
  <span class="p-path">recon-app</span>
  <span class="p-branch">(main)</span>
  <span class="p-cmd">{cmd}</span>{cursor}
</div>
"""

FRAME_COMMAND = "recon test http://localhost:8000 --ai"

DISCOVERY_PANEL = """
<div class="panel panel-cyan">
  <div class="panel-title white bold">Recon QA <span class="cyan">(Project: localhost_8000)</span></div>
  <div class="dim">Target: <span class="cyan">http://localhost:8000</span> | Concurrency: <span class="yellow">4</span> | Browser: <span class="white">True</span> | AI Provider: <span class="green">Active (Gemini)</span></div>
</div>
<div style="margin: 8px 0; color: #94a3b8;">
  <span class="cyan bold">Scanning target:</span> http://localhost:8000<br>
  <span class="green">✔</span> Discovered 12 endpoints & schemas from OpenAPI specification
</div>
"""

TABLE_DISCOVERED = """
<table class="term-table">
  <thead>
    <tr>
      <th style="width: 80px;">Method</th>
      <th>Path</th>
      <th>Parameters</th>
      <th>Response</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td><span class="badge b-get">GET</span></td>
      <td class="cyan">/api/v1/products</td>
      <td class="dim">limit, offset, category</td>
      <td class="white">200 OK (List[Product])</td>
    </tr>
    <tr>
      <td><span class="badge b-post">POST</span></td>
      <td class="cyan">/api/v1/orders/checkout</td>
      <td class="dim">items, coupon_code</td>
      <td class="white">201 Created (Order)</td>
    </tr>
    <tr>
      <td><span class="badge b-get">GET</span></td>
      <td class="cyan">/api/v1/users/profile</td>
      <td class="dim">Authorization Bearer</td>
      <td class="white">200 OK (User)</td>
    </tr>
  </tbody>
</table>
"""

TEST_LINES = [
    '<div style="color:#94a3b8; margin: 4px 0;"><span class="b-pass">✔ PASS</span> <span class="cyan">GET</span> /api/v1/health <span class="dim">→ 200 OK (8ms)</span></div>',
    '<div style="color:#94a3b8; margin: 4px 0;"><span class="b-pass">✔ PASS</span> <span class="cyan">GET</span> /api/v1/products <span class="dim">→ 200 OK (24ms) [boundary: limit=100]</span></div>',
    '<div style="color:#94a3b8; margin: 4px 0;"><span class="b-pass">✔ PASS</span> <span class="cyan">POST</span> /api/v1/auth/login <span class="dim">→ 200 OK (38ms) [positive auth]</span></div>',
    '<div style="color:#f87171; margin: 4px 0; font-weight: 500;"><span class="b-fail">✖ FAIL</span> <span class="cyan">POST</span> /api/v1/orders/checkout <span class="red">→ 500 Internal Error (42ms) [coupon=null]</span></div>',
    '<div style="color:#94a3b8; margin: 4px 0;"><span class="b-pass">✔ PASS</span> <span class="cyan">GET</span> /api/v1/users/profile <span class="dim">→ 401 Unauthorized (12ms) [negative auth guard]</span></div>',
]

SUMMARY_PANEL = """
<div class="panel panel-red" style="margin-top: 14px;">
  <div class="panel-title bold white">Recon Test Run Completed</div>
  <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 4px; margin-top: 6px; font-size: 13px;">
    <div>Total Tests : <span class="white bold">5</span></div>
    <div>Passed      : <span class="green bold">4</span></div>
    <div>Failed      : <span class="red bold">1</span></div>
    <div>Pass Rate   : <span class="yellow bold">80.0%</span></div>
    <div>Duration    : <span class="white">1.24s</span></div>
    <div>HTML Report : <span class="cyan" style="text-decoration: underline;">reports/run-20261107/report.html</span></div>
  </div>
</div>
"""

AI_PANEL = """
<div class="panel panel-yellow">
  <div class="panel-title bold yellow">⚡ Failure Analysis Highlights (Gemini AI Root-Cause)</div>
  <div style="font-size: 13px; line-height: 1.5; margin-top: 4px;">
    <div><span class="red bold">Test Failed:</span> POST /api/v1/orders/checkout</div>
    <div><span class="yellow bold">Likely Cause:</span> Unhandled null pointer in coupon discount validator</div>
    <div><span class="green bold">Suggested Fix:</span> Add <code style="background:rgba(255,255,255,0.1); padding: 1px 4px; border-radius: 3px;">if order.coupon and order.coupon.code:</code> check before discount lookup</div>
    <div class="dim">Confidence Score: 95%</div>
  </div>
</div>
"""

REPORT_READY = """
<div style="margin: 10px 0; color: #34d399; font-weight: 600;">
  ✔ Interactive HTML report ready with 1-click cURL reproduction: <span style="text-decoration: underline; color: #38bdf8;">reports/latest.html</span>
</div>
"""

PROMPT_RETURN = """
<div class="prompt-line" style="margin-top: 12px;">
  <span class="p-icon">❯</span>
  <span class="p-path">recon-app</span>
  <span class="p-branch">(main)</span>
  <span class="p-cmd"></span><span class="cursor"></span>
</div>
"""


async def generate_gif():
    OUTPUT_GIF.parent.mkdir(parents=True, exist_ok=True)
    frames_data = []

    # Frame 0: Idle prompt
    f0 = PROMPT.format(cmd="", cursor='<span class="cursor"></span>')
    frames_data.append((f0, 600))

    # Typing frames
    cmd_text = FRAME_COMMAND
    steps = [3, 7, 12, 17, 23, 29, 34, len(cmd_text)]
    for s in steps:
        sub = cmd_text[:s]
        content = PROMPT.format(cmd=sub, cursor='<span class="cursor"></span>')
        frames_data.append((content, 90))

    # Command executed (enter pressed)
    f_enter = (
        PROMPT.format(cmd=cmd_text, cursor="")
        + '<div style="margin: 8px 0; color: #94a3b8;"><span class="cyan">⠋</span> Discovering application assets & OpenAPI schemas...</div>'
    )
    frames_data.append((f_enter, 450))

    # Discovery panel + endpoints table
    f_disc = PROMPT.format(cmd=cmd_text, cursor="") + DISCOVERY_PANEL + TABLE_DISCOVERED
    frames_data.append((f_disc, 650))

    # Running tests one by one
    running_tests = ""
    for idx, t_line in enumerate(TEST_LINES):
        running_tests += t_line
        f_tests = (
            PROMPT.format(cmd=cmd_text, cursor="")
            + DISCOVERY_PANEL
            + TABLE_DISCOVERED
            + '<div style="margin-top: 8px; font-weight: 600; color: #38bdf8;">Executing Generated Test Suite:</div>'
            + running_tests
        )
        duration = 320 if "FAIL" in t_line else 200
        frames_data.append((f_tests, duration))

    # Summary panel appears
    f_summary = (
        PROMPT.format(cmd=cmd_text, cursor="")
        + DISCOVERY_PANEL
        + TABLE_DISCOVERED
        + '<div style="margin-top: 8px; font-weight: 600; color: #38bdf8;">Executing Generated Test Suite:</div>'
        + running_tests
        + SUMMARY_PANEL
    )
    frames_data.append((f_summary, 700))

    # AI RCA analysis highlight appears
    f_ai = (
        PROMPT.format(cmd=cmd_text, cursor="")
        + DISCOVERY_PANEL
        + TABLE_DISCOVERED
        + '<div style="margin-top: 8px; font-weight: 600; color: #38bdf8;">Executing Generated Test Suite:</div>'
        + running_tests
        + SUMMARY_PANEL
        + AI_PANEL
    )
    frames_data.append((f_ai, 1100))

    # Final frame: prompt return and report link
    f_final = (
        PROMPT.format(cmd=cmd_text, cursor="")
        + DISCOVERY_PANEL
        + TABLE_DISCOVERED
        + '<div style="margin-top: 8px; font-weight: 600; color: #38bdf8;">Executing Generated Test Suite:</div>'
        + running_tests
        + SUMMARY_PANEL
        + AI_PANEL
        + REPORT_READY
        + PROMPT_RETURN
    )
    # Hold final frame for 4000ms so PR viewers have time to read
    frames_data.append((f_final, 4000))

    print(f"Total animation frames: {len(frames_data)}")

    # Render each frame with Playwright
    pil_images = []
    durations = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 960, "height": 920})

        for i, (content, dur) in enumerate(frames_data):
            html = HTML_TEMPLATE.format(content=content)
            await page.set_content(html, wait_until="domcontentloaded")
            window_elem = page.locator(".window")
            screenshot_bytes = await window_elem.screenshot()

            import io

            img = Image.open(io.BytesIO(screenshot_bytes))
            # Convert RGBA to RGB with background
            rgb_img = Image.new("RGB", img.size, (11, 15, 25))
            if img.mode == "RGBA":
                rgb_img.paste(img, mask=img.split()[3])
            else:
                rgb_img.paste(img)

            # Downscale slightly for crisp retina sampling (900 -> 800) and small file size
            resized = rgb_img.resize(
                (820, int(820 * rgb_img.height / rgb_img.width)), Image.Resampling.LANCZOS
            )

            # Quantize with web-safe / adaptive palette
            quantized = resized.quantize(colors=128, method=Image.Quantize.MEDIANCUT)
            pil_images.append(quantized)
            durations.append(dur)
            print(f"Rendered frame {i + 1}/{len(frames_data)} ({dur}ms)")

        await browser.close()

    print("Assembling animated GIF...")
    pil_images[0].save(
        OUTPUT_GIF,
        save_all=True,
        append_images=pil_images[1:],
        duration=durations,
        loop=0,
        optimize=True,
    )

    # Also save to demo.gif so existing references/assets stay updated
    pil_images[0].save(
        LEGACY_GIF,
        save_all=True,
        append_images=pil_images[1:],
        duration=durations,
        loop=0,
        optimize=True,
    )

    size_kb = OUTPUT_GIF.stat().st_size / 1024
    print(f"Successfully generated GIF: {OUTPUT_GIF}")
    print(f"File size: {size_kb:.1f} KB")


if __name__ == "__main__":
    asyncio.run(generate_gif())
