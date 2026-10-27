"""Bin set-up (hardware calibration) after the camera has learnt its photos.

1. Find closed: the servo sweeps 1° at a time until the lid presses the closed button.
2. Set open: from closed, open the lid 5° at a time until it opens far enough.
3. Test it: open, then close until the button presses again. Save the two angles.
"""
from .outputs import OutputRule, make_lid

STEP_DEGREES = 5
MIN_OPENING = 5   # the open angle stays at least this far from closed


class BinSetup:
    def __init__(self, factory, servo_pin, button_pin, closes_up, start_angle=90):
        self.servo_pin, self.button_pin = servo_pin, button_pin
        self.direction = 1 if closes_up else -1
        self.start_angle = float(start_angle)
        self.open_angle = None
        # A rule with a placeholder closed angle at the far end, until the button finds it.
        rule = OutputRule(1, "servo", servo_pin, self.start_angle, 180.0 if closes_up else 0.0, button_pin)
        self.lid = make_lid(factory, rule, home=False)

    @property
    def closed_angle(self):
        return self.lid.found

    @property
    def pressed(self):
        return self.lid.pressed()

    @property
    def homing(self):
        return self.lid.state in ("closing", "settling") and self.lid.found is None

    def find_closed(self):
        """Sweep towards closed from where the lid opens now. False if it can't start."""
        self.open_angle = None
        start = self.lid.position if self.lid.state == "open" else self.start_angle
        return self.lid.home(start, self.direction)

    def open_by(self, steps):
        """Open (+) or close (-) the lid by 5° steps from the found closed angle."""
        closed = self.closed_angle
        if closed is None:
            return False
        current = self.open_angle if self.open_angle is not None else closed
        angle = current - self.direction * STEP_DEGREES * steps
        angle = min(180.0, max(0.0, angle))
        if (closed - angle) * self.direction < MIN_OPENING:
            angle = closed - self.direction * MIN_OPENING
        if not 0 <= angle <= 180:
            return False
        self.open_angle = angle
        self.lid.open(angle)
        self.lid.fault = ""
        return True

    def test_cycle(self):
        """Open to the chosen angle, wait, then close until the button presses."""
        if self.closed_angle is None or self.open_angle is None:
            return False
        self.lid.closed_angle = self.closed_angle
        self.lid.open(self.open_angle)
        self.lid.close()
        return True

    @property
    def ready(self):
        return self.closed_angle is not None and self.open_angle is not None

    def rule(self, label):
        return OutputRule(label, "servo", self.servo_pin, float(self.open_angle),
                          float(self.closed_angle), self.button_pin)

    def release(self):
        """Close the lid gently, then free the pins (in the background)."""
        if self.closed_angle is not None:
            self.lid.closed_angle = self.closed_angle
        self.lid.release()
        return self.lid


class SimulatedBin:
    """A pretend lid for --demo: it shuts (pressing the button) at 120° or more."""
    def __init__(self, closed_at=120):
        self.closed_at = closed_at
        self.servo = None

    def AngularServo(self, pin, **kwargs):
        self.servo = SimServo(pin)
        return self.servo

    def InputDevice(self, pin, **kwargs):
        return SimButton(self, pin)


class SimServo:
    def __init__(self, pin):
        self.pin = pin
        self.last = 90.0
        self.angle = None

    def __setattr__(self, name, value):
        if name == "angle" and value is not None:
            object.__setattr__(self, "last", value)
        object.__setattr__(self, name, value)

    def close(self):
        pass


class SimButton:
    def __init__(self, bin, pin):
        self.bin, self.pin = bin, pin

    @property
    def value(self):
        servo = self.bin.servo
        return int(servo is not None and servo.last >= self.bin.closed_at)

    def close(self):
        pass
