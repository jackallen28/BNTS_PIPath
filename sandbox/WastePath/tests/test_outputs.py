"""Output behaviour and GPIO cleanup without connecting physical hardware."""
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import time
import unittest
import warnings
from wastepath.outputs import (
    Controller, OutputRule, OutputConfig, ServoDriver, default_config, validate_config,
    save_config, load_config,
)
from wastepath.bin_setup import BinSetup, SimulatedBin


class FakeDevice:
    def __init__(self, pin, **kwargs):
        self.pin = pin
        self.last = None
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

    def blink(self,**kwargs):
        if self.fail_on: raise OSError("lost GPIO")
        self.value=1
        self.events.append("blink")

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
        if value is not None:
            self.last = value
        self.events.append(value)

    def close(self):
        self.closed = True
        self.events.append("close")


class FakeButton:
    """Pressed when `pressed(servo_angle)` says the lid is shut."""
    def __init__(self, factory, pin):
        self.factory, self.pin, self.closed = factory, pin, False

    @property
    def value(self):
        servo = self.factory.servo
        angle = servo.last if servo is not None else None
        return int(self.factory.pressed(angle))

    def close(self):
        self.closed = True


class FakeFactory:
    def __init__(self, pressed=lambda angle: False):
        self.devices = {}
        self.fail_servo = False
        self.pressed = pressed
        self.servo = None

    def InputDevice(self, pin, **kwargs):
        self.button_kwargs = kwargs
        device = FakeButton(self, pin)
        self.devices[pin] = device
        return device

    def LED(self, pin, **kwargs):
        device = FakeDevice(pin, **kwargs)
        self.devices[pin] = device
        return device

    def AngularServo(self, pin, **kwargs):
        if self.fail_servo:
            raise OSError("PWM unavailable")
        device = FakeDevice(pin, **kwargs)
        self.devices[pin] = device
        self.servo = device
        return device


def fast_servo(test):
    """Run the lid's timing quickly, so a full sweep takes a fraction of a second."""
    for name, value in (("STEP_SECONDS", .001), ("SETTLE_SECONDS", .01),
                        ("RELEASE_SECONDS", .02), ("HOLD_OPEN_SECONDS", 0)):
        old = getattr(ServoDriver, name)
        setattr(ServoDriver, name, value)
        test.addCleanup(setattr, ServoDriver, name, old)


