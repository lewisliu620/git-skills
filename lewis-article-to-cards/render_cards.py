#!/usr/bin/env python3
"""
Lewis Article to Cards — HTML → PNG renderer
Usage: python3 render_cards.py <input.html> <output_dir>
Finds all .poster.xhs elements and screenshots each as PNG (1080x1440).
"""
import sys, os, pathlib
from playwright.sync_api import sync_playwright

def main():
    if len(sys.argv) < 3:
        print("Usage: python3 render_cards.py <input.html> <output_dir>")
        sys.exit(1)

    html_path = pathlib.Path(sys.argv[1]).resolve()
    out_dir = pathlib.Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)

    if not html_path.exists():
        print(f"ERROR: {html_path} not found")
        sys.exit(1)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path="/usr/local/bin/chromium-browser",
            args=["--no-sandbox", "--disable-gpu"]
        )
        page = browser.new_page(viewport={"width": 1080, "height": 1440})
        page.goto(f"file://{html_path}")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(500)

        # Find all xhs posters
        posters = page.query_selector_all(".poster.xhs")
        if not posters:
            print("ERROR: no .poster.xhs elements found in HTML")
            browser.close()
            sys.exit(1)

        print(f"Found {len(posters)} cards to render")
        for i, poster in enumerate(posters, 1):
            out_path = out_dir / f"card_{i:02d}.png"
            poster.screenshot(path=str(out_path))
            print(f"  card_{i:02d}.png  ({out_path.stat().st_size // 1024}KB)")

        browser.close()

    print(f"\nDone: {len(posters)} cards → {out_dir}")

if __name__ == "__main__":
    main()
