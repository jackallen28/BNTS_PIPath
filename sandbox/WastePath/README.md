# WastePath — TEST sandbox, version 0.4.0

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
2. **Teach:** two boxes show each bin's photos: a progress bar to 10 and the last
   five photos taken. Click a box to choose the bin. Take **at least 10 Waste
   photos**, then **10 Recycling photos** (it moves on to Recycling by itself after
   the first ten). Move or turn the item between photos and take your hand away.
   Names are optional.
3. **More photos, any time:** keep pressing **Take photo** past 10 (the bar shows
   "+3 extra"), or use **+ Add more … photos** under the quiz results on the Train
   screen. New photos need **Train again** before Live uses them. The small photos
   on screen are only kept while WastePath is open; only the measurements are saved.
4. **Train:** press **Train and quiz**. It uses the original colour/shape scaling,
   five-nearest-neighbour votes, photo quiz and unknown-object distance limit. Each
   bin's quiz result has a bar; under 90% suggests adding more photos of that bin.
5. **Set up bin** (the hardware calibration, see below), the first time only.
6. **Live:** simulation shows what the outputs would do. Press **Enable real GPIO**
   once for this session.

The default behaviour is:

| Camera result | Servo / bin | LED |
| --- | --- | --- |
| Recognised Recycling | Opens at once to the open angle | Off |
| Recognised Waste | Closes slowly until the button presses | Flashes |
| Unrecognised or uncertain item | Closes slowly until the button presses | Flashes |
| Empty table | Closes slowly until the button presses | Off |
| Camera disconnected or stale | Closes, then GPIO stops | Off |

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

## The servo and the closed button

The servo works like the BNTS smart bin's Arduino program:

- **Open:** the servo goes straight to the open angle and holds it. The lid stays
  open for at least 2 seconds, so it doesn't flap.
- **Close:** it sweeps **1° every 15 ms** towards closed, checking the closed button
  after each step. When the shut lid presses the button it holds for 0.3 s, then
  **goes limp** (no pulses), so it doesn't buzz or push against the lid.
- **No press:** it stops 15° past the saved closed angle, rests at the saved angle
  and shows ⚠ in Live (like the Arduino's fallback angle). Check the button.
- **Stuck:** if the button is still pressed 0.4 s after opening, Live shows ⚠.
- **Start-up:** when you enable real GPIO, a shut lid stays still. Otherwise it
  homes from the open angle, as the Arduino does at power-up.
- **Stop GPIO**, changing screens, the watchdog and quitting all close the lid
  first, then free the pins.

Without a button, the servo still sweeps slowly to the closed angle and goes limp.

### Wiring (power off first)

- **LED:** BCM17 (**physical pin 11**) → LED long leg; short leg → **220–330 Ω
  resistor** → GND (physical pin 6).
- **Servo signal:** BCM18 (**physical pin 12**). Power the servo from its own 5 V
  supply and join its GND to the Pi's GND. Never power it from a GPIO pin.
- **Closed button:** one leg → BCM23 (**physical pin 16**), the other leg → GND
  (physical pin 14). No resistor: the Pi's own pull-up is used. **Never connect the
  button to 5 V** (the Arduino bin's 5 V + 10k wiring would damage a Pi pin). Fix it
  where the shut lid presses it.

### 4. Set up bin (hardware calibration)

1. Choose which bin the lid opens for, the servo and button GPIO numbers, and which
   way the servo turns to close (the Arduino bin closes towards 180°).
2. **Find the closed position:** the lid sweeps closed until it presses the button.
   The dial shows the servo angle and the button.
3. **Open 5° more:** press until the lid opens far enough (**5° less** goes back).
4. **Test:** opens, waits 2 s, then closes until the button presses.
5. **Save the bin settings.** The angles and button are kept in `outputs.json`.

In `--demo` the bin step uses a pretend lid whose button presses at 120°.
**GPIO outputs** still lets you type angles and pins yourself, including the button
("none" for no button).

Choose Off, LED or Servo separately for Waste and Recycling. Each enabled output
and button needs a different **BCM GPIO number**, not a physical pin number. To
make a waste bin instead, give the servo to Waste and the LED to Recycling.
Unrecognised items flash the LEDs; they never open a servo.

The app starts with GPIO disabled. An independent watchdog stops outputs if
decision updates stop for 1.5 seconds; GPIO errors also stop outputs until you
enable them again. Use a supervised lightweight classroom mechanism and keep
fingers clear. This is not a person detector or a safety interlock. See
[HARDWARE-CHECKLIST.md](HARDWARE-CHECKLIST.md).

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
