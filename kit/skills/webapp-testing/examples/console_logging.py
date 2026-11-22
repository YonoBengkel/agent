import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

# Example: Capturing console logs during browser automation
# Adapted 2026-11-03 (see SOURCE.md): installed Edge, Edge's temporary profile on D:, output in the current folder

os.environ["TEMP"] = os.environ["TMP"] = str(Path(sys.prefix, "tmp"))
Path(os.environ["TEMP"]).mkdir(exist_ok=True)

url = 'http://localhost:5173'  # Replace with your URL

console_logs = []

with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge", headless=True, timeout=90_000)
    page = browser.new_page(viewport={'width': 1920, 'height': 1080})

    # Set up console log capture
    def handle_console_message(msg):
        console_logs.append(f"[{msg.type}] {msg.text}")
        print(f"Console: [{msg.type}] {msg.text}")

    page.on("console", handle_console_message)

    # Navigate to page
    page.goto(url)
    page.wait_for_load_state('networkidle')

    # Interact with the page (triggers console logs)
    page.click('text=Dashboard')
    page.wait_for_timeout(1000)

    browser.close()

# Save console logs to file
with open('console.log', 'w', encoding='utf-8') as f:
    f.write('\n'.join(console_logs))

print(f"\nCaptured {len(console_logs)} console messages")
print("Logs saved to: console.log")
