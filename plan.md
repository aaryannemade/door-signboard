# Door Signboard Development Plan

## 1. Goal

Build a headless Python service for a Raspberry Pi Zero W connected over SPI to
a Waveshare 3.52-inch e-paper display. Home Assistant will control the sign by
publishing MQTT messages. The Pi will receive the desired state, render one of
two preset scene layouts into an image, and update the physical display.

The system should:

- run automatically when the Pi boots;
- work without a web frontend on the Pi;
- expose controls and status in Home Assistant through MQTT Discovery;
- retain the last desired state across restarts or reconnects;
- avoid unnecessary e-paper refreshes;
- recover from MQTT, Wi-Fi, rendering, and display errors;
- keep Waveshare-specific code isolated from layout and MQTT code.

## 2. Terminology And Data Flow

The Pi is not the MQTT broker. A broker such as the Mosquitto add-on runs
alongside Home Assistant. The Pi runs an MQTT client.

```text
Home Assistant
    |
    | publish desired state / receive status
    v
MQTT broker (for example, Mosquitto)
    |
    | subscribed command messages
    v
Pi MQTT client -> scene renderer -> display driver -> Waveshare e-paper
    |
    +---------------- publish availability and result -----------------> broker
```

An update should follow this sequence:

1. Home Assistant publishes a complete desired-state message.
2. The MQTT module validates and converts it to an internal model.
3. The display module renders the selected scene to a Pillow image.
4. The display driver converts and sends the image to the EPD library.
5. The MQTT module publishes the applied state or an error.

## 3. Proposed Python Modules

Use Python package names with underscores even though the conceptual module
names contain hyphens.

### `display_driver.py`

Responsibility: adapt Pillow images to the Waveshare 3.52-inch EPD library and
own the panel's hardware lifecycle.

The checked-in vendor example is:

```text
tmp/e-paper/RaspberryPi_JetsonNano/python/examples/epd_3in52_test.py
```

It imports `waveshare_epd.epd3in52`. The corresponding driver declares a
monochrome panel with a native portrait resolution of 240 x 360 pixels:

```python
from waveshare_epd import epd3in52

epd = epd3in52.EPD()
assert (epd.width, epd.height) == (240, 360)
```

For landscape orientation, `display.render_scene()` should produce a mode `1`
Pillow image sized 360 x 240. The vendor's `epd.getbuffer()` recognizes that
size and rotates it into the panel's native 240 x 360 buffer. The driver should
also accept native portrait images sized 240 x 360, but it must reject every
other size instead of allowing `getbuffer()` to silently return a blank buffer.

Public interface should initially stay small:

```python
class Waveshare3in52DisplayDriver:
    def initialize(self) -> None: ...
    def show(self, image: Image.Image) -> None: ...
    def clear(self) -> None: ...
    def sleep(self) -> None: ...
```

`initialize()` should construct `epd3in52.EPD()`, call `epd.init()`, and treat a
non-zero return value as initialization failure. A normal full update must use
the same sequence as the vendor demo:

```python
buffer = epd.getbuffer(image.convert("1"))
epd.display(buffer)
epd.lut_GC()
epd.refresh()
```

The call to `display()` only transfers the new frame; `lut_GC()` selects the
full-refresh waveform and `refresh()` makes the frame visible. These calls must
remain in this order. The wrapper should not duplicate low-level commands,
lookup tables, busy-pin polling, or SPI writes from `epd3in52.py`.

The display changes infrequently, so the initial lifecycle for each update
should be:

1. Acquire the driver's update lock.
2. Validate the image size and convert it to monochrome mode `1`.
3. Compare a digest of the normalized image with the last successful digest;
   return without initializing the panel if they match.
4. Call `initialize()`.
5. Transfer and fully refresh the image with the sequence above.
6. Record the digest only after `refresh()` succeeds.
7. Call `epd.sleep()` in `finally` after a successful initialization; this
   enters deep sleep, waits two seconds, and calls the vendor's
   `epdconfig.module_exit()`.

Sleeping after each update is suitable for a door sign that changes
occasionally and ensures GPIO/SPI cleanup. Every later update must initialize
the panel again. If measurements show that rapid updates are common, this can
later become an idle timeout rather than keeping the panel awake indefinitely.

`clear()` is an explicit maintenance action implemented with `epd.Clear()`,
which transfers a white frame, loads the GC waveform, and refreshes. Do not
clear during startup or normal shutdown: e-paper retains the last image and a
clear would add an unnecessary full refresh.

