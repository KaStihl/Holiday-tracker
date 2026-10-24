import importlib

from adapters import ADAPTERS
from config import CONFIG


def test_every_adapter_has_the_interface_and_valid_deeplinks():
    assert ADAPTERS[:2] == ["invia", "satur"]
    for name in ADAPTERS:
        mod = importlib.import_module(f"adapters.{name}")
        assert mod.NAME and mod.HOME.startswith("https://")
        links = mod.deeplinks(CONFIG)
        assert links, name
        for d in links:
            assert d["transport"] in ("flight", "car") and d["label"] and d["url"].startswith("https://"), d
        if getattr(mod, "DEEPLINK_ONLY", False):
            assert mod.search(CONFIG) == []
