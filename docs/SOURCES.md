# Sources

Prior reverse-engineering work this project builds on. See [PROTOCOL.md](PROTOCOL.md) §0 for how
much each source is trusted.

| Project | Device | Transport | License | Notes |
|---|---|---|---|---|
| https://github.com/Aeternitaas/dsp-408-ui | DSP 408 | TCP 9761 | GPL-3.0 | Flutter app; the only source tested on a DSP 408 |
| https://github.com/juli303/t-dsp-ui | DSP 408 | TCP 9761 | GPL-3.0 | Identical fork of dsp-408-ui |
| https://github.com/FlexiFlizz/t.racks-DSP-control | DSP 206 | TCP + USB HID | GPL-3.0 | Python driver and simulator; source for delay, phase, dynamics and slopes |
| https://github.com/IMBArator/miniDSP-Linux | DSP 4x4 Mini | USB HID | GPL-3.0 | Most rigorous protocol documentation of the family |

## Reuse rules

- GPL-3.0 code may be combined with this AGPL-3.0 project (GPLv3 §13 / AGPLv3 §13).
- Any copied code or test vector keeps its original copyright notice, and this file must list
  where it came from:

| File in this repo | Origin | Notes |
|---|---|---|
| _none yet_ | | |