The demo conditions the panel once before its examples by displaying a white
frame, performing a GC refresh, then sending command `0x50` with data `0x17`.
That low-level step is not represented by a named vendor API and must be tested
on the Pi. If it is required after every `init()`, encapsulate it in a private
driver method and account for the extra refresh. If ordinary images render
correctly after `init()` without it, reserve the conditioning sequence for
installation diagnostics rather than clearing the sign on every update.

The vendor demo includes a quick-update path using `lut_DU()`, but comments that
its visual result is poor and that it is not recommended. Version one must
therefore use `lut_GC()` full refresh only. Do not add a configurable
`full_refresh_every` policy until partial refresh has been tested on this exact
panel.

The driver should also:

- serialize access so two display writes cannot overlap;
- translate vendor `IOError` and initialization failures into a
  `DisplayDriverError` while preserving the original exception;
- call `epd3in52.epdconfig.module_exit(cleanup=True)` if initialization fails
  after partially acquiring hardware resources;
- log initialization, skipped duplicate, refresh completion, and cleanup at
  useful levels without logging the packed image buffer;
- expose a fake implementation for development and tests without Pi hardware.

It should not know about MQTT, Home Assistant, text fields, or scene layouts.

### `display.py`

Responsibility: turn validated sign content into an image using Pillow.

Suggested interface:

```python
def render_scene(state: SignState, settings: DisplaySettings) -> Image.Image:
    ...
```

It should:

- contain the two scene layout implementations;
- load fonts and static assets from an `assets/` directory;
- handle text wrapping, alignment, truncation, and font sizing;
- output the exact pixel dimensions and color mode expected by the driver;
- remain deterministic: the same state should create the same image;
- support saving rendered PNG previews on a development machine;
- have no GPIO, SPI, Waveshare, or MQTT imports.

The initial renderer implements four scenes. Three share an apartment header
and a name/phone footer:

1. `default`: displays only the resident name and apartment number.
2. `delivery`: displays the configured delivery message.
3. `away`: displays the configured away message.
4. `busy`: displays the configured busy message.

The renderer owns these preset layouts. MQTT will select a scene and provide
content values rather than drawing coordinates.

### `ha_mqtt.py`

Responsibility: connect the application to the MQTT broker and Home Assistant.

It should:

- connect using a dedicated MQTT account;
- subscribe to the command topic;
- validate incoming JSON before passing it to the application;
- publish online/offline availability using an MQTT Last Will;
- publish the last successfully applied state;
- publish useful error details separately from applied state;
- reconnect with backoff after network or broker failure;
- publish Home Assistant MQTT Discovery entities at startup;
- never call the Waveshare library directly.

Use a filename such as `ha_mqtt.py`, not `HA-mqtt-broker.py`: hyphens are not
valid in Python import names, and this component is a client rather than a
broker.

## 4. Application Orchestrator

Although there are three main functional modules, add a thin `main.py` to wire
them together. This prevents the MQTT module from becoming responsible for
rendering and hardware.

```text
main.py
  receives validated SignState from ha_mqtt
  renders it through display
  writes it through display_driver
  reports success or failure through ha_mqtt
```

Only one update should execute at a time. If commands arrive quickly, keep the
newest desired state and discard superseded pending updates. This is appropriate
for a sign where only the latest state matters and protects a slow e-paper
display from a backlog of refreshes.

## 5. Internal State Model

Use a dataclass or a small validated model shared between the renderer,
orchestrator, and MQTT adapter.

Initial conceptual model:

```python
class Scene(str, Enum):
    DEFAULT = "default"
    DELIVERY = "delivery"
    AWAY = "away"
    BUSY = "busy"


@dataclass(frozen=True)
class SignContent:
    apartment_number: str
    delivery_message: str
    away_message: str
    busy_message: str
    name: str
    phone_number: str
```

Set explicit maximum lengths. Reject unknown scenes and wrong field types.
Decide whether unknown JSON fields are rejected; rejecting them initially makes
configuration mistakes easier to detect.

The model may evolve once the two scenes are specified. Avoid passing arbitrary
drawing coordinates or font settings over MQTT; MQTT should describe content and
intent while the Pi owns the preset layouts.

## 6. MQTT Contract

Use a stable device ID, for example `door_signboard`, and configurable topic
prefix.

Suggested topics:

| Topic                         | Direction | Retained | Purpose                       |
| ----------------------------- | --------- | -------- | ----------------------------- |
| `door-signboard/command`      | HA to Pi  | Yes      | Complete desired state        |
| `door-signboard/state`        | Pi to HA  | Yes      | Last state successfully shown |
| `door-signboard/availability` | Pi to HA  | Yes      | `online` or `offline`         |
| `door-signboard/error`        | Pi to HA  | No       | Last processing/display error |

