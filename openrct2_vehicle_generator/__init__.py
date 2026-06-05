""" """

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("OpenRCT2-VehicleGenerator")
except PackageNotFoundError:  # pragma: no cover - source tree without an install
    __version__ = "0.0.0"
