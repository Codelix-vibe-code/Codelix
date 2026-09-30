"""Backward-compatible import namespace; use :mod:`vybelix` for new code."""

import importlib
import pkgutil
import sys
import vybelix

__version__ = vybelix.__version__
__path__ = [str(__import__("pathlib").Path(vybelix.__file__).resolve().parent)]

# Alias legacy submodule names to the same module objects so monkeypatches and
# class identity remain consistent during upgrades.
for _item in pkgutil.walk_packages(vybelix.__path__, prefix="vybelix."):
    if _item.name.endswith(".__main__"):
        continue
    _module = importlib.import_module(_item.name)
    sys.modules["codelix" + _item.name[len("vybelix"):]] = _module