Example command:

```json
{
  "scene": "message",
  "title": "In a meeting",
  "message": "Please come back at 15:30",
  "detail": "Do not disturb"
}
```

Publish the entire desired state in every command rather than applying patches.
Retain the command so the sign can restore the desired display after restarting.
Do not publish the command payload as successfully applied state until rendering
and the hardware update complete.

Later, Home Assistant MQTT Discovery can create entities such as:

- a scene selector (`message` or `status`);
- text entities for title, message, and detail;
- a connectivity binary sensor;
- a sensor for the last applied scene or error.

Home Assistant entities publish a complete command through an automation or
script. Start with one raw JSON command topic before adding Discovery, because
it is easier to test and isolates MQTT/device behavior from HA entity design.

## 7. Suggested Repository Layout

```text
door-signboard/
├── README.md
├── plan.md
├── pyproject.toml
├── src/
│   └── door_signboard/
│       ├── __init__.py
│       ├── main.py
│       ├── models.py
│       ├── config.py
│       ├── display.py
│       ├── display_driver.py
│       └── ha_mqtt.py
├── assets/
│   ├── fonts/
│   └── images/
├── tests/
│   ├── test_display.py
│   ├── test_models.py
│   └── test_ha_mqtt.py
├── examples/
│   └── config.example.toml
└── deploy/
    └── door-signboard.service
```

Do not copy the Waveshare library into the application until its recommended
installation method and license are confirmed. If it must be vendored, isolate
it under a clearly named third-party directory and record its source/version.

## 8. Configuration

Keep non-secret settings in one TOML file or environment variables:

```toml
[mqtt]
host = "homeassistant.local"
port = 1883
username = "door_signboard"
topic_prefix = "door-signboard"
client_id = "door-signboard-pi"

[display]
model = "epd3in52"
orientation = "landscape"
```

Pass the MQTT password through a root-readable environment file, not Git.
Configuration should include logging level and orientation. The model and
resolution are fixed to `epd3in52` and 240 x 360 in the first implementation;
do not make unsupported hardware variants or partial refresh configurable yet.

## 9. Development Phases

### Phase 0: Confirm Hardware And Constraints

- Record the exact Waveshare product revision. The current code identifies the
  display as the monochrome 3.52-inch, 240 x 360 model using `epd3in52.py`.
- Treat full GC refresh as the supported update mode. The demo exposes DU quick
  refresh but explicitly does not recommend its visual result.
- Confirm the required Raspberry Pi OS architecture and Python versions.
- Enable SPI with `raspi-config` and verify `/dev/spidev*` exists.
- Run the exact vendor example on the Pi before integrating application code.
- Record the display's native orientation, Pillow mode, and refresh duration.
- Confirm the two scene names, fields, examples, and visual priorities.

Exit criterion: a vendor example reliably displays an image and the project has
an agreed content sketch for both scenes.

### Phase 1: Renderer First

- Create the package, dependency metadata, state model, and configuration model.
- Implement both layouts with Pillow on a normal development computer.
- Add a preview command that writes PNG files instead of using hardware.
- Add representative fixtures for short, long, empty, and multiline text.
- Test output dimensions/mode and snapshot or pixel-hash rendered images.

Exit criterion: both scene previews are readable and deterministic at the
display's actual resolution.

### Phase 2: Hardware Driver

- Wrap `waveshare_epd.epd3in52.EPD` behind
  `Waveshare3in52DisplayDriver`.
- Accept 360 x 240 landscape or 240 x 360 portrait Pillow images, convert to
  mode `1`, and reject all other dimensions.
- Implement the exact full-update sequence: `init()`, `getbuffer()`,
  `display()`, `lut_GC()`, `refresh()`, and `sleep()`.
- Keep `lut_DU()` quick refresh out of the first implementation.
- Cache a hash of the last successfully displayed image to avoid duplicates.
- Test landscape rotation, black/white polarity, full refresh, deep sleep, and
  repeated reinitialization directly on the Pi.

Exit criterion: a local command can render and show either scene repeatedly
without manual cleanup or display corruption.

### Phase 3: MQTT Control

- Install/configure Mosquitto in Home Assistant if it is not already available.
- Create a dedicated least-privilege MQTT user for the sign.
- Implement connection, retained command subscription, Last Will availability,
  state, and error publishing.
- Validate JSON and protect the main loop from malformed messages.
- Coalesce rapid updates so only the newest state is rendered next.
- Test commands with an MQTT CLI before involving HA automations.

Exit criterion: publishing a retained command changes the display, publishes
applied state, and reconnects correctly after Wi-Fi or broker interruption.

