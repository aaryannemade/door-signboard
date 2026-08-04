import hashlib
import os
import unittest

from door_signboard import Scene, SignContent, generate_image


class DisplayTests(unittest.TestCase):
    def test_each_scene_generates_a_distinct_monochrome_image(self) -> None:
        digests = set()

        for scene in Scene:
            image = generate_image(scene)
            colors = {color for _, color in image.convert("L").getcolors()}

            self.assertEqual(image.size, (360, 240))
            self.assertEqual(image.mode, "1")
            self.assertLessEqual(colors, {0, 255})
            self.assertIn(0, colors)
            self.assertEqual(image.getpixel((0, 0)), 255)
            self.assertEqual(image.getpixel((1, 1)), 255)
            self.assertEqual(image.getpixel((2, 2)), 0)
            self.assertEqual(image.getpixel((357, 237)), 0)
            self.assertEqual(image.getpixel((359, 239)), 255)
            digests.add(hashlib.sha256(image.tobytes()).hexdigest())

        self.assertEqual(len(digests), len(Scene))

    def test_scene_selects_its_message(self) -> None:
        content = SignContent(
            delivery_message="delivery text",
            away_message="away text",
            busy_message="busy text",
        )

        self.assertEqual(content.message_for(Scene.DELIVERY), "delivery text")
        self.assertEqual(content.message_for(Scene.AWAY), "away text")
        self.assertEqual(content.message_for(Scene.BUSY), "busy text")

    def test_message_scenes_have_black_header_banners(self) -> None:
        delivery = generate_image(Scene.DELIVERY)
        away = generate_image(Scene.AWAY)
        busy = generate_image(Scene.BUSY)

        self.assertEqual(delivery.getpixel((3, 3)), 0)
        self.assertEqual(delivery.getpixel((356, 42)), 0)
        self.assertEqual(away.getpixel((3, 3)), 0)
        self.assertEqual(away.getpixel((356, 42)), 0)
        self.assertEqual(busy.getpixel((3, 3)), 0)
        self.assertEqual(busy.getpixel((356, 42)), 0)

    def test_delivery_and_busy_do_not_show_phone_number(self) -> None:
        first = SignContent(apartment_number="42", phone_number="111")
        second = SignContent(apartment_number="42", phone_number="999")
        different_apartment = SignContent(apartment_number="43", phone_number="111")

        for scene in (Scene.DELIVERY, Scene.BUSY):
            first_image = generate_image(scene, first).tobytes()

            self.assertEqual(first_image, generate_image(scene, second).tobytes())
            self.assertNotEqual(
                first_image,
                generate_image(scene, different_apartment).tobytes(),
            )

    def test_away_scene_shows_phone_and_apartment_separately(self) -> None:
        original = SignContent(apartment_number="42", phone_number="110000000000")
        different_phone = SignContent(
            apartment_number="42", phone_number="990000000000"
        )
        different_apartment = SignContent(
            apartment_number="43", phone_number="110000000000"
        )
        original_image = generate_image(Scene.AWAY, original).tobytes()

        self.assertNotEqual(
            original_image,
            generate_image(Scene.AWAY, different_phone).tobytes(),
        )
        self.assertNotEqual(
            original_image,
            generate_image(Scene.AWAY, different_apartment).tobytes(),
        )

    def test_delivery_otp_is_optional_and_only_changes_delivery(self) -> None:
        without_otp = SignContent(delivery_otp=None)
        empty_otp = SignContent(delivery_otp="  ")
        with_otp = SignContent(delivery_otp="123456")

        delivery_without_otp = generate_image(Scene.DELIVERY, without_otp).tobytes()
        self.assertEqual(
            delivery_without_otp,
            generate_image(Scene.DELIVERY, empty_otp).tobytes(),
        )
        self.assertNotEqual(
            delivery_without_otp,
            generate_image(Scene.DELIVERY, with_otp).tobytes(),
        )
        self.assertEqual(
            generate_image(Scene.AWAY, without_otp).tobytes(),
            generate_image(Scene.AWAY, with_otp).tobytes(),
        )

    def test_phone_number_is_formatted_with_country_code(self) -> None:
        with_plus = SignContent(phone_number="+919876543210")
        without_plus = SignContent(phone_number="919876543210")

        self.assertEqual(with_plus.formatted_phone_number(), "+91 98765 43210")
        self.assertEqual(without_plus.formatted_phone_number(), "+91 98765 43210")

    def test_invalid_phone_number_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "exactly 12 digits"):
            SignContent(phone_number="+91 98765 43210").formatted_phone_number()

    def test_default_scene_ignores_scene_messages_and_phone_number(self) -> None:
        first = SignContent(
            name="Resident",
            apartment_number="42",
            delivery_message="first delivery message",
            phone_number="111",
        )
        second = SignContent(
            name="Resident",
            apartment_number="42",
            delivery_message="different delivery message",
            phone_number="999",
        )

        image = generate_image(Scene.DEFAULT, first)

        self.assertEqual(image.tobytes(), generate_image(Scene.DEFAULT, second).tobytes())
        self.assertEqual(image.getpixel((3, 3)), 0)
        self.assertEqual(image.getpixel((356, 158)), 0)
        self.assertEqual(image.getpixel((3, 159)), 255)
        self.assertEqual(image.getpixel((356, 236)), 255)

    def test_string_scene_values_are_accepted(self) -> None:
        image = generate_image("delivery")

        self.assertEqual(image.size, (360, 240))

    def test_message_that_cannot_fit_is_rejected(self) -> None:
        content = SignContent(delivery_message="x" * 100)

        with self.assertRaisesRegex(ValueError, "too long"):
            generate_image(Scene.DELIVERY, content)

    def test_missing_font_has_a_clear_error(self) -> None:
        original_font = os.environ.pop("DOOR_SIGNBOARD_FONT", None)
        original_bold_font = os.environ.pop("DOOR_SIGNBOARD_BOLD_FONT", None)
        try:
            with self.assertRaisesRegex(FileNotFoundError, "No usable font found"):
                generate_image(Scene.AWAY, font_path="/missing/font.ttf")
        finally:
            if original_font is not None:
                os.environ["DOOR_SIGNBOARD_FONT"] = original_font
            if original_bold_font is not None:
                os.environ["DOOR_SIGNBOARD_BOLD_FONT"] = original_bold_font


if __name__ == "__main__":
    unittest.main()
