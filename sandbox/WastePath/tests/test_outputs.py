"""Output behaviour and GPIO cleanup without connecting physical hardware."""
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import time
import unittest
import warnings
from wastepath.outputs import (
    Controller, OutputRule, OutputConfig, default_config, validate_config,
    save_config, load_config,
)


class FakeDevice:
    def __init__(self, pin, **kwargs):
        self.pin = pin
        self.kwargs = kwargs
        self.value = 0
        self._angle = kwargs.get("initial_angle")
        self.events = []
        self.closed = False
        self.fail_on = False
        self.fail_rest = False

    def on(self):
        if self.fail_on:
            raise OSError("lost GPIO")
        self.value = 1
        self.events.append("on")

    def off(self):
        self.value = 0
        self.events.append("off")
        if self.fail_rest:
            raise OSError("rest failed")

    @property
    def angle(self):
        return self._angle

    @angle.setter
    def angle(self, value):
        if self.fail_on:
            raise OSError("lost PWM")
        self._angle = value
        self.events.append(value)

    def close(self):
        self.closed = True
        self.events.append("close")


class FakeFactory:
    def __init__(self):
        self.devices = {}
        self.fail_servo = False

    def LED(self, pin, **kwargs):
        device = FakeDevice(pin, **kwargs)
        self.devices[pin] = device
        return device

    def AngularServo(self, pin, **kwargs):
        if self.fail_servo:
            raise OSError("PWM unavailable")
        device = FakeDevice(pin, **kwargs)
        self.devices[pin] = device
        return device


