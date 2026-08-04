# Display Driver Implementation Plan

## Goal

Connect the existing image renderer and Home Assistant WebSocket client to the
Waveshare 3.52-inch monochrome e-paper display attached to the Raspberry Pi Zero
W over SPI.

The driver must update the physical panel reliably, avoid unnecessary
refreshes, put the panel into deep sleep after every update, and keep all
Waveshare-specific behavior isolated from scenes and Home Assistant code.

## 1. Module Structure

Add:

```text
src/door_signboard/
├── display_driver.py
└── vendor/
    └── waveshare_epd/
        ├── __init__.py
        ├── epd3in52.py
        └── epdconfig.py
```

Vendor only the required Waveshare files, preserving their license headers and
recording their source and version. Production code must not depend on the
ignored `tmp/` directory or a system-wide Waveshare installation.

## 2. Driver Interface

```python
class Waveshare3in52DisplayDriver:
    def show(self, image: Image.Image, *, force: bool = False) -> bool: ...
    def clear(self) -> None: ...
    def close(self) -> None: ...
```

`show()` returns:

- `True` when the panel was refreshed;
- `False` when an identical image was skipped.

The driver remains independent of Home Assistant, WebSockets, scenes, and text
content.

## 3. Image Validation

Before accessing hardware:

- require Pillow mode `1`;
- accept landscape images sized 360 x 240;
- optionally accept native portrait images sized 240 x 360;
- reject every other mode and dimension;
- calculate a SHA-256 digest of the validated image;
- skip duplicate images unless `force=True`.

The vendor's `getbuffer()` performs the landscape-to-native rotation.

## 4. Hardware Update Sequence

Use the demonstrated Waveshare API:

```python
epd.init()
buffer = epd.getbuffer(image)
epd.display(buffer)
epd.lut_GC()
epd.refresh()
epd.sleep()
```

Each update will:

1. Acquire an update lock.
2. Validate and hash the image.
3. Skip an unchanged image.
4. Initialize GPIO, SPI, and the panel.
5. Transfer the packed image buffer.
6. Select the recommended `lut_GC()` full-refresh waveform.
7. Refresh and wait for completion.
8. Record the digest only after success.
9. Put the panel into deep sleep.
10. Release GPIO and SPI resources.

Do not use `lut_DU()` in version one because Waveshare documents its poorer
visual quality and increased ghosting.

## 5. Busy-Pin Timeout

The vendor implementation can wait forever if the panel remains busy. Add a
thin `EPD` subclass or adapter that preserves the vendor protocol while imposing
a configurable busy timeout, initially 30 seconds.

A timeout will:

- raise `DisplayTimeoutError`;
- trigger hardware cleanup;
- leave the previous digest unchanged;
- prevent the Pi service from hanging indefinitely.

## 6. Error Handling

Define driver-specific exceptions:

```python
class DisplayDriverError(Exception): ...
class DisplayInitializationError(DisplayDriverError): ...
class DisplayTimeoutError(DisplayDriverError): ...
class InvalidDisplayImageError(DisplayDriverError): ...
```

On failure:

- attempt `epdconfig.module_exit(cleanup=True)`;
- preserve the original exception as the cause;
- do not report the Home Assistant revision as applied;
- allow a later desired revision to retry.

## 7. Deep Sleep And Panel Conditioning

The panel must not remain powered between updates. Call `epd.sleep()` after each
successful refresh.

The Waveshare demo performs a white refresh and sends `0x50 / 0x17` during
initial conditioning. Test this on the physical panel before making it part of
every update because clearing after every wake would double refresh time and
panel wear.

Compare these sequences on the Pi:

- direct `init()` followed by image refresh;
- vendor conditioning followed by image refresh;
- repeated wake, refresh, and sleep cycles.

Use the smallest sequence that produces reliable, clean updates.

## 8. Refresh Scheduling

Waveshare recommends approximately 180 seconds between full refreshes. The
application layer will:

- render Home Assistant changes immediately;
- retain only the newest pending revision;
- refresh immediately if the minimum interval has elapsed;
- otherwise wait and apply only the latest revision;
- report a revision as applied only after physical refresh succeeds.

The minimum interval will be configurable, with 180 seconds as the safe initial
default.

## 9. Preview And Hardware Modes

Refactor the orchestrator to support interchangeable image outputs:

```python
class ImageOutput(Protocol):
    def show(self, image: Image.Image) -> bool: ...
```

Implement:

- `PreviewImageOutput`, which writes `ha-preview.png`;
- `Waveshare3in52DisplayDriver`, which updates the panel.

CLI examples:

```bash
python -m door_signboard.main --output-mode preview
python -m door_signboard.main --output-mode hardware
```

Preview mode remains the default on non-Pi development machines. Importing the
application must never access GPIO or SPI.

## 10. Raspberry Pi Dependencies

Document Raspberry Pi OS installation for:

- `fonts-dejavu-core`;
- `python3-pil`;
- `python3-numpy`;
- `python3-gpiozero`;
- `spidev`;
- `websockets`.