### Phase 4: Home Assistant Integration

- Add MQTT Discovery configuration with a stable unique device ID.
- Create entities needed to edit/select the two scenes.
- Add HA scripts or automations that combine entity values into one complete
  JSON command.
- Verify availability and applied state are visible in HA.
- Document example service calls and automations.

Exit criterion: the sign can be controlled entirely from HA services, scripts,
and automations without logging into the Pi.

### Phase 5: Deployment And Hardening

- Create a dedicated Linux user with only required GPIO/SPI permissions.
- Install the project in a virtual environment.
- Add a `systemd` unit with restart-on-failure and network ordering.
- Log to stdout/stderr so logs are available through `journalctl`.
- Add graceful shutdown that puts the panel to sleep and cleans up GPIO.
- Test cold boot, MQTT outage, Wi-Fi outage, malformed input, process crash, and
  power restoration.
- Document install, update, rollback, and troubleshooting steps.

Exit criterion: after power loss, the service starts unattended, reconnects, and
restores the retained desired state.

## 10. Testing Strategy

Most tests should run without a Raspberry Pi:

- model tests for valid and invalid command payloads;
- renderer tests for dimensions, modes, wrapping, overflow, and both scenes;
- MQTT tests using mocked callbacks or a temporary broker;
- orchestrator tests with fake MQTT and fake display driver implementations;
- tests proving duplicate images do not refresh the panel;
- tests proving failed display writes do not publish successful applied state;
- tests proving several rapid commands result in the newest state being shown.

Hardware smoke tests must run manually on the Pi because CI cannot validate SPI
timing, panel orientation, ghosting, or refresh behavior.

## 11. Operational And E-Paper Considerations

- E-paper updates are slow. Treat commands as desired state, not an event queue.
- Frequent partial updates can cause ghosting. Follow the exact panel
  documentation and periodically perform a full refresh if partial refresh is
  used.
- Do not refresh solely to show a ticking clock unless the panel's refresh
  limits and product requirements justify it.
- The displayed image usually remains after power loss; published MQTT state
  means "last successfully written," not proof that the panel is currently
  powered.
- Avoid clearing the display during normal startup/shutdown because it causes an
  unnecessary refresh.
- Configure timeouts around update operations where the vendor API permits it,
  while recognizing that a stuck hardware call may require service restart.
- Use structured, concise logs without MQTT credentials or full secret-bearing
  configuration.

## 12. Security

- Use a separate broker username/password for this device.
- Restrict its ACL to reading `door-signboard/command` and writing its state,
  availability, error, and Discovery topics.
- Prefer TLS if MQTT crosses an untrusted network; a trusted isolated home LAN
  may start with authenticated port 1883.
- Do not store credentials in Git or publish them in logs.
- Validate message size and field lengths before rendering to prevent memory or
  layout abuse.
- Keep Raspberry Pi OS and Python dependencies updated deliberately rather than
  unpinned.

## 13. Initial Technology Choices

- Python version supported by the installed Raspberry Pi OS, preferably Python
  3.11 or newer when available.
- Pillow for image generation.
- `paho-mqtt` for MQTT and Home Assistant compatibility.
- Standard-library `dataclasses`, `json`, `logging`, and `tomllib` where
  sufficient.
- `pytest` for unit tests.
- `systemd` for process lifecycle.

Keep dependencies small because the Pi Zero W has limited CPU and memory. Avoid
an HTTP server, GUI toolkit, database, or asynchronous framework until a
demonstrated requirement needs one.

## 14. Decisions Needed Before Implementation

1. What is the exact hardware revision/SKU of the confirmed Waveshare 3.52-inch
   monochrome 240 x 360 display?
2. What should each of the two scenes look like, and which text/icon fields does
   each require?
3. Which orientation will the sign use?
4. Is partial refresh required, supported, and visually acceptable on this
   panel?
5. Is an MQTT broker already installed and configured in Home Assistant?
6. Should a blank/clear scene be supported, or only the two content scenes?
7. Are fonts/icons redistributable in the repository, or should deployment
   install system fonts?

## 15. Recommended First Milestone

Do not begin with Home Assistant Discovery. The smallest useful vertical slice
is:

1. Confirm the vendor display example works on the Pi.
2. Define one exact scene and render it to a PNG on a development machine.
3. Display that generated image through the driver wrapper on the Pi.
4. Subscribe to one raw MQTT command topic and update the image.
5. Publish applied state and availability.

After this works reliably, add the second scene, Home Assistant Discovery,
deployment automation, and partial-refresh optimizations. This sequence tests
the riskiest boundary, the exact display hardware and vendor driver, before
investing in the broader integration.
