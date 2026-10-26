# WastePath — TEST sandbox

> Experimental, standalone test program. It is not integrated into PiPath.
> Cloud tests use mock GPIO and synthetic cameras; try it on an actual Pi before classroom use.

A standalone waste-versus-recycling camera workshop for Raspberry Pi, styled to
fit PiPath: teal desktop, silver bevelled controls, purple-to-teal title bar,
short student instructions and a guided **Set up → Teach → Train → Test → Live** journey.
It does not change or depend on the PiPath checkout. Its modules can be integrated later.

Students teach a small, local machine learning model using **their actual rubbish
items and their school's bin rules**. It learns appearance, not material composition.
It cannot identify every recyclable object or decide council rules by itself.
You can also map each bin category to an LED or a small servo using the GPIO controls.

## Raspberry Pi installation

Use Raspberry Pi OS **Desktop, Bookworm or newer**, a USB webcam and a fixed,
downward-facing camera mount. Designed to keep the same lightweight approach as
the supplied ML Camera program; physical Pi performance still needs checking.

1. Unzip this folder somewhere permanent, such as `~/WastePath-app`.
2. Open a terminal there and run `bash install.sh`. It installs signed distro
   packages if missing, then adds a menu entry and desktop launcher. It does not
   start the app or alter PiPath. The folder must stay at that location.
3. Plug in the webcam and open **WastePath** from the menu. If the desktop asks,
   mark the launcher executable/trusted. Alternatively:

```sh
/usr/bin/python3 main.py
# Another USB device:
/usr/bin/python3 main.py --camera 1
```

Camera reads run in a background thread and reconnect after a read failure.
Choose a camera number in Setup and press Reconnect if needed. CSI/ribbon cameras
are not supported by this version's camera adapter; use a USB webcam.

For a no-webcam walkthrough:

```sh
/usr/bin/python3 main.py --demo
```

The demo uses deliberately simple coloured shapes. It is labelled on screen,
stores its own examples separately and is **not evidence of rubbish accuracy**.
GPIO actions can be previewed in simulation; the demo cannot enable real GPIO.

For an existing installation, replace the application files with this version and
rerun `bash install.sh` to add the GPIO dependencies. Your default `~/WastePath`
training folder is separate from the application folder; keep it when updating.

## The student workshop

1. **Set up the station.** Aim down at a plain mat. The marked central box is the
   inspection area; everything outside it is excluded from measurements. Agree on
   local bin rules with the teacher and enter a short reminder. Use clean props,
   not sharp, dirty or hazardous waste. Clear the mat and photograph it.
2. **Collect Waste examples.** Select Waste. Name a real item, such as `wrapper A`.
   Take at least **8 photos**, moving and turning it between photos. Keep hands out.
   Repeat with a genuinely different item, such as `tissue B` if local rules agree.
3. **Collect Recycling examples.** Repeat with at least **2 different items**,
   8 photos each. Include similar colours across both bins so the computer cannot
   simply learn “blue means recycling”. Add more item types when results are weak.
4. **Teach what to ignore.** Select **People / hands / other**. Make at least
   **2 scene sets**, 8 photos each: for example a hand entering from the left and
   a sleeve/torso entering from the right. Include varied hands, clothing and
   positions, with permission. Names describe scenes, never people. A completely
   empty mat needs no negative photo: it is handled by the background check.
5. **Train and quiz.** Training requires all six sets (at least 48 examples).
   The quiz withholds a whole named item/scene each time. It reports correct bin
   choices, withheld answers and wrong bin choices separately. Poor results are
   useful clues: return to Teach, undo/delete a bad set or add better examples.
6. **Test fresh examples.** Use different physical items, not the training items.
   Wait for a steady answer and record what the item actually is with the three
   category buttons. Repeat with people, hands, unknown objects and an empty mat.
   Test records are independent: they never train the model. A withheld item is
   counted as withheld, not as a correct bin classification. For people/no-item
   trials, withholding is the desired behaviour.
7. **Try Live.** Show one whole item in the box, move hands away and wait about a
   second. A steady accepted answer is shown as WASTE or RECYCLING. Otherwise the
   app explains why it is withholding a choice. Check any real disposal decision
   against the local rules. Live uses the same pipeline as Test.

There is no automatic progression or claim of “ready” based on a perfect quiz.
Test until behaviour is acceptable for the activity. In particular, record **zero
bin choices on people-only trials** before demonstrating it; if this fails, improve
the station and data. Passing these trials still does not guarantee detection.

## People in the camera path

A generic downloaded bank of people is not enough: it may have different framing,
lighting and clothing from the classroom. This app instead combines:

- A fixed inspection box. People outside it do not become classifier inputs.
- Local negative scene examples: hands, sleeves, people and other distractions.
- Scene checks that withhold a bin if objects touch the box edge, cover too much
  of it, or appear as multiple separate objects.
- Motion checks and a one-second steady-label requirement.
- Similarity and novelty rejection: weak or unfamiliar matches get no bin choice.
- Immediate withdrawal of a result if the webcam stops delivering fresh frames.

**This is not a person detector.** A stationary hand or person wholly inside the
box can still resemble a trained item; an item held by a person can also fool it.
The strongest practical protection is a downward-facing, enclosed or screened
inspection station where faces and bodies cannot enter the item area. The GPIO
feature is for a supervised classroom LED or lightweight servo prototype. This
classifier is not a safety interlock for people or industrial machinery.