Enable SPI and verify that `/dev/spidev0.0` exists. The service user will need
access to the Pi's SPI and GPIO-related groups.

## 11. Automated Tests

Use a fake Waveshare EPD implementation to verify:

- initialization and refresh call order;
- `getbuffer()` receives the validated image;
- `display()`, `lut_GC()`, `refresh()`, and `sleep()` ordering;
- invalid modes and dimensions are rejected before hardware access;
- duplicate images are skipped;
- `force=True` bypasses duplicate detection;
- failed refreshes do not update the digest;
- cleanup occurs after initialization or refresh failure;
- busy timeout raises the correct exception;
- concurrent updates cannot overlap;
- an applied revision is reported only after success;
- rapid revisions result in only the newest hardware update.

## 12. Physical Smoke Tests

Run directly on the Raspberry Pi:

1. Display a black-and-white orientation test image.
2. Confirm landscape rotation and pixel polarity.
3. Display each signboard scene.
4. Repeat initialize, refresh, and sleep cycles.
5. Test duplicate-image skipping.
6. Disconnect or miswire BUSY and confirm timeout recovery.
7. Restart the service and confirm reconnection to Home Assistant.
8. Change several entities quickly and confirm only the latest revision appears.
9. Verify the panel sleeps after every update.
10. Observe ghosting and decide whether startup conditioning is necessary.

## 13. Deployment Completion

After hardware validation:

- add a `systemd` service;
- start after networking is available;
- restart on failure;
- log through `journalctl`;
- gracefully report offline status;
- document installation, updates, and troubleshooting.

## Implementation Checklist

Implementation and desktop verification completed on 2026-08-04. Phase 5 and
the remaining Phase 6 verification items require the physical Raspberry Pi and
panel. Source provenance uses exact snapshot versions and SHA-256 hashes because
the supplied Waveshare snapshot does not contain upstream Git metadata.

### Phase 1: Driver Foundation

- [x] Record the exact Waveshare source snapshot hashes, versions, and license.
- [x] Vendor only `epd3in52.py`, `epdconfig.py`, and required package files.
- [x] Add `display_driver.py`.
- [x] Define the driver exception hierarchy.
- [x] Define the `ImageOutput` protocol.
- [x] Implement mode and dimension validation.
- [x] Implement deterministic image hashing.
- [x] Implement duplicate-refresh skipping and `force=True`.

### Phase 2: Hardware Lifecycle

- [x] Implement lazy Waveshare imports.
- [x] Implement panel initialization failure handling.
- [x] Implement `getbuffer()`, `display()`, `lut_GC()`, and `refresh()` ordering.
- [x] Implement deep sleep after successful refresh.
- [x] Implement GPIO/SPI cleanup after failures.
- [x] Implement explicit `clear()` behavior.
- [x] Implement serialized access with a lock.
- [x] Implement the busy-pin timeout.

### Phase 3: Application Integration

- [x] Extract `PreviewImageOutput` from the current preview renderer.
- [x] Make the orchestrator accept an `ImageOutput` implementation.
- [x] Add `--output-mode preview`.
- [x] Add `--output-mode hardware`.
- [x] Add configurable minimum refresh interval.
- [x] Coalesce revisions while waiting for the refresh interval.
- [x] Report applied status only after successful output.
- [x] Report driver errors without advancing the applied revision.
- [x] Keep preview mode safe on machines without GPIO or SPI.

### Phase 4: Automated Verification

- [x] Test all accepted and rejected image modes and sizes.
- [x] Test the exact vendor API call order.
- [x] Test successful digest updates.
- [x] Test duplicate skips.
- [x] Test forced refreshes.
- [x] Test initialization failures.
- [x] Test transfer and refresh failures.
- [x] Test timeout and cleanup behavior.
- [x] Test concurrent calls cannot overlap.
- [x] Test refresh scheduling and revision coalescing.
- [x] Run the complete existing renderer and WebSocket test suite.
- [x] Run the unit tests, Hassfest, and `nix flake check`.

### Phase 5: Raspberry Pi Validation

- [ ] Enable SPI on the Pi.
- [ ] Verify `/dev/spidev0.0` and physical wiring.
- [ ] Run the original Waveshare 3.52-inch demo.
- [ ] Display the orientation and polarity test image.
- [ ] Display all four production scenes.
- [ ] Test repeated wake, refresh, and sleep cycles.
- [ ] Compare direct refresh with vendor conditioning.
- [ ] Select the smallest reliable initialization sequence.
- [ ] Confirm duplicate images do not refresh.
- [ ] Confirm BUSY timeout recovery.
- [ ] Confirm rapid Home Assistant edits produce one latest update.
- [ ] Confirm applied and error diagnostics in Home Assistant.

### Phase 6: Deployment

- [x] Document Raspberry Pi OS package installation.
- [x] Document creation of a dedicated Linux service user.
- [x] Document SPI and GPIO group access.
- [x] Add the `systemd` unit.
- [x] Configure restart-on-failure behavior.
- [ ] Verify startup after power loss.
- [ ] Verify graceful shutdown and offline reporting.
- [x] Document logs and troubleshooting commands.
