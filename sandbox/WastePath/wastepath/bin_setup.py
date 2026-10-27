"""Bin set-up (automatic hardware calibration), like the BNTS Arduino bin's power-up.

1. Home: the lid lifts, then the servo closes 1° at a time until the lid presses
   the closed button. That angle is "closed". The user confirms the lid is shut
   (or closes it 5° more).
2. Open: the servo opens to the usual opening (60° from closed, or the saved one).
   The user confirms it is open far enough (or opens it 5° more or less).
3. Save: the lid closes onto the button and the angles and pins are saved.
"""
from .outputs import OutputRule, make_lid

STEP_DEGREES = 5
MIN_OPENING = 5        # the open angle stays at least this far from closed
DEFAULT_OPENING = 60   # how far the lid opens before the user adjusts it
MAX_EXTRA_CLOSE = 15   # "close 5° more" can go this far past the button press

# The steps of the set-up, in order.
HOMING, NO_PRESS, CONFIRM_CLOSED, CONFIRM_OPEN = "homing", "no press", "confirm closed", "confirm open"


class BinSetup:
    def __init__(self, factory, servo_pin, button_pin, closes_up, start_angle=90, opening=DEFAULT_OPENING):
        self.servo_pin, self.button_pin = servo_pin, button_pin
        self.direction = 1 if closes_up else -1
        self.start_angle = float(start_angle)
        self.opening = float(opening)
        self.phase = None
        self.closed = None       # the confirmed closed angle (button press, plus any extra)
        self.open_angle = None
        # A rule with a placeholder closed angle at the far end, until the button finds it.
        rule = OutputRule(1, "servo", servo_pin, self.start_angle, 180.0 if closes_up else 0.0, button_pin)
        self.lid = make_lid(factory, rule, home=False)

    @property
    def pressed(self):
        return self.lid.pressed()

    def start(self):
        """Home onto the button, then wait for the user to confirm the lid is shut."""
        self.closed = self.open_angle = None
        self.phase = HOMING
        self.lid.home(self.start_angle, self.direction)

    def update(self):
        """Call regularly: moves on once homing has finished."""
        if self.phase == HOMING and self.lid.state == "closed":
            if self.lid.found is not None and not self.lid.fault:
                self.closed = self.lid.found
                self.phase = CONFIRM_CLOSED
            else:
                self.phase = NO_PRESS
        return self.phase

    def close_more(self):
        """The button pressed but the lid isn't quite shut: close 5° further."""
        if self.phase != CONFIRM_CLOSED:
            return False
        angle = self.closed + self.direction * STEP_DEGREES
        if (angle - self.lid.found) * self.direction > MAX_EXTRA_CLOSE or not 0 <= angle <= 180:
            return False
        self.closed = angle
        self.lid.open(angle)    # hold it there
        return True

    def lid_is_shut(self):
        """Confirmed: open the lid by the usual amount, ready to confirm or adjust."""
        if self.phase != CONFIRM_CLOSED:
            return False
        angle = min(180.0, max(0.0, self.closed - self.direction * self.opening))
        if (self.closed - angle) * self.direction < MIN_OPENING:
            angle = self.closed - self.direction * MIN_OPENING
        self.open_angle = angle
        self.lid.closed_angle = self.closed
        self.lid.open(angle)
        self.phase = CONFIRM_OPEN
        return True

    def open_by(self, steps):
        """Open (+) or close (-) the open position by 5° steps."""
        if self.phase != CONFIRM_OPEN:
            return False
        angle = min(180.0, max(0.0, self.open_angle - self.direction * STEP_DEGREES * steps))
        if (self.closed - angle) * self.direction < MIN_OPENING:
            angle = self.closed - self.direction * MIN_OPENING
        self.open_angle = angle
        self.lid.open(angle)
        return True

    @property
    def ready(self):
        return self.phase == CONFIRM_OPEN

    def rule(self, label):
        return OutputRule(label, "servo", self.servo_pin, float(self.open_angle),
                          float(self.closed), self.button_pin)

    def release(self):
        """Close the lid onto the button (in the background), then free the pins."""
        if self.closed is not None:
            self.lid.closed_angle = self.closed
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
