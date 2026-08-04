# Waveshare V1.0, 2022-07-20, adapted for Door Signboard.
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

from . import epdconfig

EPD_WIDTH = 240
EPD_HEIGHT = 360

logger = logging.getLogger(__name__)


class EPD:
    lut_R20_GC = [
        0x01, 0x0F, 0x0F, 0x0F, 0x01, 0x01, 0x01,
        *([0x00] * 49),
    ]
    lut_R21_GC = [
        0x01, 0x4F, 0x8F, 0x0F, 0x01, 0x01, 0x01,
        *([0x00] * 35),
    ]
    lut_R22_GC = [
        0x01, 0x0F, 0x8F, 0x0F, 0x01, 0x01, 0x01,
        *([0x00] * 49),
    ]
    lut_R23_GC = [
        0x01, 0x4F, 0x8F, 0x4F, 0x01, 0x01, 0x01,
        *([0x00] * 49),
    ]
    lut_R24_GC = [
        0x01, 0x0F, 0x8F, 0x4F, 0x01, 0x01, 0x01,
        *([0x00] * 35),
    ]

    def __init__(self, busy_timeout_seconds: float = 30.0) -> None:
        self.reset_pin = epdconfig.RST_PIN
        self.dc_pin = epdconfig.DC_PIN
        self.busy_pin = epdconfig.BUSY_PIN
        self.cs_pin = epdconfig.CS_PIN
        self.width = EPD_WIDTH
        self.height = EPD_HEIGHT
        self.Flag = 0
        self.busy_timeout_seconds = busy_timeout_seconds

    def reset(self) -> None:
        epdconfig.digital_write(self.reset_pin, 1)
        epdconfig.delay_ms(200)
        epdconfig.digital_write(self.reset_pin, 0)
        epdconfig.delay_ms(2)
        epdconfig.digital_write(self.reset_pin, 1)
        epdconfig.delay_ms(200)

    def send_command(self, command: int) -> None:
        epdconfig.digital_write(self.dc_pin, 0)
        epdconfig.digital_write(self.cs_pin, 0)
        epdconfig.spi_writebyte([command])
        epdconfig.digital_write(self.cs_pin, 1)

    def send_data(self, data: int) -> None:
        epdconfig.digital_write(self.dc_pin, 1)
        epdconfig.digital_write(self.cs_pin, 0)
        epdconfig.spi_writebyte([data])
        epdconfig.digital_write(self.cs_pin, 1)

    def send_data2(self, data) -> None:
        epdconfig.digital_write(self.dc_pin, 1)
        epdconfig.digital_write(self.cs_pin, 0)
        epdconfig.spi_writebyte2(data)
        epdconfig.digital_write(self.cs_pin, 1)

    def ReadBusy(self) -> None:
        deadline = time.monotonic() + self.busy_timeout_seconds
        logger.debug("e-Paper busy")
        while epdconfig.digital_read(self.busy_pin) == 0:
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"e-paper remained busy for {self.busy_timeout_seconds:g}s"
                )
            epdconfig.delay_ms(5)
        logger.debug("e-Paper busy released")

    def refresh(self) -> None:
        self.send_command(0x17)
        self.send_data(0xA5)
        self.ReadBusy()
        epdconfig.delay_ms(200)

    def lut_GC(self) -> None:
        self.send_command(0x20)
        self.send_data2(self.lut_R20_GC[:56])
        self.send_command(0x21)
        self.send_data2(self.lut_R21_GC[:42])
        self.send_command(0x24)
        self.send_data2(self.lut_R24_GC[:42])
        if self.Flag == 0:
            bw, wb = self.lut_R22_GC, self.lut_R23_GC
            self.Flag = 1
        else:
            bw, wb = self.lut_R23_GC, self.lut_R22_GC
            self.Flag = 0
        self.send_command(0x22)
        self.send_data2(bw[:56])
        self.send_command(0x23)
        self.send_data2(wb[:42])

    def init(self) -> int:
        if epdconfig.module_init() != 0:
            return -1
        self.Flag = 0
        self.reset()
        self.send_command(0x00)
        self.send_data(0xFF)
        self.send_data(0x01)
        self.send_command(0x01)
        for value in (0x03, 0x10, 0x3F, 0x3F, 0x03):
            self.send_data(value)
        self.send_command(0x06)
        for value in (0x37, 0x3D, 0x3D):
            self.send_data(value)
        self.send_command(0x60)
        self.send_data(0x22)
        self.send_command(0x82)
        self.send_data(0x07)
        self.send_command(0x30)
        self.send_data(0x09)
        self.send_command(0xE3)
        self.send_data(0x88)
        self.send_command(0x61)
        for value in (0xF0, 0x01, 0x68):
            self.send_data(value)
        self.send_command(0x50)
        self.send_data(0xB7)
        return 0

    def getbuffer(self, image):
        buffer = [0xFF] * (self.width // 8 * self.height)
        pixels = image.load()
        if image.size == (self.width, self.height):
            for y in range(self.height):
                for x in range(self.width):
                    if pixels[x, y] == 0:
                        buffer[(x + y * self.width) // 8] &= ~(0x80 >> (x % 8))
        elif image.size == (self.height, self.width):
            for y in range(self.width):
                for x in range(self.height):
                    if pixels[x, y] == 0:
                        new_x = y
                        new_y = self.height - x - 1
                        buffer[(new_x + new_y * self.width) // 8] &= ~(
                            0x80 >> (y % 8)
                        )
        return buffer

    def display(self, image) -> None:
        self.send_command(0x13)
        self.send_data2(image)

    def Clear(self) -> None:
        self.display([0xFF] * (self.width * self.height // 8))
        self.lut_GC()
        self.refresh()

    def sleep(self) -> None:
        self.send_command(0x07)
        self.send_data(0xA5)
        epdconfig.delay_ms(2000)
