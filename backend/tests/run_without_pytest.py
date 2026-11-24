"""Fallback runner: `python -m tests.run_without_pytest` (pytest is preferred when installed)."""
import importlib
import pkgutil
import sys
import traceback

import tests

failed = 0
for m in pkgutil.iter_modules(tests.__path__):
    if not m.name.startswith("test_"):
        continue
    mod = importlib.import_module(f"tests.{m.name}")
    for name in sorted(dir(mod)):
        if name.startswith("test_") and callable(getattr(mod, name)):
            try:
                getattr(mod, name)()
                print(f"PASS {m.name}::{name}")
            except Exception:
                failed += 1
                print(f"FAIL {m.name}::{name}")
                traceback.print_exc()
print("\nfailures:", failed)
sys.exit(1 if failed else 0)
