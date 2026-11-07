"""Multi-client web controller for the t.racks DSP 408."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("dsp408-multiui")
except PackageNotFoundError:  # pragma: no cover - running from a source tree without install
    __version__ = "0.0.0"

__all__ = ["__version__"]
