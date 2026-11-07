"""Protocol-accurate simulated DSP 408 (docs/SPEC.md §4.5)."""

from dsp408_multiui.simulator.device import SimulatedDevice
from dsp408_multiui.simulator.faults import Faults
from dsp408_multiui.simulator.scenarios import SCENARIOS, apply_scenario
from dsp408_multiui.simulator.server import SecondClient, SimulatorServer

__all__ = [
    "SCENARIOS",
    "Faults",
    "SecondClient",
    "SimulatedDevice",
    "SimulatorServer",
    "apply_scenario",
]
