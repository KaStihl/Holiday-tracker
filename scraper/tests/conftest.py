import os
import sys
from pathlib import Path

# Tests run against a pinned copy of the settings, so editing nastavenia.yml on GitHub never breaks them.
os.environ["DOVOLENKA_SETTINGS"] = str(Path(__file__).parent / "fixtures" / "nastavenia_test.yml")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
