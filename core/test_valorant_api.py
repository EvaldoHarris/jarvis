import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests

from core import valorant_api as api
from core.plugin_loader import discover_plugins
from plugins import valorant


class ValorantTests(unittest.TestCase):
    def setUp(self):
        self.values = {"api_key": "private-key", "riot_id": "Meu Nome#BR1", "region": "br", "platform": "pc"}

    def response(self, data, status=200):
        return Mock(status_code=status, json=Mock(return_value={"status": status, "data": data}))

    @patch.object(api.requests, "get")
    def test_rank_auth_encoding_and_current_schema(self, get):
        get.return_value = self.response({"current": {"tier": {"name": "Gold 1"}, "rr": 24}})
        result = api.query(self.values)
        self.assertEqual(result["current"]["rr"], 24)
        args, kwargs = get.call_args
        self.assertEqual(args[0], api.BASE_URL + "/v3/mmr/br/pc/Meu%20Nome/BR1")
        self.assertEqual(kwargs["headers"]["Authorization"], "private-key")
        self.assertFalse(kwargs["allow_redirects"])
        self.assertEqual(kwargs["timeout"], (5, 20))
        self.assertNotIn("private-key", args[0])

    @patch.object(api.requests, "get")
    def test_match_summary_targets_requested_player(self, get):
        match = {"metadata": {"map": {"name": "Ascent"}}, "players": [
            {"name": "Other", "tag": "BR1", "stats": {"kills": 99}},
            {"name": "meu nome", "tag": "br1", "team_id": "Red", "stats": {"kills": 12}},
        ], "teams": [{"team_id": "Red", "won": False}]}
        get.return_value = self.response([match, match])
        result = api.query(self.values, "matches", count=1)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["stats"]["kills"], 12)
        self.assertFalse(result[0]["team"]["won"])
        self.assertEqual(get.call_args.kwargs["params"], {"size": 1})

    @patch.object(api.requests, "get")
    def test_missing_player_does_not_use_someone_elses_stats(self, get):
        get.return_value = self.response([{"players": [{"name": "Other", "tag": "XX"}]}])
        result = api.query(self.values, "matches")[0]
        self.assertFalse(result["player_found"])
        self.assertIsNone(result["stats"])

    @patch.object(api.requests, "get")
    def test_invalid_settings_never_make_request(self, get):
        for changes in ({"api_key": ""}, {"riot_id": "NoTag"}, {"region": "invalid"}, {"platform": "bad"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                api.query(self.values | changes)
        for count in (0, 11, True, 2.5, "invalid"):
            with self.subTest(count=count), self.assertRaises(ValueError):
                api.query(self.values, "matches", count=count)
        get.assert_not_called()

    @patch.object(api.requests, "get")
    def test_errors_do_not_expose_response_body_or_retry(self, get):
        for status in (301, 401, 403, 404, 429, 503):
            get.reset_mock()
            get.return_value = self.response({"secret": "private-key"}, status)
            with self.subTest(status=status), self.assertRaises(ValueError) as caught:
                api.query(self.values)
            self.assertNotIn("private-key", str(caught.exception))
            get.assert_called_once()

    @patch.object(api.requests, "get")
    def test_timeout_is_sanitized(self, get):
        get.side_effect = requests.Timeout("private-key")
        with self.assertRaises(ValueError) as caught:
            api.query(self.values)
        self.assertNotIn("private-key", str(caught.exception))

    @patch.object(api.requests, "get")
    def test_invalid_json_and_api_error(self, get):
        get.return_value = Mock(status_code=200, json=Mock(side_effect=ValueError("bad")))
        with self.assertRaises(ValueError):
            api.query(self.values)
        get.return_value = Mock(status_code=200, json=Mock(return_value={"status": 400, "data": {}}))
        with self.assertRaises(ValueError):
            api.query(self.values)

    @patch.object(valorant, "get_plugin_config")
    @patch.object(valorant, "query")
    def test_tool_result_labels_untrusted_data_and_redacts_key(self, query, config):
        config.return_value = self.values
        query.return_value = {"name": "private-key"}
        text = valorant.run({"action": "account"})
        self.assertIn("status=done", text)
        self.assertIn("[redacted]", text)
        self.assertNotIn("private-key", text)

    @patch.object(valorant, "get_plugin_config")
    @patch.object(valorant, "query")
    def test_status_is_local_and_does_not_claim_authentication(self, query, config):
        config.return_value = self.values
        text = valorant.run({"action": "status"})
        self.assertIn("connection_verified=false", text)
        self.assertNotIn("private-key", text)
        query.assert_not_called()

    @patch.object(valorant, "query")
    def test_settings_connection_button(self, query):
        query.return_value = {"name": "Meu Nome", "tag": "BR1"}
        ok, text = valorant._test(self.values)
        self.assertTrue(ok)
        self.assertIn("Meu Nome#BR1", text)
        query.assert_called_once_with(self.values, "account")

    def test_discovery_exposes_password_field_and_tool(self):
        source = Path(valorant.__file__).read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, "valorant.py").write_text(source, encoding="utf-8")
            registry = discover_plugins(Path(folder), set(), logger=lambda _: None)
            self.assertTrue(registry.has("valorant"))
            sections = registry.settings_schemas()
            self.assertEqual(sections[0]["namespace"], "valorant")
            field = next(f for f in sections[0]["fields"] if f["key"] == "api_key")
            self.assertEqual(field["type"], "password")


if __name__ == "__main__":
    unittest.main()
