# Door Signboard

A Home Assistant-controlled door sign for a Raspberry Pi Zero W and Waveshare
3.52-inch e-paper display.

## Architecture

This repository contains both sides of the integration:

- `custom_components/door_signboard/` is installed into Home Assistant by HACS;
- `src/door_signboard/` runs on the Pi and renders the physical sign;
- Home Assistant sends complete desired state through integration-owned
  WebSocket commands;
- the Pi reports heartbeat, applied revision, and errors through the same API.

No MQTT broker or manually-created Home Assistant Helpers are required.

## HACS Installation

1. Open HACS in Home Assistant.
2. Open the menu and select **Custom repositories**.
3. Add `https://github.com/aaryannemade/door-signboard` with category
   **Integration**.
4. Find and download **Door Signboard**.
5. Restart Home Assistant.
6. Open **Settings > Devices & services > Add integration**.
7. Select **Door Signboard** and confirm the setup.

The integration creates one device with editable scene, apartment number,
resident name, phone number, delivery message, delivery OTP, away message, and
busy message entities. It also creates connection, revision, scene, and error
diagnostics.

## Pi Credentials

Create a dedicated non-administrator Home Assistant user for the Pi, sign in as
that user, and create a long-lived access token from its profile page. Create
`credentials.secret` from `credentials.example`:

```text
HA-URL: http://homeassistant.local:8123
HA-TOKEN: replace-with-the-long-lived-access-token
DEVICE-ID: door_signboard
```

The secret file is ignored by Git. The token is never included in logs or
object representations.

## Development Shell

Enter the pinned Nix development environment:

```console
nix develop
```

The shell provides Python, Pillow (`PIL`), NumPy, GPIO Zero, `spidev`,
WebSockets, and DejaVu fonts. The vendored Waveshare module is imported only in
hardware mode, so preview development does not access GPIO or SPI.

## Image Generator

The renderer produces 360 x 240 Pillow images in monochrome mode `1`. Available
scenes are `Scene.DEFAULT`, `Scene.DELIVERY`, `Scene.AWAY`, and `Scene.BUSY`.
The default scene only shows the resident name and apartment number.

Shared drawing behavior lives in `src/door_signboard/display.py`. Individual
layouts live under `src/door_signboard/scenes/` so they can be changed without
growing the common renderer.

Default placeholder values are defined in
`src/door_signboard/constants.py`:

- `APARTMENT_NUMBER`
- `DELIVERY_MESSAGE`
- `AWAY_MESSAGE`
- `BUSY_MESSAGE`
- `NAME`
- `PHONE_NUMBER`

Supply real or Home Assistant-provided values with `SignContent` rather than changing
layout code:

```python
from door_signboard import Scene, SignContent, generate_image

content = SignContent(
    apartment_number="42",
    delivery_message="Please leave the parcel beside the door.",
    delivery_otp="123456",
    away_message="We're away until 18:00.",
    busy_message="In a meeting until 15:30.",
    name="Aaryan",
    phone_number="919876543210",
)

image = generate_image(Scene.DELIVERY, content)
image.save("delivery.png")
```

`delivery_otp` is optional and is intended to be supplied by Home Assistant.
When it is empty or `None`, the delivery message remains centered and no OTP
line is rendered.

From the repository root, run this code with `PYTHONPATH=src` until the package
installation configuration is added.

## Signboard Client

Validate the ignored credentials file without connecting:

```console
PYTHONPATH=src python -m door_signboard.main --check-config
```

Run the WebSocket client in preview mode (the default):

```console
PYTHONPATH=src python -m door_signboard.main
```

Changing a Door Signboard entity in Home Assistant generates the latest image
at `tmp/generated-images/ha-preview.png`.

On the Raspberry Pi, update the physical display with:

```console
PYTHONPATH=src python -m door_signboard.main --output-mode hardware
```

Hardware mode performs full GC refreshes and, by default, refreshes the panel
on every new Home Assistant revision (after a short debounce), retaining only
the latest revision while a refresh is in flight. To throttle physical refreshes
(for example, to limit e-ink panel wear), set a minimum interval in seconds.
Override the interval or 30-second BUSY timeout only when diagnosing the panel:

```console
PYTHONPATH=src python -m door_signboard.main --output-mode hardware \
  --minimum-refresh-interval 180 --busy-timeout 30
```

## Raspberry Pi Setup

Install Raspberry Pi OS packages and enable SPI:

```console
sudo apt update
sudo apt install fonts-dejavu-core git python3-gpiozero python3-numpy python3-pil python3-spidev python3-venv
sudo raspi-config nonint do_spi 0
test -e /dev/spidev0.0
```

For a dedicated service account and an installation at
`/opt/door-signboard`:

```console
sudo useradd --system --home /opt/door-signboard --shell /usr/sbin/nologin door-signboard
sudo install -d -o door-signboard -g door-signboard /opt/door-signboard
sudo -u door-signboard git clone https://github.com/aaryannemade/door-signboard.git /opt/door-signboard
sudo -u door-signboard python3 -m venv --system-site-packages /opt/door-signboard/.venv
sudo -u door-signboard /opt/door-signboard/.venv/bin/pip install 'websockets>=14,<16'
sudo usermod -aG gpio,spi door-signboard
sudo install -m 600 -o door-signboard -g door-signboard credentials.secret /opt/door-signboard/credentials.secret
sudo chmod 600 /opt/door-signboard/credentials.secret
sudo cp /opt/door-signboard/deploy/door-signboard.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now door-signboard.service
```

Inspect runtime status and logs with:

```console
systemctl status door-signboard.service
journalctl -u door-signboard.service -f
```

After updating the checkout, restart it with
`sudo systemctl restart door-signboard.service`. The unit waits for networking,
restarts after failures, and uses `SIGINT` so the client can report offline and
release display resources during shutdown.

The adapted Waveshare source, source hashes, license, and modifications are
documented in `src/door_signboard/vendor/waveshare_epd/README.md`.

## Tests

```console
PYTHONPATH=src python -m unittest discover -s tests -v
nix flake check path:.
```
