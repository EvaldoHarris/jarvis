from types import SimpleNamespace
from core.appidentity import exact_candidates


def test_tab_title_and_similar_executable_are_not_program_identity():
    matches = [SimpleNamespace(name="chrome.exe", titles=["Discord"]),
               SimpleNamespace(name="DiscordCanary.exe", titles=["Discord"]),
               SimpleNamespace(name="Discord.exe", titles=["Friends"])]
    assert exact_candidates("Discord", matches) == [matches[2]]


def test_alias_resolves_executable_without_using_window_title():
    code = SimpleNamespace(name="Code.exe")
    assert exact_candidates("Visual Studio Code", [code]) == [code]
    assert exact_candidates("Chrome", [SimpleNamespace(name="msedgewebview2.exe")]) == []
