"""Protocol-accurate simulated DSP 408 (docs/ARCHITECTURE.md §5)."""

from tracks_dsp_controller.simulator.device import SimulatedDevice
from tracks_dsp_controller.simulator.faults import Faults
from tracks_dsp_controller.simulator.scenarios import SCENARIOS, apply_scenario
from tracks_dsp_controller.simulator.server import SecondClient, SimulatorServer

__all__ = [
    "SCENARIOS",
    "Faults",
    "SecondClient",
    "SimulatedDevice",
    "SimulatorServer",
    "apply_scenario",
]
