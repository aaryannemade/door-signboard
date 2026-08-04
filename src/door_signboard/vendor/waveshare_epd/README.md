# Waveshare Driver Provenance

These files are a minimal Raspberry Pi-only adaptation of the Waveshare
3.52-inch Python demo distributed in the `waveshareteam/e-Paper` repository:

<https://github.com/waveshareteam/e-Paper>

Source snapshot:

- `epd3in52.py`, V1.0, 2022-07-20, SHA-256
  `eb79c2f618ff63c679114db77eb6d0f3626b9ea4230379554af27840e0775653`
- `epdconfig.py`, V1.2, 2022-10-29, SHA-256
  `f2ac0bd9828bb7bcb3371b9ad5fdb49de565618177e71592106d799f843d62f1`
- Snapshot package changelog dated 2024-08-08.

The original files are available in this repository's ignored development
snapshot under `tmp/e-paper/RaspberryPi_JetsonNano/python/lib/waveshare_epd/`.

Adaptations:

- removed Jetson Nano and Sunrise X3 backends;
- removed unused test patterns and the discouraged DU waveform;
- delayed GPIO/SPI construction until `module_init()`;
- added a timeout to the active-low BUSY wait;
- separated deep-sleep commands from resource cleanup.

The original permission notice is retained in each adapted source file.
