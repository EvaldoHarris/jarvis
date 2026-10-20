import asyncio
import sys
import unittest
from unittest.mock import AsyncMock, patch

from dashboard import server as dashboard


class DashboardStartupTests(unittest.IsolatedAsyncioTestCase):
    async def test_consoleless_startup_configures_uvicorn(self):
        instance = dashboard.DashboardServer()
        with patch.object(dashboard, "PORT", 0), \
                patch.object(dashboard, "_ensure_network_access"), \
                patch.object(instance, "_ssl_enabled", return_value=False), \
                patch.object(dashboard.uvicorn.Server, "serve", new_callable=AsyncMock) as serve, \
                patch.object(sys, "stdout", None), patch.object(sys, "stderr", None):
            await instance.serve()
        self.assertEqual(instance._bind_error, "")
        self.assertIsNotNone(instance._server)
        self.assertFalse(instance._server.config.use_colors)
        serve.assert_awaited_once()

    async def test_startup_exception_is_available_to_remote_dialog(self):
        instance = dashboard.DashboardServer()
        with patch.object(instance, "_serve", side_effect=ValueError("formatter failure")):
            await instance.serve()
        self.assertIn("ValueError", instance._bind_error)

    async def test_uvicorn_system_exit_does_not_stop_the_assistant(self):
        instance = dashboard.DashboardServer()
        with patch.object(instance, "_serve", side_effect=SystemExit(1)):
            await instance.serve()
        self.assertIn("SystemExit", instance._bind_error)

    async def test_cancellation_is_not_swallowed(self):
        instance = dashboard.DashboardServer()
        with patch.object(instance, "_serve", side_effect=asyncio.CancelledError):
            with self.assertRaises(asyncio.CancelledError):
                await instance.serve()


if __name__ == "__main__":
    unittest.main()
