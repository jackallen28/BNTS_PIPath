"""Beginner wiring steps and a hidden, independently checked hardware test."""
from __future__ import annotations

from dataclasses import dataclass, field
from .gpio import SAFETY, wiring_parts

EXPLANATIONS = {
    'led': 'An LED makes light. Its long leg is positive. A series resistor limits current so the LED and Pi stay safe.',
    'rgbled': 'An RGB LED has red, green and blue lights in one package. Each colour needs its own resistor. Check the common leg with your teacher.',
    'button': 'A button is an input. Pressing it joins two contacts so the Pi can detect a press. Use legs on opposite sides of the middle gap.',
    'switch': 'A switch is an input. It joins or separates contacts when it is moved. Your program reads whether the contacts are joined.',
    'buzzer': 'A buzzer turns electrical signals into sound. Check which terminal is marked positive.',
    'pir': 'A motion sensor is an input. It detects changes in infrared energy when a warm object moves. It may need a minute to settle.',
    'distance': 'This ultrasonic sensor sends out sound and times its echo. TRIG sends the pulse. ECHO returns a signal. Its 5V ECHO needs the resistor divider shown below before reaching a Pi GPIO.',
    'servo': 'A positional servo moves an arm to a chosen position. The GPIO sends only its control signal. A separate teacher-approved supply powers the motor; its ground must join Pi ground. Keep fingers clear.',
    'camera': 'A camera is an input. It turns light into picture data. Plug a USB camera into USB, not the GPIO header. Keep it steady and check that its view is clear.',
}


def guide_pages(lesson: dict) -> list[dict]:
    pages = [{'title': 'Before you connect anything', 'kind': 'safety',
              'text': '\n'.join('- ' + s for s in SAFETY) +
                      '\n\nFollow the physical pin numbers in the instructions. GPIO numbers are different from physical pin numbers. '
                      'Ask your teacher to check the wiring before reconnecting the blue HAT. '
                      'The pictures help you recognise parts; check the terminal labels on your own kit.'}]
    for row in lesson.get('wiring', []):
        kind = row.get('kind', 'camera' if 'camera' in row.get('part', '').lower() else 'note')
        steps = row.get('wire_steps') or [row.get('connect', '')]
        for i, instruction in enumerate(steps):
            pages.append({'title': row.get('part', 'Connection') + (f' ({i + 1}/{len(steps)})' if len(steps) > 1 else ''),
                          'kind': kind, 'colour': row.get('colour', 'red'),
                          'pins': row.get('pins') or ([row['pin']] if 'pin' in row else []),
                          'text': EXPLANATIONS.get(kind, '') + '\n\n**Connect this:**\n' + instruction})
    if lesson.get('requires_camera') and not any(p['kind'] == 'camera' for p in pages):
        pages.append({'title':'Connect the camera', 'kind':'camera', 'text':EXPLANATIONS['camera'], 'pins':[]})
    pages.append({'title': 'Check the whole circuit', 'kind': 'test',
                  'text': 'Put the blue HAT back on after your teacher checks the wires. Clear moving parts. '
                          'Start the test, follow its messages, then confirm each part worked. '
                          'You will see the test results, not its code. If anything does not work, go Back, fix it and test again. '
                          'In the Simulator, use the on-screen buttons and sensor controls. '
                          'Passing in the Simulator does not check your real wires.'})
    return pages


def test_items(lesson: dict) -> list[dict]:
    items = [dict(p, id=str(i)) for i, p in enumerate(wiring_parts(lesson))]
    if lesson.get('requires_camera'):
        items.append({'id':'camera', 'kind':'camera', 'label':'Camera', 'pins':[]})
    return items


