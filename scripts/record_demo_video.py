"""Record the no-key Project SuperJoin walkthrough from the real browser UI.

The recorder is intentionally optional: Playwright is only imported when this
script is run, so the one-container runtime and offline test suite do not gain
another dependency. It records the bundled Demo Mode snapshot and never opens
the source-PDF links.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
from pathlib import Path

CAPTION_STYLE = """
  position: fixed; left: 50%; bottom: 22px; transform: translateX(-50%);
  z-index: 2147483647; max-width: 90%; padding: 11px 18px;
  border: 1px solid rgba(111, 229, 145, .45); border-radius: 4px;
  background: rgba(6, 35, 25, .94); color: #dff7e5;
  font: 600 15px/1.35 system-ui, sans-serif; text-align: center;
  box-shadow: 0 8px 24px rgba(0, 0, 0, .22);
"""


REDACTION_STYLE = """
  .workspace-picker select { color: transparent !important; text-shadow: none !important; }
  .topbar h1 { color: transparent !important; position: relative; }
  .topbar h1::after { content: 'Demo workspace'; color: var(--ink); position: absolute; left: 0; top: 0; }
  .document-info, .document-info *, .case-card h3, .case-card p, .case-card .badge,
  .case-card .case-footer, .case-card .case-footer *, .case-row, .case-row *,
  .table-card tbody, .table-card tbody *, .run-row strong, .run-row small,
  .run-row strong *, .run-row small *, .trust-form input, .gate-result,
  .gate-result * { color: transparent !important; text-shadow: none !important; }
  .document-info, .case-card h3, .case-card p, .case-card .case-footer, .case-row,
  .table-card tbody, .run-row strong, .run-row small, .gate-result,
  .inspector > :not(.inspector-top) { filter: blur(9px); }
  .inspector > :not(.inspector-top) * { color: transparent !important; text-shadow: none !important; }
  .document-source-link, .page-link { color: #0b9c47 !important; filter: none !important; }
  .page-list, .evidence-block, .relationship-hero, .dimension-list, .failure-box { filter: blur(10px); }
  .trust-form input { caret-color: transparent !important; }
"""


STEPS = (
    ("Project SuperJoin · recorded Demo Mode; no provider calls", 2.5),
    ("Documents keep parser quality, printed pages, and source links inspectable", 3.5),
    ("Required cases preserve corroboration, contradiction, reconciliation, and failure", 4.0),
    ("Facts remain tied to exact evidence anchors and normalized interpretations", 4.0),
    ("Knowledge Diff makes incremental changes and reuse visible", 3.0),
    ("Trust Gate blocks an unresolved value under the strict policy", 4.0),
    ("Runs expose recorded lifecycle and zero-call telemetry", 3.5),
    ("Independent provider roles are configured through nonsecret settings", 3.5),
)


def redaction_init_script() -> str:
    """Return the browser init script used by the rights-safe capture."""

    return (
        "(() => { const style = document.createElement('style'); "
        f"style.textContent = {json.dumps(REDACTION_STYLE)}; "
        "const install = () => (document.head || document.documentElement).appendChild(style); "
        "if (document.head || document.documentElement) install(); "
        "else document.addEventListener('DOMContentLoaded', install, { once: true }); })();"
    )


async def record(url: str, output: Path, redact_source: bool = False) -> Path:
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:  # pragma: no cover - optional local recording tool
        raise SystemExit("Install Playwright locally to record: python -m pip install playwright") from exc

    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = output.parent / (output.stem + "-staging")
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            device_scale_factor=1,
            record_video_dir=str(staging),
            record_video_size={"width": 1440, "height": 900},
        )
        if redact_source:
            await context.add_init_script(script=redaction_init_script())
        page = await context.new_page()
        await page.goto(url, wait_until="networkidle")
        await page.wait_for_selector("text=Project SuperJoin")

        await page.add_style_tag(content=f"#psj-caption {{{CAPTION_STYLE}}}")
        await page.evaluate(
            """() => {
              const caption = document.createElement('div');
              caption.id = 'psj-caption';
              caption.setAttribute('aria-hidden', 'true');
              document.body.appendChild(caption);
            }"""
        )

        async def caption(text: str, seconds: float) -> None:
            await page.locator("#psj-caption").evaluate(
                "(element, value) => { element.textContent = value; }", text
            )
            await page.wait_for_timeout(round(seconds * 1000))

        await caption(*STEPS[0])
        await page.get_by_role("button", name="Documents", exact=True).click()
        await page.get_by_role("button", name="Inspect Delhivery Annual Report FY24 · curated excerpt").click()
        await caption(*STEPS[1])
        await page.get_by_role("button", name="Close evidence inspector").click()

        await page.get_by_role("button", name="Required cases 4", exact=True).click()
        await page.locator(".case-card").first.click()
        await caption(*STEPS[2])
        await page.get_by_role("button", name="Close evidence inspector").click()

        await page.get_by_role("button", name="Facts", exact=True).click()
        await page.locator("tbody tr").first.click()
        await caption(*STEPS[3])
        await page.get_by_role("button", name="Close evidence inspector").click()

        await page.get_by_role("button", name="Knowledge Diff", exact=True).click()
        await caption(*STEPS[4])

        await page.locator(".workspace-picker select").select_option("india-macro")
        await page.get_by_role("heading", name="India Macroeconomy").wait_for()
        await page.get_by_role("button", name="Trust Gate", exact=True).click()
        trust_form = page.locator(".trust-form")
        await trust_form.locator("input").nth(0).fill("India")
        await trust_form.locator("input").nth(1).fill("real_gdp_growth")
        await trust_form.locator("input").nth(2).fill("FY26")
        await page.get_by_role("button", name="Resolve fact", exact=True).click()
        await caption(*STEPS[5])

        await page.get_by_role("button", name="Runs", exact=True).click()
        await page.get_by_role("button", name="Inspect telemetry").first.click()
        await caption(*STEPS[6])

        await page.get_by_role("button", name="Settings", exact=True).click()
        await caption(*STEPS[7])

        await context.close()
        await browser.close()

    recordings = sorted(staging.glob("*.webm"), key=lambda item: item.stat().st_mtime)
    if not recordings:
        raise RuntimeError(f"Playwright did not create a recording in {staging}")
    if output.exists():
        output.unlink()
    recordings[0].replace(output)
    shutil.rmtree(staging, ignore_errors=True)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8080", help="Running Project SuperJoin URL")
    parser.add_argument("--output", type=Path, required=True, help="Output WebM path outside the repository")
    parser.add_argument(
        "--redact-source",
        action="store_true",
        help="Mask source-derived text and values for a rights-safe public walkthrough",
    )
    args = parser.parse_args()
    result = asyncio.run(record(args.url, args.output, args.redact_source))
    print(result)


if __name__ == "__main__":
    main()
