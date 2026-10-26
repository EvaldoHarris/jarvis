"""Local Playwright fixtures for calendars, repeated cards and stale DOM targets."""
import time
import unittest
from unittest.mock import AsyncMock

from playwright.async_api import async_playwright
from actions import browser_control as browser


class BrowserControlsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        browser._load_playwright()
        self.pw = await async_playwright().start()
        self.browser = await self.pw.chromium.launch(headless=True, channel='msedge')
        context = await self.browser.new_context()
        self.page = await context.new_page()
        self.session = object.__new__(browser._BrowserSession)
        self.session._page = self.page
        self.session._context = context
        self.session._launch = AsyncMock()
        self.session.inspect_page = AsyncMock(return_value='fixture observation')

    async def asyncTearDown(self):
        await self.browser.close()
        await self.pw.stop()

    async def observe(self, name):
        await self.session.controls()
        matches = [key for key, (_, row) in self.session._control_targets.items() if row['name'] == name]
        self.assertEqual(len(matches), 1)
        return matches[0]

    async def test_date_textbox_opens_calendar_and_exposes_full_dates(self):
        await self.page.set_content('''<input aria-label="Fazer check-in" readonly onclick="document.querySelector('section').hidden=false">
            <section hidden><div role="gridcell" data-iso="2026-12-19" onclick="document.querySelector('input').value='19/12/2026'">
            <div role="button"><span aria-label="19 de dezembro de 2026">19</span></div></div></section>''')
        result = await self.session.click(text='Fazer check-in')
        self.assertNotIn('status=failed', result)
        key = await self.observe('19 de dezembro de 2026')
        row = self.session._control_targets[key][1]
        self.assertEqual(row['date'], '2026-12-19')
        await self.session.click(element_id=key)
        self.assertEqual(await self.page.locator('input').input_value(), '19/12/2026')

    async def test_repeated_price_labels_use_hotel_context_and_hover_without_click(self):
        await self.page.set_content('''<article><h2>Hotel Ipora</h2><button onmousemove="document.body.dataset.hovered='Ipora'" onclick="document.body.dataset.clicked=1">Ver precos</button></article>
            <article><h2>Hotel Universitario</h2><button>Ver precos</button></article>''')
        ambiguous = await self.session.hover(text='Ver precos')
        self.assertIn('status=failed', ambiguous)
        await self.session.controls()
        key = next(k for k, (_, row) in self.session._control_targets.items()
                   if row['name'] == 'Ver precos' and 'Hotel Ipora' in row['context'])
        result = await self.session.hover(element_id=key)
        self.assertIn('status=done', result)
        self.assertEqual(await self.page.locator('body').get_attribute('data-hovered'), 'Ipora')
        self.assertIsNone(await self.page.locator('body').get_attribute('data-clicked'))
        self.assertIn('status=failed', await self.session.hover(element_id=key))

    async def test_changed_context_or_replaced_node_is_rejected(self):
        for change in ["document.querySelector('h2').textContent='Other hotel'",
                       "document.querySelector('button').outerHTML='<button>Ver precos</button>'"]:
            await self.page.set_content('<article><h2>Hotel Ipora</h2><button>Ver precos</button></article>')
            key = await self.observe('Ver precos')
            await self.page.evaluate(change)
            result = await self.session.hover(element_id=key)
            self.assertIn('status=failed', result)

    async def test_expired_ids_are_rejected(self):
        await self.page.set_content('<button>Ver precos</button>')
        key = await self.observe('Ver precos')
        self.session._controls_at = time.monotonic() - 46
        self.assertIn('status=failed', await self.session.hover(element_id=key))

    async def test_unique_field_is_filled_and_value_verified(self):
        await self.page.set_content('<label>Destino<input></label><input type="password" aria-label="Senha" value="secret">')
        key = await self.observe('Destino')
        self.assertFalse(any(row['name'] == 'Senha' for _, row in self.session._control_targets.values()))
        result = await self.session.type_text(text='Ubatuba', element_id=key)
        self.assertIn('status=done', result)
        self.assertEqual(await self.page.locator('input').first.input_value(), 'Ubatuba')

    async def test_duplicate_selector_does_not_type_into_first_field(self):
        await self.page.set_content('<input><input>')
        result = await self.session.type_text(selector='input', text='19/12/2026')
        self.assertIn('status=failed', result)
        self.assertEqual(await self.page.locator('input').first.input_value(), '')


if __name__ == '__main__':
    unittest.main()