There is no face identification, online image bank, upload or cloud API. Captured
training pictures are processed in memory and discarded; only colour/shape
measurements, labels and scene/item names are saved. The **empty mat background**
is retained for segmentation, so make sure it is empty when calibrating.
Measurements and names should still be treated as classroom data.

## Custom GPIO outputs

Open **GPIO outputs** to choose **Off**, **LED** or **Servo** independently for
Waste and Recycling. Choose a distinct **BCM GPIO number** for each enabled output;
these are not the physical header pin numbers. Supported BCM numbers are 2–27.
For a servo, set the detected-item angle and rest angle between 0° and 180°.

The starting example matches a simple sorting demonstration:

| Detected category | Output | BCM GPIO | Physical header pin | Action |
| --- | --- | --- | --- | --- |
| Waste | LED | 17 | 11 | LED on while Waste is accepted |
| Recycling | Servo | 18 | 12 | 90° while Recycling is accepted; 0° at rest |

The other output returns to neutral when a category is accepted: Waste turns the
LED on and requests the servo's rest angle; Recycling turns the LED off and requests
the servo's active angle. Choose angles that match your particular gate mechanism.
The servo driver uses a conservative 1–2 ms pulse range; actual travel varies by servo.

1. Start in simulation, set the mapping and save it. Use Live to check the intended
   actions displayed on screen without connecting anything.
2. Disconnect power before wiring. For the default LED, connect BCM17 (physical
   pin 11) to its anode, and its cathode through a **220–330 Ω resistor** to GND
   (physical pin 6). For the servo, connect its signal to BCM18 (physical pin 12).
   Power the servo from a suitable regulated **5 V external supply**, not a GPIO
   output. Join the supply ground, servo ground and Pi ground. Check your servo's
   voltage/current requirements and keep fingers clear of its travel.
3. Complete setup, training and fresh tests, then open **Live** with a fresh camera
   view. Press **Enable real GPIO** to connect the outputs for this session. On
   Raspberry Pi OS, the installer includes `python3-gpiozero` and `python3-lgpio`.
4. Present an item and move your hands away. Only an accepted, steady **Live**
   result drives real outputs. Setup, Teach, Train and Test do not drive them.
   **Stop GPIO** releases the hardware whenever you need to stop.

No item, motion, an unknown view, a person/hand rejection or a missing camera
withdraws the bin choice: the LED turns off and the servo is commanded to its rest
angle while GPIO is enabled. Moving to another screen, opening settings, resetting
or changing the training/configuration, and closing the app disarm and release the
outputs. An independent watchdog also disarms if fresh decision updates stop for
more than 1.5 seconds. A GPIO fault disarms and reports the error; it does not
silently re-enable hardware.

The app always starts in simulation. Saved mappings never save the enabled state.
A rest-angle command is not position feedback: once a servo is released, during
power loss or after a fault, the app cannot confirm that it reached or holds rest.
Real GPIO operation and servo movement still require a trial on the actual Pi.

## Saved sessions

Normal data goes in `~/WastePath`; demo data in `~/WastePath/demo`.
Use `--data-dir /some/folder` or `WASTEPATH_HOME` to change it.

- `training.npz`: versioned feature measurements and the empty-mat background.
  Saved after each capture, undo and set deletion with an atomic file replacement.
- `project.json`: the local bin-rules reminder.
- `fresh-tests.json`: the most recently recorded fresh-test results.
- `outputs.json`: the GPIO mapping and servo angles; enabling real hardware is never saved.

Saved training needs an **empty-table check and retraining** after reopening.
If the camera, light or mat changed, photograph a new empty mat and collect new
examples. Recapturing the background clears previous training after confirmation.
**New session** asks before deleting this app's saved data. It never touches PiPath.

## How the model works

Adapted from your supplied ML Camera: background subtraction in Lab colour space,
then 29 colour/shape features and distance-weighted 5-nearest-neighbour voting.
Features are scaled from the training set. Each class has a novelty limit derived
from its nearest same-class examples; bin choices also need at least 80% of the
neighbour vote and a clear margin. Those votes are **not calibrated probabilities**.
The whole-item quiz refits its model without the held-out item, including scaling
and novelty limits. Training is capped at 480 examples to bound memory on small Pis.

It is intentionally an inspectable teaching model, not a pretrained semantic
waste recogniser. Transparent bottles, shadows, dirty packaging, very similar
objects and unfamiliar materials can defeat it. A future PiPath integration could
add a small transfer-learning image encoder behind the same model interface, with
separate Raspberry Pi performance and accuracy validation.

## Development and testing

On desktop Linux (Python 3.11+ with Tk installed):

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python main.py --demo
.venv/bin/python -m unittest discover -s tests -v
```

GUI tests require a display. With Xvfb available:

```sh
xvfb-run -a .venv/bin/python -m unittest discover -s tests -v
```

Tests exercise known/unknown/ambiguous classifications, negative examples, grouped
validation, stability reset, camera loss, safe local persistence and the full real
Tk teach/train/test/live workflow using a synthetic camera. They do not validate
USB hardware, Raspberry Pi frame rate, physical GPIO/servo behaviour or real-world
people rejection. GPIO tests use simulated devices rather than real header pins.

See [HARDWARE-CHECKLIST.md](HARDWARE-CHECKLIST.md) before a classroom trial and
[INTEGRATION.md](INTEGRATION.md) for the later PiPath merge.
