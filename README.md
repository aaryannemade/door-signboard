# Door Signboard

A Home Assistant-controlled door sign for a Raspberry Pi Zero W and Waveshare
3.52-inch e-paper display.

## Development Shell

Enter the pinned Nix development environment:

```console
nix develop
```

The shell provides Python, Pillow (`PIL`), NumPy, `spidev`, and DejaVu fonts.
The Waveshare hardware library will be integrated with the display driver
separately.

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

Supply real or MQTT-provided values with `SignContent` rather than changing
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

## Tests

```console
PYTHONPATH=src python -m unittest discover -s tests -v
```
