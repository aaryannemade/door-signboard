# Door Signboard Development Plan

## 1. Goal

Build a headless door signboard using:

- a Raspberry Pi Zero W running Raspberry Pi OS Lite;
- a Waveshare 3.52-inch monochrome e-paper display over SPI;
- a Python renderer and display driver on the Pi;
- a HACS-installable Home Assistant custom integration;
- Home Assistant's authenticated WebSocket API for local push communication.

The integration will create one Door Signboard device and all editable entities
without MQTT, a broker, or manually-created Helpers.

## 2. Architecture

```text
Home Assistant custom integration
    |
    | door_signboard/subscribe command (complete desired state stream)
    v
Home Assistant WebSocket API
    |
    v
Pi WebSocket client -> scene renderer -> display driver -> e-paper
    |
    | door_signboard/status command (heartbeat/applied/error/offline)
    v
Home Assistant custom integration
```

The Home Assistant integration owns persistent desired state. The Pi treats
received messages as desired state, renders only the newest revision, and
reports a revision as applied only after the image or hardware update succeeds.

## 3. Repository Layout

The same GitHub repository serves both HACS and the Pi application:

```text
door-signboard/
├── hacs.json
├── custom_components/
│   └── door_signboard/
│       ├── __init__.py
│       ├── manifest.json
│       ├── config_flow.py
│       ├── const.py
│       ├── coordinator.py
│       ├── entity.py
│       ├── select.py
│       ├── text.py
│       ├── binary_sensor.py
│       ├── sensor.py
│       ├── strings.json
│       ├── translations/en.json
│       └── brand/icon.png
├── src/
│   └── door_signboard/
│       ├── __init__.py
│       ├── constants.py
│       ├── display.py
│       ├── display_driver.py
│       ├── ha_websocket.py
│       ├── main.py
│       └── scenes/
├── tests/
├── flake.nix
├── generate-images.sh
└── README.md
```

HACS requires exactly one integration directory under `custom_components/` and
copies only that integration into Home Assistant. The Pi application remains a
separate importable package under `src/`.

## 4. Home Assistant Device

The config flow creates one config entry and one device named Door Signboard.
The first version supports one signboard.

Editable entities:

- scene selector: `default`, `delivery`, `away`, or `busy`;
- apartment number text;
- resident name text;
- phone number text;
- delivery message text;
- delivery OTP text, which may be empty;
- away message text;
- busy message text.

Diagnostic entities:

- connected binary sensor;
- last applied scene sensor;
- desired revision sensor;
- applied revision sensor;
- last error sensor.

Editable entities remain available while the Pi is offline. Their state is
stored by the integration and sent in full when the Pi reconnects.

## 5. Home Assistant State Coordinator

The integration coordinator will:

- load defaults or the last persisted state from Home Assistant `Store`;
- validate all entity updates;
- increment a monotonically increasing desired revision on each real change;
- write state back to storage;
- update all entities through one coordinator notification;
- push complete desired state to integration-owned WebSocket subscribers;
- send the complete current state immediately after a Pi subscribes;
- process heartbeat, applied, error, and offline status commands;
- mark the Pi disconnected after a heartbeat timeout.

The integration does not import code from `src/door_signboard`; every runtime
file needed by HACS must remain inside `custom_components/door_signboard/`.
Protocol compatibility will be protected by contract tests.

## 6. WebSocket Command Contract

### Desired state

Subscription command: `door_signboard/subscribe`

```json
{
  "device_id": "door_signboard",
  "revision": 8,
  "scene": "delivery",
  "apartment_number": "Tower X / XXX",
  "name": "Resident",
  "phone_number": "911234567890",
  "delivery_message": "Please leave deliveries on the table",
  "delivery_otp": "123456",
  "away_message": "No one is home right now",
  "busy_message": "Please do not disturb"
}
```

### Device status

Command: `door_signboard/status`

Statuses are `online`, `heartbeat`, `applied`, `error`, and `offline`.
Applied and error reports include the relevant revision. Error reports include
a bounded error message. Heartbeats allow the integration to detect an
uncleanly disconnected Pi.

## 7. Pi WebSocket Client

`ha_websocket.py` will:

- derive `ws://` or `wss://` from the configured Home Assistant URL;
- authenticate with a dedicated Home Assistant long-lived access token;
- subscribe through the integration-owned `door_signboard/subscribe` command;
- receive the complete current state immediately after subscribing;
- validate payload types, lengths, scene values, phone number, and revisions;
- ignore events for other device IDs and stale revisions;
- reconnect with bounded exponential backoff;
- send online, heartbeat, applied, error, and graceful offline status commands;
- expose received state through a callback without importing display hardware.

The ignored `credentials.secret` format becomes:

