import unittest
from unittest.mock import AsyncMock, patch

from scraper import (
    RegionalPricingError, detect_store, extract_with_selectors, fetch_page_html,
)


URL = "https://www.yesstyle.com/en/serum/info.html/pid.1126934079"


def product_html(destination="Kuwait", selling_price="US$\u00a010.71"):
    return f'''<meta property="og:title" content="KSECRET Serum | YesStyle">
    <meta property="product:price:amount" content="14.30">
    <script type="application/ld+json">{{"@type":"Product",
    "name":"KSECRET Serum","offers":{{"price":14.30,"priceCurrency":"USD"}}}}</script>
    <span class="productDetailPage-module-scss-module__dKBM_W__sellingPrice">{selling_price}</span>
    <del>US$ 16.48</del><h6><span>Shipping to {destination}</span></h6>
    <a>Coupons offering a percentage discount cannot be used with this product.</a>
    <a>Recommended product US$ 4.62</a>'''


class RegionalPriceTests(unittest.TestCase):
    def test_kuwait_sale_price_overrides_default_metadata(self):
        fields = extract_with_selectors("yes_style", product_html(), URL)
        self.assertEqual(fields["price"], 10.71)
        self.assertFalse(fields["eligibleForCode"])

    def test_wrong_or_missing_destination_is_rejected(self):
        for destination in ("United States", "Egypt", ""):
            with self.subTest(destination=destination), self.assertRaises(RegionalPricingError):
                extract_with_selectors("yes_style", product_html(destination), URL)

    def test_non_usd_missing_range_or_zero_price_is_rejected(self):
        for price in ("KWD 3.29", "", "US$ 0.00", "US$ 10.71–12.00"):
            with self.subTest(price=price), self.assertRaises(RegionalPricingError):
                extract_with_selectors("yes_style", product_html(selling_price=price), URL)

    def test_metadata_alone_is_never_used_for_yesstyle(self):
        html = '<meta property="product:price:amount" content="14.30">'
        with self.assertRaises(RegionalPricingError):
            extract_with_selectors("yes_style", html, URL)

    def test_stylekorean_extraction_is_preserved(self):
        html = '''<meta property="og:title" content="Cream | StyleKorean">
        <meta property="product:price:amount" content="12.50">Gross Weight\n120 g'''
        fields = extract_with_selectors("style_korean", html, "https://www.stylekorean.com/timedeal-cream")
        self.assertEqual((fields["price"], fields["weight"], fields["timeDeal"]), (12.5, 120, True))

    def test_store_detection_requires_real_store_domain(self):
        self.assertEqual(detect_store(URL), "yes_style")
        self.assertIsNone(detect_store("https://yesstyle.com.example.org/product"))
        self.assertIsNone(detect_store("file://yesstyle.com/product"))


class FetchTests(unittest.IsolatedAsyncioTestCase):
    async def test_yesstyle_always_uses_regional_browser_flow(self):
        with patch("scraper._fetch_with_playwright", new_callable=AsyncMock) as browser:
            browser.return_value = product_html()
            with patch("scraper.httpx.AsyncClient") as client:
                await fetch_page_html(URL)
            client.assert_not_called()
            browser.assert_awaited_once_with(URL, kuwait_pricing=True)

    async def test_region_failure_is_not_replaced_with_plain_http(self):
        with patch("scraper._fetch_with_playwright", new_callable=AsyncMock) as browser:
            browser.side_effect = RegionalPricingError("Region unavailable")
            with self.assertRaises(RegionalPricingError):
                await fetch_page_html(URL)


if __name__ == "__main__":
    unittest.main()
