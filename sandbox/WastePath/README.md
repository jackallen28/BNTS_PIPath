# WastePath — TEST sandbox, version 0.3.1

A standalone PiPath-style waste/recycling camera workshop, based on your working
**ML Camera** program. This version restores its recognition method and removes
the people-training category. It remains separate from the main PiPath app.

## Set up a new Raspberry Pi 5

Use Raspberry Pi OS Desktop (64-bit, Bookworm or Trixie), connected to the internet
for the first install. Plug in the USB webcam, open **Terminal** and run:

```sh
git clone --depth 1 -b test-wastepath-gpio https://github.com/jackallen28/BNTS_PIPath.git ~/BNTS_PIPath
cd ~/BNTS_PIPath/sandbox/WastePath
bash install.sh
```

The installer asks for your password once (for `sudo apt-get`), adds the camera, Tk
and GPIO packages, and creates a **WastePath** menu entry (Education) and a desktop
icon. It finishes with a readiness check, something like this:

```text
WastePath check on Raspberry Pi 5 Model B Rev 1.0 (Debian GNU/Linux 13 (trixie))
  ✓ Libraries: Python 3.13.5, Tk 8.6, OpenCV 4.10.0, NumPy 2.2.4, Pillow 11.1.0, gpiozero
  ✓ GPIO: lgpio can use GPIO chip 4
  ✓ Camera: /dev/video0 gives 640×480 pictures
Ready to go.
```

Run the check again at any time with `/usr/bin/python3 main.py --check`. It never
moves an output. Then open WastePath from the menu, or run `/usr/bin/python3 main.py`.

**Update later:** `cd ~/BNTS_PIPath && git pull`, then run `bash install.sh` again.
Saved training and GPIO settings in `~/WastePath` are kept.

## Install from a copy

On another Raspberry Pi OS Desktop, unzip the program somewhere permanent, open a
terminal inside the WastePath folder, and run:

```sh
bash install.sh
/usr/bin/python3 main.py
```

Use a USB webcam. WastePath finds it by itself (`auto` in Setup), even on a Pi 5
whose own video devices also appear as `/dev/video*`, and reconnects if it is
unplugged. To choose one yourself, type its number in Setup or start with
`--camera 1`. For a no-camera walkthrough use `--demo`; the demo never enables
physical GPIO.

**Updating from 0.1/0.2:** replace the application files and run the installer again.
Then take a new empty-table photo and retrain once. Older training used a central
crop and is incompatible with the restored full-frame measurements. The app keeps
a `training-backup-*.npz` copy before replacing old-format training. Your GPIO pins
and angles are kept in the separate `outputs.json` file.

## Teach it, then sort

1. **Set up:** aim at a plain table with steady lighting. Clear the table, including
   your hands, then press **Photograph empty table**. It averages ten camera frames,
   just like the original. Keep the camera in that position.
2. **Teach Waste:** take **10 photos**. Move or turn the item between photos and
   take your hand away. Names are optional. You can include different waste items
   if they belong in your local waste bin.
3. **Teach Recycling:** the category advances automatically after the first ten
   photos. Take **10 recycling photos** in the same way. There is no humans, hands
   or background training class. More varied item photos can be added later.
4. **Train:** press **Train and quiz**. It uses the original colour/shape scaling,
   five-nearest-neighbour votes, photo quiz and unknown-object distance limit.
   Training takes you straight to **Live**, ready to sort.
5. **Live:** simulation shows what the outputs would do. On the Pi, configure the
   pins in **GPIO outputs**, then press **Enable real GPIO** once for this session.

The default behaviour is:

| Camera result | Servo / bin | LED |
| --- | --- | --- |
| Recognised Recycling | Open, at configured active angle | Off |
| Recognised Waste | Rest / closed angle | Flashes |
| Unrecognised or uncertain item | Rest / closed angle | Flashes |
| Empty table | Rest / closed angle | Off |
| Camera disconnected or stale | Rest-angle command | Off |

A new accepted label must remain consistent for half a second before operating
its output. Recognition is smoothed across frames as in ML Camera; the removed
motion, edge, large-area and central-crop gates no longer keep blocking items.
The LED flashes twice per second and does not restart its flash timer each frame.

“Wrong” means waste presented to the default recycling bin, or something the model
does not recognise. The program cannot know by itself that a confident prediction
is factually wrong. Use the optional **Test** screen and record the actual category
to measure those mistakes. Test results never become training photos or move hardware.

If the outline misses pale objects, reduce the **Background threshold** in Setup.
If it picks up shadows, increase it. The default is 22, as in your original app.
Use **Computer view** to see the changed pixels. The whole 4:3 camera image is used;
widescreen input is cropped to 4:3 before resizing, so shapes are not stretched.

## GPIO settings and wiring

Choose Off, LED or Servo separately for Waste and Recycling. Each enabled output
needs a different **BCM GPIO number**, not a physical header pin number. Servo
active/rest angles can be set from 0° to 180°. To make a waste bin instead, assign
the servo to Waste and LED to Recycling. Unrecognised items activate whichever LED
outputs are configured; they never activate a servo. Keep an LED configured if you
want the wrong-item indicator.

Default wiring, with power disconnected:

- LED: BCM17 (**physical pin 11**) → LED anode; cathode → **220–330 Ω resistor** →
  Pi GND (for example physical pin 6).
- Servo signal: BCM18 (**physical pin 12**). Power it from a suitable external
  regulated supply, normally 5 V, according to its specification. Join the servo
  ground, supply ground and Pi ground. Do not power a motor from a GPIO signal pin.
- Set active/rest angles to match your mechanism before attaching a lid or gate.
  The driver uses 1–2 ms pulses. Actual travel depends on the servo.

The app starts with GPIO disabled. **Stop GPIO**, changing screens/settings,
changing training, reset and exit release hardware. An independent watchdog stops
outputs if decision updates stop for 1.5 seconds; GPIO errors also stop outputs
until you explicitly enable them again. A rest command is not position feedback
and cannot guarantee that an unpowered or faulty servo closed the bin.

Use a supervised lightweight classroom mechanism and keep fingers clear. This is
not a person detector or a safety interlock. See [HARDWARE-CHECKLIST.md](HARDWARE-CHECKLIST.md).

## Saved data and later PiPath integration

Normal data is in `~/WastePath`; demo data is in `~/WastePath/demo`. Use
`--data-dir /some/folder` or `WASTEPATH_HOME` to choose a different location.

- `training.npz`: version 2 full-frame measurements and the empty-table background;
  saved atomically after capture/undo/deleting examples. Camera photos are not saved.
- `outputs.json`: GPIO mapping and angles; the enabled state is never saved.
- `project.json`: local bin-rules note and segmentation threshold.
- `fresh-tests.json`: the latest optional fresh test results.

Reopening saved version 2 training needs the empty-table check and retraining.
A new background capture clears current examples after confirmation. **New session**
clears training/test data, preserving hardware mappings and any migration backups.

`vision.py` and `model.py` contain the original-style recognition, `camera.py` reads
the newest frame off the Tk thread, `outputs.py` handles GPIO, and `app.py` provides
the PiPath-style interface. See [INTEGRATION.md](INTEGRATION.md) for the later merge.

## Development checks

On desktop Linux with Python 3.11+ and Tk:

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python main.py --demo
# Use a desktop display, or prefix this command with xvfb-run -a:
.venv/bin/python -m unittest discover -s tests -v
```

Tests include reference results generated from the uploaded original camera
program, GUI training-to-sorting, and simulated GPIO blinking/servo behaviour.
They do not establish real rubbish accuracy, USB compatibility or Pi performance.
