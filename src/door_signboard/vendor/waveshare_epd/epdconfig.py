# Waveshare V1.2, 2022-10-29, adapted for Raspberry Pi by Door Signboard.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

import logging
import time

RST_PIN = 17
DC_PIN = 25
CS_PIN = 8
BUSY_PIN = 24
PWR_PIN = 18

logger = logging.getLogger(__name__)

_spi = None
_rst = None
_dc = None
_power = None
_busy = None


def module_init() -> int:
    global _spi, _rst, _dc, _power, _busy
    import gpiozero
    import spidev

    if _spi is not None:
        return 0
    _spi = spidev.SpiDev()
    _rst = gpiozero.LED(RST_PIN)
    _dc = gpiozero.LED(DC_PIN)
    _power = gpiozero.LED(PWR_PIN)
    _busy = gpiozero.Button(BUSY_PIN, pull_up=False)
    _power.on()
    _spi.open(0, 0)
    _spi.max_speed_hz = 4_000_000
    _spi.mode = 0
    return 0


def digital_write(pin: int, value: int) -> None:
    output = {RST_PIN: _rst, DC_PIN: _dc, PWR_PIN: _power}.get(pin)
    if output is not None:
        output.on() if value else output.off()


def digital_read(pin: int) -> int:
    if pin != BUSY_PIN or _busy is None:
        raise ValueError(f"Unsupported input pin: {pin}")
    return int(_busy.value)


def delay_ms(delay: float) -> None:
    time.sleep(delay / 1000.0)


def spi_writebyte(data) -> None:
    _spi.writebytes(data)


def spi_writebyte2(data) -> None:
    _spi.writebytes2(data)


def module_exit(cleanup: bool = False) -> None:
    global _spi, _rst, _dc, _power, _busy
    logger.debug("Closing e-paper SPI and power")
    errors = []
    operations = []
    if _spi is not None:
        operations.append(_spi.close)
    operations.extend(
        output.off for output in (_rst, _dc, _power) if output is not None
    )
    if cleanup:
        operations.extend(
            device.close
            for device in (_rst, _dc, _power, _busy)
            if device is not None
        )
    try:
        for operation in operations:
            try:
                operation()
            except Exception as error:
                errors.append(error)
    finally:
        if cleanup:
            _spi = _rst = _dc = _power = _busy = None
    if errors:
        raise errors[0]
