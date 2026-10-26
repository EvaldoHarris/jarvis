"""Real Playwright regression tests on local fixtures; no hotel requests or AI calls."""
import unittest
from unittest.mock import AsyncMock

from playwright.async_api import async_playwright
from actions import browser_control as browser


class BrowserClickTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        browser._load_playwright()
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=True, channel="msedge")
        self.context = await self.browser.new_context()
        await self.context.route("https://hotel.test/**", lambda route: route.fulfill(
            content_type="text/html", body="<html><body><h1>Golden Garden: site de destino</h1></body></html>"))
        self.page = await self.context.new_page()
        self.session = object.__new__(browser._BrowserSession)
        self.session._page = self.page
        self.session._context = self.context
        self.session._launch = AsyncMock()
        self.session.inspect_page = AsyncMock(return_value="Destino conferido visualmente")

    async def asyncTearDown(self):
        await self.browser.close()
        await self.playwright.stop()

    async def test_heading_is_ignored_and_partial_link_name_is_clicked(self):
        await self.page.set_content('<h2>Golden Garden</h2><p>Golden Garden House (Hostel)</p>'
                                    '<a href="https://hotel.test/">Golden Garden Hostel</a>')
        result = await self.session.click(text="Golden Garden")
        self.assertEqual(self.session._page.url, "https://hotel.test/", result)
        self.assertIn("status=done", result)
        self.session.inspect_page.assert_awaited_once()

    async def test_new_tab_is_adopted_and_subsequent_reads_use_destination(self):
        await self.page.set_content('<a target="_blank" href="https://hotel.test/">Golden Garden Hostel</a>')
        result = await self.session.smart_click("Golden Garden")
        self.assertIsNot(self.session._page, self.page, result)
        self.assertEqual(self.session._page.url, "https://hotel.test/")
        self.assertEqual((await self.session.get_url()), "https://hotel.test/")
        self.assertIn("new_tab=true", result)

    async def test_ambiguous_links_are_not_clicked(self):
        await self.page.set_content('<a href="https://hotel.test/1">Golden Garden site</a>'
                                    '<a href="https://hotel.test/2">Golden Garden Booking</a>')
        result = await self.session.click(text="Golden Garden")
        self.assertIn("status=failed", result)
        self.assertEqual(self.page.url, "about:blank")
        self.session.inspect_page.assert_not_awaited()

    async def test_blocked_popup_uses_real_dom_destination_without_second_click(self):
        await self.page.set_content('<h2>Golden Garden</h2>'
            '<a target="_blank" href="https://hotel.test/" '
            'onclick="event.preventDefault()">Golden Garden Hostel</a>')
        result = await self.session.click(text="Golden Garden")
        self.assertEqual(self.session._page.url, "https://hotel.test/", result)
        self.assertIn('method=destination_from_dom', result)
        self.session.inspect_page.assert_awaited_once()

    async def test_script_links_are_not_replaced_by_invented_navigation(self):
        await self.page.set_content('<button onclick="document.body.dataset.clicked=1">Confirmar</button>')
        result = await self.session.click(text="Confirmar")
        self.assertEqual(self.page.url, "about:blank")
        self.assertEqual(await self.page.locator("body").get_attribute("data-clicked"), "1")
        self.assertNotIn('method=destination_from_dom', result)
        self.assertIn('status=unverified', result)
        self.assertNotIn('status=done', result)

    async def test_verify_checks_visible_exact_text_without_clicking(self):
        await self.page.set_content('<button onclick="document.body.dataset.clicked=1">Concluido</button>')
        result = await self.session.verify("Concluido")
        self.assertIn('status=done', result)
        self.assertIn('verified_scope=visible_text_only', result)
        self.assertIsNone(await self.page.locator('body').get_attribute('data-clicked'))

    async def test_verify_rejects_hidden_and_partial_evidence(self):
        await self.page.set_content('<p hidden>Concluido</p><p>Quase concluido</p>')
        result = await self.session.verify("Concluido")
        self.assertIn('status=unverified', result)

    async def test_links_exposes_actual_names_and_destinations(self):
        await self.page.set_content('<h2>Golden Garden</h2>'
                                    '<a href="https://hotel.test/">Golden Garden Hostel</a>')
        result = await self.session.links()
        self.assertIn('"name": "Golden Garden Hostel"', result)
        self.assertIn('https://hotel.test/', result)
        self.assertNotIn('<h2>', result)


if __name__ == "__main__":
    unittest.main()
