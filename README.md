# Door Signboard

A Home Assistant-controlled door sign for a Raspberry Pi Zero W and Waveshare
3.52-inch e-paper display.

Home Assistant owns the desired state and pushes it to the Pi over WebSocket.
The Pi renders the sign and reports back its status. No MQTT broker or manual
Home Assistant helpers are required.

- `custom_components/door_signboard/` is installed into Home Assistant via HACS.
- `src/door_signboard/` runs on the Pi and drives the display.

## 1. Install the Home Assistant integration (HACS)

1. Open HACS in Home Assistant.
2. Open the menu and select **Custom repositories**.
3. Add `https://github.com/aaryannemade/door-signboard` with category
   **Integration**.
4. Find and download **Door Signboard**.
5. Restart Home Assistant.
6. Open **Settings > Devices & services > Add integration**.
7. Select **Door Signboard** and confirm the setup.

This creates one device with editable scene, apartment number, resident name,
phone number, delivery message, delivery OTP, away message, and busy message
entities, plus connection, revision, scene, and error diagnostics.

## 2. Create Pi credentials

Create a dedicated non-administrator Home Assistant user for the Pi, sign in as
that user, and create a long-lived access token from its profile page.

Copy `credentials.example` to `credentials.secret` and fill it in:

```text
HA-URL: http://homeassistant.local:8123
HA-TOKEN: replace-with-the-long-lived-access-token
DEVICE-ID: door_signboard
```

`credentials.secret` is ignored by Git and its token is never logged.

## 3. Prepare the Raspberry Pi

Install the OS packages and enable SPI:

```console
sudo apt update
sudo apt install fonts-dejavu-core git python3-gpiozero python3-numpy python3-pil python3-spidev python3-venv
sudo raspi-config nonint do_spi 0
test -e /dev/spidev0.0
```

## 4. Install and run the service

Clone the repository into your home directory and create the virtual
environment (run these as your own user, not root):

```console
git clone https://github.com/aaryannemade/door-signboard.git ~/door-signboard
cd ~/door-signboard
python3 -m venv --system-site-packages .venv
.venv/bin/pip install 'websockets>=14,<16'
```

Make sure your user can access the display's GPIO and SPI, then place your
`credentials.secret` from step 2 in the repository root and lock it down:

```console
sudo usermod -aG gpio,spi "$USER"   # log out and back in for this to apply
chmod 600 ~/door-signboard/credentials.secret
```

The service file ships with `<user>` placeholders. Edit
`deploy/door-signboard.service` and replace every `<user>` with your Linux
username, then install and start the service:

```console
sudo cp ~/door-signboard/deploy/door-signboard.service /etc/systemd/system/door-signboard.service
sudo systemctl daemon-reload
sudo systemctl enable --now door-signboard.service
```

The service waits for networking, restarts on failure, and shuts down with
`SIGINT` so the Pi can report offline and release the display cleanly.

## 5. Operate

Check status and follow logs:

```console
systemctl status door-signboard.service
journalctl -u door-signboard.service -f
```

After pulling updates, restart the service:

```console
sudo systemctl restart door-signboard.service
```

By default the panel refreshes on every new Home Assistant revision. To throttle
physical refreshes (for example, to limit e-ink panel wear), add
`--minimum-refresh-interval <seconds>` to the `ExecStart` line in
`/etc/systemd/system/door-signboard.service`, then reload and restart:

```console
sudo systemctl daemon-reload
sudo systemctl restart door-signboard.service
```

## Attribution

The adapted Waveshare source, source hashes, license, and modifications are
documented in `src/door_signboard/vendor/waveshare_epd/README.md`.

## License

This project is licensed under the MIT License; see [LICENSE](LICENSE).

The vendored Waveshare driver under `src/door_signboard/vendor/waveshare_epd/`
retains its own upstream license notices and is not covered by the MIT license
above.