def wait_for(condition, seconds=3):
    deadline = time.monotonic() + seconds
    while not condition() and time.monotonic() < deadline:
        time.sleep(.005)
    return condition()


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
            OutputConfig([OutputRule(1, "servo", 18, 90, 90)]),
            OutputConfig([OutputRule(1, "servo", 18, button_pin=18)]),
            OutputConfig([OutputRule(1, "servo", 18, button_pin=1)]),
            OutputConfig([OutputRule(1, "servo", 18, button_pin=True)]),
            OutputConfig([OutputRule(0, "led", 23), OutputRule(1, "servo", 18, button_pin=23)]),
        ]
        for config in bad:
            with self.subTest(config=config), self.assertRaises(ValueError):
                validate_config(config)
        validate_config(OutputConfig([OutputRule(0, "off", 17), OutputRule(1, "servo", 17)]))

    def test_closed_button_round_trips_and_older_files_still_load(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"gpio.json"
            config = OutputConfig([OutputRule(0, "led", 17), OutputRule(1, "servo", 18, 70, 125, 23)])
            save_config(path, config)
            self.assertEqual(load_config(path).rules[1].button_pin, 23)
            path.write_text('{"version":1,"rules":[{"label":1,"kind":"servo","pin":18,"active_angle":90,"rest_angle":0}]}')
            self.assertEqual(load_config(path).rules[0].button_pin, 0)

    def test_loading_rejects_unsupported_file_and_does_not_modify_it(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"gpio.json"
            for contents in ('{}', '{"version":1,"rules":null}', '{"version":1,"rules":[{"label":0,"kind":"led","pin":99}]}', '{"version":1,"rules":[],"armed":true}'):
                path.write_text(contents)
                with self.assertRaises(ValueError): load_config(path)
                self.assertEqual(path.read_text(), contents)


class ControllerTests(unittest.TestCase):
    def setUp(self):
        fast_servo(self)
        self.now = 0.
        self.factory = FakeFactory()
        self.controller = Controller(factory=self.factory, clock=lambda: self.now)
        self.addCleanup(self.controller.close)

    def closed(self, lid):
        self.assertTrue(wait_for(lambda: lid.state == "closed"), lid.state)

    def test_simulation_never_allocates_gpio_and_returns_to_neutral(self):
        c = self.controller
        self.assertFalse(c.armed)
        c.update(0)
        self.assertIn("Waste: LED BCM17 FLASHING", c.state_text)
        self.assertIn("servo BCM18 0°", c.state_text)
        c.update(1)
        self.assertIn("LED BCM17 off", c.state_text)
        self.assertIn("servo BCM18 90°", c.state_text)
        c.neutral()
        self.assertIn("servo BCM18 0°", c.state_text)
        self.assertEqual(self.factory.devices, {})

    def test_servo_opens_at_once_then_sweeps_closed_one_degree_at_a_time_and_goes_limp(self):
        c = self.controller
        c.update(1)  # Existing simulated prediction must not activate on arm.
        self.assertTrue(c.arm())
        led, servo, lid = self.factory.devices[17], self.factory.devices[18], c._devices[1]
        self.assertIsNone(servo.kwargs['initial_angle'])
        self.assertEqual(servo.kwargs['min_pulse_width'], .001)
        self.assertEqual(servo.kwargs['max_pulse_width'], .002)
        self.closed(lid)                      # no button: rests at the closed angle...
        self.assertEqual(servo.events[:1], [0])
        self.assertIsNone(servo.angle)        # ...then goes limp, no buzzing
        self.assertEqual(led.value, 0)
        c.update(1)
        self.assertEqual(servo.angle, 90)     # opens straight away
        before = list(servo.events)
        for _ in range(20): c.update(1)
        self.assertEqual(servo.events, before)
        self.assertIn("servo BCM18 open 90°", c.state_text)
        c.update(0)
        self.assertEqual(led.value, 1)
        self.closed(lid)
        sweep = [e for e in servo.events[len(before):] if e is not None]
        self.assertEqual(sweep, [float(a) for a in range(90, -1, -1)])
        self.assertIsNone(servo.events[-1])
        c.neutral()
        self.assertEqual(led.value, 0)
        c.disarm()
        self.assertFalse(c.armed)
        self.assertTrue(led.closed)
        self.assertTrue(wait_for(lambda: servo.closed))

    def test_closing_stops_when_the_lid_presses_the_button(self):
        self.factory.pressed = lambda angle: angle is not None and angle >= 120
        c = Controller(OutputConfig([OutputRule(1, "servo", 18, 70, 120, 23)]), factory=self.factory)
        self.addCleanup(c.close)
        self.assertTrue(c.arm())
        lid, servo = c._devices[1], self.factory.devices[18]
        self.assertEqual(self.factory.button_kwargs, {"pull_up": True})
        # At start-up it homes from the open angle, like the Arduino bin.
        self.closed(lid)
        self.assertEqual(servo.events[0], 70)
        self.assertEqual(lid.found, 120)
        self.assertEqual(max(e for e in servo.events if e is not None), 120)
        self.assertIsNone(servo.angle)
        c.update(1)
        self.assertEqual(servo.angle, 70)
        c.update(None)
        self.closed(lid)
        self.assertEqual(lid.found, 120)
        self.assertEqual(lid.fault, "")

    def test_button_that_never_presses_rests_at_the_saved_angle_with_a_warning(self):
        c = Controller(OutputConfig([OutputRule(1, "servo", 18, 70, 125, 23)]), factory=self.factory)
        self.addCleanup(c.close)
        self.assertTrue(c.arm())
        lid, servo = c._devices[1], self.factory.devices[18]
        self.closed(lid)
        moved = [e for e in servo.events if e is not None]
        self.assertEqual(max(moved), 140)     # 15° past the saved angle, never further
        self.assertEqual(moved[-1], 125)      # then rests at the saved closed angle
        self.assertIn("button didn't press", lid.fault)
        self.assertIn("⚠", c.state_text)

    def test_lid_stays_open_a_moment_and_a_stuck_button_is_reported(self):
        ServoDriver.HOLD_OPEN_SECONDS = .3
        self.factory.pressed = lambda angle: True   # stuck down
        lid = ServoDriver(FakeDevice(18), 70, 125, FakeButton(self.factory, 23), home=False)
        self.addCleanup(lid.stop_now)
        self.factory.servo = lid.servo
        lid.open(); lid.close()
        time.sleep(.1)
        self.assertEqual(lid.state, "open")
        self.assertTrue(wait_for(lambda: "still pressed" in lid.fault))

    def test_already_shut_lid_does_not_move_when_armed(self):
        self.factory.pressed = lambda angle: True
        c = Controller(OutputConfig([OutputRule(1, "servo", 18, 70, 125, 23)]), factory=self.factory)
        self.addCleanup(c.close)
        self.assertTrue(c.arm())
        time.sleep(.05)
        self.assertEqual(self.factory.devices[18].events, [])
        self.assertEqual(c._devices[1].state, "closed")

    def test_configure_releases_old_devices_before_changing_pins_and_copies_settings(self):
        c = self.controller
        c.arm(); c.update(0)
        old_devices = list(self.factory.devices.values())
        config = OutputConfig([OutputRule(0, "servo", 22, 120, 20), OutputRule(1, "led", 23)])
        c.configure(config)
        self.assertFalse(c.armed)
        self.assertTrue(wait_for(lambda: all(d.closed for d in old_devices)))
        self.assertFalse(c.lid_closing)
        config.rules[0].pin = 99
        self.assertEqual(c.config.rules[0].pin, 22)
        self.assertTrue(c.arm())
        c.update(0)
        self.assertEqual(self.factory.devices[22].angle, 120)
        c.update(1)
        self.closed(c._devices[0])
        self.assertEqual(self.factory.devices[22].last, 20)
        self.assertEqual(self.factory.devices[23].value, 1)

    def test_rearming_waits_for_a_closing_lid(self):
        c = self.controller
        ServoDriver.STEP_SECONDS = .01
        c.arm(); c.update(1); c.disarm()     # the lid now sweeps 90° closed
        self.assertTrue(c.lid_closing)
        self.assertFalse(c.arm())
        self.assertIn("still closing", c.error)
        self.assertTrue(wait_for(lambda: not c.lid_closing, 5))
        self.assertTrue(c.arm())

    def test_actual_gpiozero_mock_led_toggles_and_stops_flashing(self):
        from gpiozero import LED
        from gpiozero.pins.mock import MockFactory
        pins=MockFactory()
        c=Controller(OutputConfig([OutputRule(0,"led",17)]),
                     factory=SimpleNamespace(LED=lambda *a,**kw: LED(*a,pin_factory=pins,**kw)))
        self.addCleanup(c.close)
        self.assertTrue(c.arm())
        c.update(0)
        deadline=time.monotonic()+1
        pin=pins.pin(17)
        while len(pin.states)<3 and time.monotonic()<deadline:
            time.sleep(.02)
        self.assertGreaterEqual(len(pin.states),3)
        self.assertEqual([s.state for s in pin.states[:3]],[False,True,False])
        c.neutral()
        count=len(pin.states)
        time.sleep(.35)
        self.assertFalse(pin.state)
        self.assertEqual(len(pin.states),count)

    def test_invalid_config_disarms_existing_gpio(self):
        c = self.controller
        c.arm(); c.update(0)
        with self.assertRaises(ValueError):
            c.configure(OutputConfig([OutputRule(0, "led", -1)]))
        self.assertFalse(c.armed)
        self.assertTrue(wait_for(lambda: all(d.closed for d in self.factory.devices.values())))

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
        self.assertTrue(led.closed)
        self.assertTrue(wait_for(lambda: servo.closed))
        self.assertIn("lost GPIO", c.error)
        c.disarm()
        self.assertIn("lost GPIO", c.error)
        c.update(1)
        self.assertFalse(c.armed)
        self.assertTrue(c.arm())
        self.assertEqual(c.error, "")

    def test_servo_write_fault_in_the_lid_thread_stops_outputs(self):
        c = self.controller
        self.assertTrue(c.arm())
        servo = self.factory.devices[18]
        self.closed(c._devices[1])
        c.update(1)
        servo.fail_on = True
        c.update(0)                           # the sweep fails on its first step
        self.assertTrue(wait_for(lambda: not c.armed))
        self.assertIn("lost PWM", c.error)
        self.assertTrue(wait_for(lambda: servo.closed))

    def test_cleanup_continues_when_one_output_cannot_rest(self):
        c = self.controller
        c.arm()
        led, servo = self.factory.devices[17], self.factory.devices[18]
        led.fail_rest = True
        c.disarm()
        self.assertTrue(led.closed)
        self.assertTrue(wait_for(lambda: servo.closed))
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
        self.assertTrue(wait_for(lambda: all(d.closed for d in devices)))
        self.assertEqual(self.factory.devices[18].last, 0)   # the open lid closed first
        c.update(1)
        self.assertFalse(c.armed)
        self.assertTrue(c.arm())
        self.now += 1.0
        c.update(None)
        self.now += 1.0
        self.assertFalse(c.check_watchdog())

    def test_wrong_or_unknown_item_flashes_led_and_never_opens_servo(self):
        c=self.controller
        self.assertTrue(c.arm())
        led,servo,lid=self.factory.devices[17],self.factory.devices[18],c._devices[1]
        c.update(1)
        self.assertEqual(servo.angle,90)
        c.update(None,rejected=True)
        self.closed(lid)
        self.assertEqual(servo.last,0)
        self.assertEqual(led.events[-1],"blink")
        self.assertIn("FLASHING",c.state_text)
        before=list(led.events)
        c.update(None,rejected=True)
        self.assertEqual(led.events,before)
        c.update(None)
        self.assertEqual(led.events[-1],"off")
        c.update(0)
        self.assertEqual(led.events[-1],"blink")
        self.assertEqual(lid.state,"closed")
        c.update(1)
        self.assertEqual(led.events[-1],"off")
        self.assertEqual(servo.angle,90)

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
        from gpiozero import LED, AngularServo, InputDevice
        from gpiozero.pins.mock import MockFactory, MockPWMPin
        from gpiozero.exc import PWMSoftwareFallback
        pins = MockFactory(pin_class=MockPWMPin)
        factory = SimpleNamespace(
            LED=lambda *a, **kw: LED(*a, pin_factory=pins, **kw),
            AngularServo=lambda *a, **kw: AngularServo(*a, pin_factory=pins, **kw),
            InputDevice=lambda *a, **kw: InputDevice(*a, pin_factory=pins, **kw),
        )
        config = OutputConfig([OutputRule(0, "led", 17), OutputRule(1, "servo", 18, 90, 0, 23)])
        c = Controller(config, factory=factory)
        self.addCleanup(c.close)
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', PWMSoftwareFallback)
            self.assertTrue(c.arm(), c.error)
        self.assertFalse(c._devices[1].pressed())   # the Pi's pull-up: not pressed
        pins.pin(23).drive_low()   # the lid shuts: the button joins GPIO23 to GND
        self.assertTrue(c._devices[1].pressed())
        self.closed(c._devices[1])
        c.update(1)
        self.assertAlmostEqual(pins.pin(18).state, .075)
        pins.pin(23).drive_high()  # the lid lifts off the button
        c.update(0)
        self.assertIsNotNone(c._devices[0]._blink_thread)
        self.assertTrue(wait_for(lambda: c._devices[1].position <= 45))
        pins.pin(23).drive_low()   # ...and presses it again on the way down
        self.closed(c._devices[1])
        self.assertGreater(c._devices[1].found, 30)
        self.assertEqual(pins.pin(18).state, 0)   # limp
        c.neutral()
        self.assertFalse(pins.pin(17).state)
        c.close()
        # Reclaiming every pin demonstrates release of gpiozero reservations.
        led = LED(17, pin_factory=pins)
        button = InputDevice(23, pin_factory=pins)
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', PWMSoftwareFallback)
            servo = AngularServo(18, pin_factory=pins)
        led.close(); servo.close(); button.close()


class BinSetupTests(unittest.TestCase):
    def setUp(self):
        fast_servo(self)

    def setup_for(self, sim, closes_up=True, start=60, opening=60):
        setup = BinSetup(sim, 18, 23, closes_up=closes_up, start_angle=start, opening=opening)
        self.addCleanup(lambda: setup.release().join(3))
        return setup

    def finish(self, setup):
        self.assertTrue(wait_for(lambda: setup.update() != "homing"))
        return setup.phase

    def test_homes_on_the_button_then_opens_by_itself(self):
        sim = SimulatedBin(closed_at=120)
        setup = self.setup_for(sim)
        setup.start()
        self.assertEqual(setup.phase, "homing")
        self.assertEqual(self.finish(setup), "confirm closed")
        self.assertEqual(setup.closed, 120)
        self.assertTrue(setup.pressed)
        self.assertFalse(setup.ready)
        self.assertTrue(setup.lid_is_shut())
        self.assertEqual(setup.phase, "confirm open")
        self.assertEqual(setup.open_angle, 60)          # 60° from closed
        self.assertEqual(sim.servo.last, 60)
        setup.open_by(1)
        self.assertEqual(setup.open_angle, 55)
        for _ in range(20): setup.open_by(-1)           # never closer than 5° from closed
        self.assertEqual(setup.open_angle, 115)
        rule = setup.rule(1)
        self.assertEqual((rule.pin, rule.button_pin, rule.active_angle, rule.rest_angle), (18, 23, 115, 120))
        validate_config(OutputConfig([rule]))
        lid = setup.release()
        self.assertTrue(lid.join(3))
        self.assertEqual(sim.servo.last, 120)           # closed onto the button before stopping

    def test_close_more_saves_a_closed_angle_just_past_the_press(self):
        sim = SimulatedBin(closed_at=120)
        setup = self.setup_for(sim)
        setup.start(); self.finish(setup)
        self.assertTrue(setup.close_more())
        self.assertEqual((setup.closed, sim.servo.last), (125, 125))
        for _ in range(5): setup.close_more()
        self.assertEqual(setup.closed, 135)             # at most 15° past the press
        setup.lid_is_shut()
        self.assertEqual(setup.open_angle, 75)
        rule = setup.rule(1)
        # In Live it closes onto the button and then on to the saved 135°.
        lid = ServoDriver(sim.AngularServo(18), rule.active_angle, rule.rest_angle,
                          sim.InputDevice(23), home=False)
        self.addCleanup(lid.stop_now)
        lid.open(); lid.close()
        self.assertTrue(wait_for(lambda: lid.state == "closed"))
        self.assertEqual((lid.found, lid.position), (120, 135))

    def test_wrong_direction_reaches_the_end_without_a_press(self):
        sim = SimulatedBin(closed_at=120)
        setup = self.setup_for(sim, closes_up=False, start=110)
        setup.start()
        self.assertEqual(self.finish(setup), "no press")
        self.assertEqual(sim.servo.last, 0)
        self.assertIn("didn't press", setup.lid.fault)
        self.assertFalse(setup.lid_is_shut())

    def test_button_still_pressed_after_lifting_is_reported(self):
        sim = SimulatedBin(closed_at=120)
        setup = self.setup_for(sim, start=130)          # lifting the "wrong" way keeps it pressed
        setup.start()
        self.assertEqual(self.finish(setup), "no press")
        self.assertIn("still pressed at 130", setup.lid.fault)


if __name__ == '__main__':
    unittest.main()
