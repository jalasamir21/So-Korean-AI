"""
app.py

FastAPI entrypoint. The only endpoint the frontend calls:

    POST /api/analyze   { "url": "https://...", "weight": 120 }
      -> { store, productName, price, weight, timeDeal,
           eligibleForCode, totalEGP, needsWeight }

Note what's deliberately NOT in that response: shipping, service fee,
discount rate, or profit margin. Those live only in calculator.py.

YesStyle never exposes a reliable weight on the page (no labelled spec
line, no structured data for it), so it's never left to the LLM to
guess. The first call for a YesStyle link comes back with
needsWeight: true and every other field already filled in; the
frontend then asks the person for the weight (or points them at the
matching StyleKorean listing to read it off there) and re-calls this
same endpoint with that weight attached.
"""

from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from scraper import (
    detect_store,
    fetch_page_html,
    extract_visible_text,
    extract_with_selectors,
    REQUIRED_FIELDS_BY_STORE,
)
from agent import extract_product_fields, ExtractionError
from calculator import calculate_total, CalculationError

app = FastAPI(title="So Korean AI Order Analyzer")

# Tighten allow_origins to your deployed frontend domain before going live.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://so-korean-ai.vercel.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AnalyzeRequest(BaseModel):
    url: str
    weight: Optional[float] = None  # grams — supplied by the user when asked (YesStyle only)


class AnalyzeResponse(BaseModel):
    store: str
    productName: str
    price: float
    weight: float
    timeDeal: Optional[bool] = None
    eligibleForCode: Optional[bool] = None
    totalEGP: float
    needsWeight: bool = False


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/analyze", response_model=AnalyzeResponse)
async def analyze(payload: AnalyzeRequest):
    store = detect_store(payload.url)
    if not store:
        raise HTTPException(400, "Link must be a StyleKorean or YesStyle product page.")

    try:
        html = await fetch_page_html(payload.url)
    except Exception:
        raise HTTPException(502, "Couldn't reach that product page. Please check the link.")

    # Deterministic pass first — meta tags, JSON-LD, labelled spec text.
    fields = extract_with_selectors(store, html, payload.url)

    # YesStyle has no reliable weight signal anywhere on the page, so it's
    # deliberately left out of what the LLM is asked to fill in — guessing
    # shipping weight would make the total unreliable. It's handled below
    # by asking the person instead.
    llm_required = set(REQUIRED_FIELDS_BY_STORE[store])
    if store == "yes_style":
        llm_required.discard("weight")

    missing = llm_required - fields.keys()

    if missing:
        # The LLM only ever fills gaps — it can never override a field
        # the deterministic parser already found.
        try:
            page_text = extract_visible_text(html)
            llm_fields = extract_product_fields(store, page_text)
            print("LLM returned:", llm_fields)
        except ExtractionError as e:
            raise HTTPException(502, f"Couldn't read that product page: {e}")

        for key in missing:
            if key in llm_fields:
                fields[key] = llm_fields[key]

    still_missing = llm_required - fields.keys()
    if still_missing:
        raise HTTPException(
            502, f"Couldn't determine: {', '.join(sorted(still_missing))} for that product."
        )

    if store == "yes_style" and "weight" not in fields:
        if payload.weight is not None and payload.weight > 0:
            fields["weight"] = payload.weight
        else:
            # Everything else is known — pause here and let the frontend
            # collect a weight before any pricing math runs.
            return AnalyzeResponse(
                store=store,
                productName=fields["productName"],
                price=fields["price"],
                weight=0,
                timeDeal=None,
                eligibleForCode=fields.get("eligibleForCode"),
                totalEGP=0,
                needsWeight=True,
            )

    try:
        total_egp = calculate_total(
            store=store,
            price=fields["price"],
            weight=fields["weight"],
            time_deal=fields.get("timeDeal", False),
            eligible_for_code=fields.get("eligibleForCode", False),
        )
    except CalculationError as e:
        raise HTTPException(422, str(e))

    return AnalyzeResponse(
        store=store,
        productName=fields["productName"],
        price=fields["price"],
        weight=fields["weight"],
        timeDeal=fields.get("timeDeal"),
        eligibleForCode=fields.get("eligibleForCode"),
        totalEGP=total_egp,
        needsWeight=False,
    )
