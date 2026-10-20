import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from actions import browser_control as browser
from core import gemini


class BrowserVisionTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_encodes_query_and_observes_result_page(self):
        session = object.__new__(browser._BrowserSession)
        session.go_to = AsyncMock(return_value="status=done")
        session.inspect_page = AsyncMock(return_value="visual results")
        result = await session.search("café & chá + pão?")
        self.assertIn("caf%C3%A9+%26+ch%C3%A1+%2B+p%C3%A3o%3F", session.go_to.call_args.args[0])
        session.inspect_page.assert_awaited_once()
        self.assertIn("visual results", result)

    async def test_failed_navigation_does_not_analyze_previous_page(self):
        session = object.__new__(browser._BrowserSession)
        session.go_to = AsyncMock(return_value="status=failed")
        session.inspect_page = AsyncMock()
        await session.search("query")
        session.inspect_page.assert_not_awaited()

    async def test_vision_receives_playwright_screenshot_and_dom(self):
        session = object.__new__(browser._BrowserSession)
        page = Mock(url="https://example.test/search")
        page.screenshot = AsyncMock(return_value=b"page image")
        page.locator.return_value.inner_text = AsyncMock(return_value="Resultado visível")
        session._get_page = AsyncMock(return_value=page)
        session.links = AsyncMock(return_value='[{"name":"Golden Garden Hostel","href":"https://hotel.test/"}]')
        with patch.object(gemini, "call", return_value=SimpleNamespace(text="Resultado conferido")) as ai:
            result = await session.inspect_page("Confira a pesquisa")
        content = ai.call_args.args[0]
        self.assertEqual(content[0].inline_data.data, b"page image")
        self.assertIn("Resultado visível", content[1])
        self.assertIn("Resultado conferido", result)
        self.assertFalse(page.screenshot.call_args.kwargs["full_page"])

    async def test_unavailable_vision_does_not_claim_confirmation(self):
        session = object.__new__(browser._BrowserSession)
        page = Mock(url="https://example.test/")
        page.screenshot = AsyncMock(side_effect=RuntimeError("screenshot failed"))
        session._get_page = AsyncMock(return_value=page)
        result = await session.inspect_page()
        self.assertIn("status=unverified", result)


class BrowserRoutingTests(unittest.TestCase):
    def test_first_search_uses_playwright_without_native_launch(self):
        registry = Mock()
        session = registry.get.return_value
        registry.pop_native_url.return_value = ""
        session.search = AsyncMock(return_value="Playwright and vision result")
        session.run.side_effect = lambda coro, **kwargs: asyncio.run(coro)
        with patch.object(browser, "_registry", registry), patch.object(browser, "_open_native") as native:
            result = browser.browser_control({"action": "search", "query": "teste"})
        registry.get.assert_called_once_with(None)
        native.assert_not_called()
        session.search.assert_awaited_once_with("teste", "google")
        self.assertEqual(result, "Playwright and vision result")


if __name__ == "__main__":
    unittest.main()
