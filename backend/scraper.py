"""
scraper.py

Store detection, page fetching, and — the important part — deterministic
field extraction. The LLM in agent.py is now only called for whatever
fields this file can't find on its own, and it is never allowed to
override a value found here.

What's actually verified vs. best-effort:

  StyleKorean — verified against real product pages. It serves standard
  Open Graph Product meta tags (price), a labelled "Gross Weight" line
  in the visible spec area, and — reliably, across every Time Deal
  product checked — a "-timedeal-" segment in the product's own URL
  slug. All three required fields are readable with no LLM involved.

  YesStyle — NOT verified the same way: a plain fetch during development
  was blocked by their bot detection, so its real markup was never
  inspected in a browser. The parser below checks the common patterns
  (schema.org JSON-LD Product data, then Open Graph tags) as a
  reasonable default, but treat these selectors as a first draft —
  confirm them against a real rendered page (Playwright + devtools)
  before trusting them. Coupon eligibility IS deterministic though: it
  reads a specific disclaimer line YesStyle shows on non-eligible
  products ("Coupons offering a percentage discount ... cannot be used
  with this product") and defaults to eligible when that line is absent
  — no LLM guessing involved for that field anymore.
"""

import json
import re
from typing import Optional

import httpx
from bs4 import BeautifulSoup

STORE_HOSTS = {
    "stylekorean": "style_korean",
    "yesstyle": "yes_style",
}

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
MIN_TEXT_LENGTH = 500  # below this, assume the page needs JS to render

REQUIRED_FIELDS_BY_STORE = {
    "style_korean": {"productName", "price", "weight", "timeDeal"},
    "yes_style": {"productName", "price", "weight", "eligibleForCode"},
}


def detect_store(url: str) -> Optional[str]:
    host = re.sub(r"^https?://(www\.)?", "", url.strip(), flags=re.IGNORECASE)
    host = host.split("/")[0].lower()

    for needle, store in STORE_HOSTS.items():
        if needle in host:
            return store
    return None


async def fetch_page_html(url: str) -> str:
    """
    Plain HTTP GET first (fast, works for statically-rendered pages —
    confirmed sufficient for StyleKorean). Falls back to a headless
    browser for pages that need JS to render, or that block a bare
    request (YesStyle did during development).
    """
    async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:
        try:
            resp = await client.get(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept-Language": "en-US,en;q=0.9",
                },
            )
            resp.raise_for_status()
            html = resp.text
        except httpx.HTTPStatusError:
            html = ""

    needs_playwright = not html or _looks_incomplete(html)

    print("=" * 60)
    print("URL:", url)
    print("HTTP HTML length:", len(html))
    print("Needs Playwright:", needs_playwright)

    if needs_playwright:
        print("Using Playwright...")
        html = await _fetch_with_playwright(url)
    else:
        print("Using HTTP response...")

    print("Final HTML length:", len(html))
    print("=" * 60)

    return html

def _looks_incomplete(html: str) -> bool:
    text = BeautifulSoup(html, "html.parser").get_text(strip=True)
    return len(text) < MIN_TEXT_LENGTH


async def _fetch_with_playwright(url: str) -> str:
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        try:
            page = await browser.new_page(user_agent=USER_AGENT)
            await page.goto(url, wait_until="networkidle", timeout=20000)
            return await page.content()
        finally:
            await browser.close()


def extract_visible_text(html: str, max_chars: int = 6000) -> str:
    """
    Strips scripts/styles and collapses whitespace — this is what gets
    handed to the LLM fallback, never the raw HTML/CSS/JS.
    """
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "iframe"]):
        tag.decompose()

    text = soup.get_text(separator="\n")
    text = re.sub(r"\n{2,}", "\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()[:max_chars]


# ===================================================================
# Deterministic extraction — tried before the LLM ever gets involved
# ===================================================================

def extract_with_selectors(store: str, html: str, url: str) -> dict:
    """
    Returns whatever fields could be read deterministically. Missing
    keys mean "not found here" — the caller decides whether to fall
    back to the LLM for those specific fields.
    """
    if store == "style_korean":
        return _parse_style_korean(html, url)
    return _parse_yes_style(html, url)


def _meta_content(soup: BeautifulSoup, property_name: str) -> Optional[str]:
    tag = soup.find("meta", attrs={"property": property_name}) or soup.find(
        "meta", attrs={"name": property_name}
    )
    content = tag.get("content") if tag else None
    return content.strip() if content else None


def _parse_style_korean(html: str, url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    fields: dict = {}

    title = _meta_content(soup, "og:title")
    if title:
        fields["productName"] = re.split(r"\s*\|\s*", title)[0].strip()

    price = _meta_content(soup, "product:price:amount")
    if price:
        try:
            fields["price"] = float(price)
        except ValueError:
            pass

    text = soup.get_text(separator="\n")
    weight_match = re.search(r"Gross Weight\s*\n?\s*([\d.]+)\s*g", text, re.IGNORECASE)
    if weight_match:
        fields["weight"] = float(weight_match.group(1))

    # Confirmed across every Time Deal product checked during development.
    fields["timeDeal"] = "timedeal" in url.lower()

    return fields


def _parse_yes_style(html: str, url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    print("=" * 60)
    print("YESSTYLE PARSER")
    fields: dict = {}

    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue

        candidates = data if isinstance(data, list) else [data]
        for candidate in candidates:
            if not isinstance(candidate, dict) or candidate.get("@type") != "Product":
                continue

            if candidate.get("name"):
                fields.setdefault("productName", candidate["name"])

            offers = candidate.get("offers")
            if isinstance(offers, dict) and offers.get("price"):
                try:
                    fields.setdefault("price", float(offers["price"]))
                except (TypeError, ValueError):
                    pass

            weight = candidate.get("weight")
            if isinstance(weight, dict) and weight.get("value"):
                try:
                    fields.setdefault("weight", float(weight["value"]))
                except (TypeError, ValueError):
                    pass
                  
    print("After JSON-LD:", fields)
    if "productName" not in fields:
        title = _meta_content(soup, "og:title")
        if title:
            fields["productName"] = re.split(r"\s*\|\s*", title)[0].strip()

    if "price" not in fields:
        price = _meta_content(soup, "product:price:amount")
        if price:
            try:
                fields["price"] = float(price)
            except ValueError:
                pass

   print("After OG:", fields)
 
    # YesStyle marks non-eligible items with a specific disclaimer line
    # near the coupon/notes section (e.g. "Coupons offering a percentage
    # discount (e.g., 10% off) cannot be used with this product."). When a
    # product IS eligible, nothing is shown there at all — so eligibility
    # defaults to true and only flips to false when that disclaimer text
    # is present on the page.
    flat_text = re.sub(r"\s+", " ", soup.get_text(separator=" "))
    if re.search(r"coupons?.{0,200}?cannot be used with this product", flat_text, re.IGNORECASE):
        fields["eligibleForCode"] = False
    else:
        fields["eligibleForCode"] = True
      
    print("Final selector fields:", fields)
    print("=" * 60)

    return fields