```text
HA-URL: http://homeassistant.local:8123
HA-TOKEN: long-lived-access-token
DEVICE-ID: door_signboard
```

The token must belong to a dedicated Home Assistant user and must never appear
in Git or logs.

## 8. Rendering And Update Orchestration

The existing renderer remains hardware-independent and produces a 360 x 240
Pillow mode `1` image. Scene layouts stay under `src/door_signboard/scenes/`.

The orchestrator will:

- coalesce related edits and retain only the newest desired revision;
- generate a preview PNG during desktop development;
- later pass the same in-memory image to `display_driver.py`;
- skip duplicate rendered images;
- report applied state only after rendering/display succeeds;
- report errors without advancing the applied revision.

The display driver will enforce the e-paper update policy separately from the
WebSocket connection so frequent Home Assistant edits cannot create a hardware
refresh backlog.

## 9. Waveshare Display Driver

The vendor module is `waveshare_epd.epd3in52`. It declares a monochrome native
resolution of 240 x 360 and accepts the renderer's landscape 360 x 240 image
through `getbuffer()`.

The full update sequence is:

```python
epd.init()
buffer = epd.getbuffer(image.convert("1"))
epd.display(buffer)
epd.lut_GC()
epd.refresh()
epd.sleep()
```

Version one uses `lut_GC()` only. The vendor demo says `lut_DU()` has poor
visual results. The driver must serialize access, reject invalid dimensions,
skip duplicate image hashes, clean up GPIO/SPI after errors, and avoid clearing
the persistent panel during normal startup or shutdown.

## 10. HACS Packaging

Root metadata:

- `hacs.json` identifies the repository as the Door Signboard integration;
- `README.md` documents both HACS installation and Pi setup;
- GitHub releases use semantic versions when the integration is ready;
- HACS and Hassfest GitHub Actions validate each change.

Integration metadata:

- domain: `door_signboard`;
- integration type: `device`;
- IoT class: `local_push`;
- config flow enabled;
- single config entry enabled;
- documentation and issue links point to
  `https://github.com/aaryannemade/door-signboard`;
- code owner: `@aaryannemade`;
- a local brand icon is included.

Installation flow:

1. Add `https://github.com/aaryannemade/door-signboard` to HACS as a custom
   Integration repository.
2. Download Door Signboard in HACS.
3. Restart Home Assistant.
4. Add the Door Signboard integration under Devices and Services.
5. Create a dedicated Home Assistant user and long-lived token for the Pi.
6. Configure and start the Pi service.

## 11. Testing Strategy

Pi-side tests:

- credential parsing without exposing the token;
- WebSocket authentication and URL conversion;
- integration-owned subscription and initial state delivery;
- desired-state validation and stale-revision rejection;
- reconnect backoff and heartbeat behavior;
- coalescing and latest-revision rendering;
- applied versus error reporting;
- all existing renderer tests.

Integration tests:

- config flow and duplicate prevention;
- entity creation and shared device metadata;
- state validation and persistence;
- revision increments only on real changes;
- complete desired-state subscription payloads;
- initial state delivery;
- status command handling and heartbeat timeout;
- entity state updates after applied and error reports.

Repository validation:

- HACS validation action;
- Hassfest validation action;
- JSON validation for manifest, HACS metadata, strings, and translations;
- unit tests in the Nix development shell where dependencies permit.

## 12. Delivery Phases

### Phase 1: HACS integration skeleton

Create metadata, config flow, storage coordinator, device entities,
translations, brand asset, and validation workflows.

Exit criterion: HACS accepts the repository and Home Assistant creates one
device with every editable and diagnostic entity.

### Phase 2: WebSocket protocol

Implement desired-state subscription, status commands, heartbeat timeout,
persistence, and revision handling inside the custom integration.

Exit criterion: Home Assistant WebSocket commands carry complete validated state and
diagnostic entities reflect simulated device reports.

### Phase 3: Pi WebSocket preview client

Implement authentication, subscription, reconnect, heartbeat, validation,
coalescing, and preview rendering.

Exit criterion: changing an integration entity updates
`tmp/generated-images/ha-preview.png`, and Home Assistant reports the same
revision as applied.

### Phase 4: Physical display

Implement the `epd3in52` wrapper and replace preview output with the hardware
callback while retaining an optional preview mode.

Exit criterion: a Home Assistant edit reliably updates the e-paper display and
the panel sleeps after the refresh.

### Phase 5: Pi deployment

Add Raspberry Pi dependency installation, a dedicated service user, systemd
unit, restart behavior, logs, and update instructions.

Exit criterion: after power loss, the Pi reconnects unattended, subscribes to
the current desired state, updates if needed, and reports availability.
