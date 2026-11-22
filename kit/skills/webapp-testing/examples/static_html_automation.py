from playwright.sync_api import sync_playwright
import os
import sys
from pathlib import Path

# Example: Automating interaction with static HTML files using file:// URLs
# Adapted 2026-11-03 (see SOURCE.md): installed Edge, Edge's temporary profile on D:, output in the current folder,
# and a file URL that is also valid on Windows

os.environ["TEMP"] = os.environ["TMP"] = str(Path(sys.prefix, "tmp"))
Path(os.environ["TEMP"]).mkdir(exist_ok=True)

html_file_path = os.path.abspath('path/to/your/file.html')
file_url = Path(html_file_path).as_uri()

with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge", headless=True, timeout=90_000)
    page = browser.new_page(viewport={'width': 1920, 'height': 1080})

    # Navigate to local HTML file
    page.goto(file_url)

    # Take screenshot
    page.screenshot(path='static_page.png', full_page=True)

    # Interact with elements
    page.click('text=Click Me')
    page.fill('#name', 'John Doe')
    page.fill('#email', 'john@example.com')

    # Submit form
    page.click('button[type="submit"]')
    page.wait_for_timeout(500)

    # Take final screenshot
    page.screenshot(path='after_submit.png', full_page=True)

    browser.close()

print("Static HTML automation completed!")
