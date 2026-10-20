"""Check capability rendering without importing the desktop application."""
import ast
import unittest
from pathlib import Path


class CapabilityPromptTests(unittest.TestCase):
    def render(self, declarations):
        source = Path(__file__).resolve().parents[1] / "main.py"
        tree = ast.parse(source.read_text(encoding="utf-8-sig"))
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                        and n.name == "_describe_tools")
        namespace = {}
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), "exec"), namespace)
        return namespace["_describe_tools"](declarations)

    def test_named_click_contract_survives_description_truncation(self):
        rendered = self.render([{"name": "computer_control", "description": "x" * 300}])
        self.assertIn("action=screen_click", rendered)
        self.assertIn("target=the exact name", rendered)
        self.assertIn("do not need to know its coordinates", rendered)

    def test_absent_control_tool_does_not_claim_mouse_access(self):
        rendered = self.render([{"name": "weather_report", "description": "Weather"}])
        self.assertNotIn("screen_click", rendered)
        self.assertNotIn("operate the mouse", rendered)


if __name__ == "__main__":
    unittest.main()