class ConfigTests(unittest.TestCase):
    def test_defaults_and_custom_angles_round_trip_without_arming(self):
        config = default_config()
        config.rules[1].active_angle = 125
        config.rules[1].rest_angle = 15
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"gpio.json"
            save_config(path, config)
            self.assertEqual(load_config(path), config)
            payload = json.loads(path.read_text())
            self.assertEqual(set(payload), {"version", "rules"})
            save_config(path, OutputConfig([]))
            self.assertEqual(load_config(path).rules, [])
            self.assertEqual(list(Path(folder).iterdir()), [path])

    def test_invalid_labels_pins_duplicates_kinds_and_angles_are_rejected(self):
        bad = [
            OutputConfig([OutputRule(2, "led", 17)]),
            OutputConfig([OutputRule(True, "led", 17)]),
            OutputConfig([OutputRule(0, "led", 1)]),
            OutputConfig([OutputRule(0, "led", 28)]),
            OutputConfig([OutputRule(0, "led", True)]),
            OutputConfig([OutputRule(0, "motor", 17)]),
            OutputConfig([OutputRule(0, "led", 17), OutputRule(1, "servo", 17)]),
            OutputConfig([OutputRule(0, "led", 17), OutputRule(0, "servo", 18)]),
            OutputConfig([OutputRule(1, "servo", 18, active_angle=float("nan"))]),
            OutputConfig([OutputRule(1, "servo", 18, active_angle=float("inf"))]),
            OutputConfig([OutputRule(1, "servo", 18, rest_angle=-1)]),
            OutputConfig([OutputRule(1, "servo", 18, active_angle=181)]),
            OutputConfig([OutputRule(1, "servo", 18, active_angle="90")]),
        ]
        for config in bad:
            with self.subTest(config=config), self.assertRaises(ValueError):
                validate_config(config)
        validate_config(OutputConfig([OutputRule(0, "off", 17), OutputRule(1, "servo", 17)]))

    def test_loading_rejects_unsupported_file_and_does_not_modify_it(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"gpio.json"
            for contents in ('{}', '{"version":1,"rules":null}', '{"version":1,"rules":[{"label":0,"kind":"led","pin":99}]}', '{"version":1,"rules":[],"armed":true}'):
                path.write_text(contents)
                with self.assertRaises(ValueError): load_config(path)
                self.assertEqual(path.read_text(), contents)


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.now = 0.
        self.factory = FakeFactory()
        self.controller = Controller(factory=self.factory, clock=lambda: self.now)
        self.addCleanup(self.controller.close)

    def test_simulation_never_allocates_gpio_and_returns_to_neutral(self):
        c = self.controller
        self.assertFalse(c.armed)
        c.update(0)
        self.assertIn("Waste: LED BCM17 ON", c.state_text)
        self.assertIn("servo BCM18 0°", c.state_text)
        c.update(1)
        self.assertIn("LED BCM17 off", c.state_text)
        self.assertIn("servo BCM18 90°", c.state_text)
        c.neutral()
        self.assertIn("servo BCM18 0°", c.state_text)
        self.assertEqual(self.factory.devices, {})

    def test_real_rules_switch_and_repeated_updates_do_not_rewrite_servo(self):
        c = self.controller
        c.update(1)  # Existing simulated prediction must not activate on arm.
        self.assertTrue(c.arm())
        led, servo = self.factory.devices[17], self.factory.devices[18]
        self.assertEqual(led.value, 0)
        self.assertEqual(servo.angle, 0)
        self.assertEqual(servo.kwargs['min_pulse_width'], .001)
        self.assertEqual(servo.kwargs['max_pulse_width'], .002)
        c.update(1)
        self.assertEqual(servo.angle, 90)
        before = list(servo.events)
        for _ in range(20): c.update(1)
        self.assertEqual(servo.events, before)
        c.update(0)
        self.assertEqual(servo.angle, 0)
        self.assertEqual(led.value, 1)
        c.neutral()
        self.assertEqual(led.value, 0)
        self.assertEqual(servo.angle, 0)
        c.disarm()
        self.assertFalse(c.armed)
        self.assertTrue(led.closed and servo.closed)

    def test_configure_releases_old_devices_before_changing_pins_and_copies_settings(self):
        c = self.controller
        c.arm(); c.update(0)
        old_devices = list(self.factory.devices.values())
        config = OutputConfig([OutputRule(0, "servo", 22, 120, 20), OutputRule(1, "led", 23)])
        c.configure(config)
        self.assertTrue(all(d.closed for d in old_devices))
        self.assertFalse(c.armed)
        config.rules[0].pin = 99
        self.assertEqual(c.config.rules[0].pin, 22)
        self.assertTrue(c.arm())
        c.update(0)
        self.assertEqual(self.factory.devices[22].angle, 120)
        c.update(1)
        self.assertEqual(self.factory.devices[22].angle, 20)
        self.assertEqual(self.factory.devices[23].value, 1)

    def test_invalid_config_disarms_existing_gpio(self):
        c = self.controller
        c.arm(); c.update(0)
        with self.assertRaises(ValueError):
            c.configure(OutputConfig([OutputRule(0, "led", -1)]))
        self.assertFalse(c.armed)
        self.assertTrue(all(d.closed for d in self.factory.devices.values()))

    def test_partial_start_and_write_faults_release_all_devices_and_require_rearm(self):
        c = self.controller
        self.factory.fail_servo = True
        self.assertFalse(c.arm())
        self.assertFalse(c.armed)
        self.assertTrue(self.factory.devices[17].closed)
        self.assertIn("PWM unavailable", c.error)
        self.factory.fail_servo = False
        self.assertTrue(c.arm())
        led = self.factory.devices[17]
        servo = self.factory.devices[18]
        led.fail_on = True
        c.update(0)
        self.assertFalse(c.armed)
        self.assertTrue(led.closed and servo.closed)
        self.assertIn("lost GPIO", c.error)
        c.disarm()
        self.assertIn("lost GPIO", c.error)
        c.update(1)
        self.assertFalse(c.armed)
        self.assertEqual(servo.angle, 0)
        self.assertTrue(c.arm())
        self.assertEqual(c.error, "")
        self.assertEqual(self.factory.devices[18].angle, 0)

    def test_cleanup_continues_when_one_output_cannot_rest(self):
        c = self.controller
        c.arm()
        led, servo = self.factory.devices[17], self.factory.devices[18]
        led.fail_rest = True
        c.disarm()
        self.assertTrue(led.closed and servo.closed)
        self.assertIn("rest failed", c.error)

    def test_watchdog_disarms_without_tk_and_does_not_rearm_on_prediction(self):
        c = self.controller
        self.assertTrue(c.arm())
        c.update(1)
        devices = list(self.factory.devices.values())
        self.now = 1.6
        deadline = time.monotonic()+1
        # The independent real watchdog thread must notice the stale heartbeat.
        while c.armed and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertFalse(c.armed)
        self.assertIn("No fresh decisions", c.error)
        self.assertTrue(all(d.closed for d in devices))
        c.update(1)
        self.assertFalse(c.armed)
        self.assertTrue(c.arm())
        self.now += 1.0
        c.update(None)
        self.now += 1.0
        self.assertFalse(c.check_watchdog())

    def test_invalid_prediction_disarms_and_closed_controller_cannot_rearm(self):
        c = self.controller
        c.arm(); c.update(0)
        c.update(2)
        self.assertFalse(c.armed)
        self.assertIn("Invalid detection", c.error)
        c.close()
        self.assertFalse(c.arm())
        self.assertFalse(c._watchdog.is_alive())

    def test_gpiozero_mock_pwm_and_pin_reservations(self):
        from gpiozero import LED, AngularServo
        from gpiozero.pins.mock import MockFactory, MockPWMPin
        from gpiozero.exc import PWMSoftwareFallback
        pins = MockFactory(pin_class=MockPWMPin)
        factory = SimpleNamespace(
            LED=lambda *a, **kw: LED(*a, pin_factory=pins, **kw),
            AngularServo=lambda *a, **kw: AngularServo(*a, pin_factory=pins, **kw),
        )
        c = Controller(factory=factory)
        self.addCleanup(c.close)
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', PWMSoftwareFallback)
            self.assertTrue(c.arm(), c.error)
        c.update(1)
        self.assertAlmostEqual(c._devices[1].angle, 90)
        self.assertGreater(pins.pin(18).state, 0)
        c.update(0)
        self.assertTrue(pins.pin(17).state)
        self.assertAlmostEqual(c._devices[1].angle, 0)
        c.neutral()
        self.assertFalse(pins.pin(17).state)
        c.close()
        # Reclaiming both pins demonstrates release of gpiozero reservations.
        led = LED(17, pin_factory=pins)
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', PWMSoftwareFallback)
            servo = AngularServo(18, pin_factory=pins)
        led.close(); servo.close()


if __name__ == '__main__':
    unittest.main()