def wiring_test_program(lesson: dict) -> str:
    """No student code is read or executed. Markers are required before the gate can open."""
    lines = ['from gpiozero import LED, Button, Buzzer, MotionSensor, RGBLED, DistanceSensor, Servo',
             'from time import sleep', 'print("Testing each component. Follow the messages below.", flush=True)']
    for item in test_items(lesson):
        k, pins, ident = item['kind'], item['pins'], item['id']
        name = item['label']
        lines += ['ok = False', f'print({("Now testing: " + name)!r}, flush=True)']
        if k == 'led':
            lines += [f'with LED({pins[0]}) as d:', '    d.blink(0.4, 0.4, n=3, background=False)', '    ok = True']
        elif k == 'rgbled':
            lines += [f'with RGBLED({pins[0]}, {pins[1]}, {pins[2]}) as d:',
                      '    for colour in ((1,0,0), (0,1,0), (0,0,1)):', '        d.color = colour', '        sleep(0.7)', '    ok = True']
        elif k == 'buzzer':
            lines += [f'with Buzzer({pins[0]}) as d:', '    d.beep(0.2, 0.3, n=3, background=False)', '    ok = True']
        elif k in ('button','switch'):
            lines += ['print("Press / activate it now, then release it. You have 15 seconds for each action.", flush=True)',
                      f'with Button({pins[0]}) as d:', '    ok = bool(d.wait_for_press(timeout=15))',
                      '    if ok:', '        ok = bool(d.wait_for_release(timeout=15))']
        elif k == 'pir':
            lines += ['print("Wave in front of the sensor. Allow it to warm up first.", flush=True)',
                      f'with MotionSensor({pins[0]}) as d:', '    ok = bool(d.wait_for_motion(timeout=20))']
        elif k == 'distance':
            lines += ['print("Hold an object about 10 cm in front of the sensor (or move the Simulator slider).", flush=True)',
                      f'with DistanceSensor(echo={pins[0]}, trigger={pins[1]}) as d:',
                      '    for attempt in range(100):', '        if 0.02 <= d.distance <= 0.2:',
                      '            ok = True', '            break', '        sleep(0.2)']
        elif k == 'servo':
            lines += ['print("Clear the servo arm. Watch it move both ways, then return to centre.", flush=True)',
                      f'with Servo({pins[0]}, initial_value=None) as d:',
                      '    for position in (-0.5, 0, 0.5, 0):', '        d.value = position', '        sleep(0.7)',
                      '    d.detach()', '    ok = True']
        elif k == 'camera':
            lines += ['from pipath_camera import Camera', 'camera = Camera()', 'grid = camera.capture_grid(16,16)',
                      'ok = len(grid) == 16 and all(len(row) == 16 for row in grid)']
        lines += [f'print("PIPATH_CHECK:{ident}:" + ("PASS" if ok else "FAIL"), flush=True)',
                  'print("Test completed. Did you observe the expected response?" if ok else "No response. Check this connection and try again.", flush=True)']
    lines += ['print("PIPATH_CHECK:DONE", flush=True)']
    return '\n'.join(lines) + '\n'


@dataclass
class WiringSession:
    expected: set[str]
    passed: bool = False
    running: bool = False
    observed: set[str] = field(default_factory=set)

    def start(self):
        self.passed = False
        self.observed.clear()
        self.running = True

    def finish(self, stdout: str, stderr: str, rc: int | None, reason: str | None):
        self.running = False
        lines = set(stdout.splitlines())
        self.passed = (rc == 0 and reason not in ('user', 'abandoned', 'special', 'timeout', 'runaway')
                       and 'Traceback' not in stderr and 'PIPATH_CHECK:DONE' in lines
                       and all(f'PIPATH_CHECK:{i}:PASS' in lines for i in self.expected)
                       and not any(l.startswith('PIPATH_CHECK:') and l.endswith(':FAIL') for l in lines))
        self.observed.clear()

    def confirm(self, ident: str, on: bool):
        if self.passed and not self.running and ident in self.expected:
            if on:
                self.observed.add(ident)
            else:
                self.observed.discard(ident)

    @property
    def ready(self):
        return self.passed and not self.running and self.observed == self.expected
