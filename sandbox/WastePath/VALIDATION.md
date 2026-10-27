# Version 0.4.1 validation

**55 tests passed.** New: the automatic set-up homes on the pretend lid's button
(120°), opens 60° from closed, adjusts 5° at a time, saves, and closes onto the
button; "Close 5° more" is kept and used in Live (onto the button, then on to the
saved angle); a button still pressed after lifting, and the wrong direction, both
stop with a message. Checked on screen at 1024×640 in the demo.

# Version 0.4.0 validation

**53 tests passed** (12 new). New tests drive the servo with fake, gpiozero mock and
pretend-lid hardware: opening at once, closing 1° at a time, stopping when the
button presses, going limp, the fallback when the button never presses, a stuck
button, a shut lid that doesn't move on start-up, closing before pins are freed,
re-arming only after the lid has closed, a servo error stopping all outputs, the
5° calibration steps and saving them, a button pin clashing with the servo, and
taking extra photos past 10 from Teach and from the quiz.

Screens checked at 1024×640 with the demo: Teach (photo boxes, "+3 extra") and
Set up bin (dial, buttons). Not verified here: a real servo, button and lid.

# Version 0.3.1 validation (new Raspberry Pi 5)

**41 tests passed, none failed or skipped**, with the library versions Raspberry Pi
OS installs, not only the newer development pins in `requirements.txt`:

- Trixie set: Python 3.13 (Tk 9.0 in this test machine; Pi OS uses Tk 8.6), OpenCV 4.10, NumPy 2.2.4, Pillow 11.1, gpiozero 2.0.1.
- Tk 8.6 set (as on Pi OS): Python 3.12, Tk 8.6, OpenCV 4.10, NumPy 2.2.4, Pillow 11.1.
- Development pins: OpenCV 4.12, NumPy 2.2.6, Pillow 11.3.
- Bookworm set (no Tk available here, so engine, camera and GPIO tests only):
  Python 3.11, OpenCV 4.6, NumPy 1.24.2, Pillow 9.4.

Before this release, two reference tests failed on the Pi OS versions: NumPy 1.24
ordered equal-distance neighbours differently (now a stable sort), and OpenCV 4.6 /
4.10 rounded a few edge pixels differently (at most 0.0003 in a measurement; training
and sorting both happen on the Pi, so they always agree with each other).

New tests: finding the USB webcam among a Pi 5's own video devices (ribbon camera
interface, HEVC decoder, ISP), waiting for a webcam to be plugged in, and the
`--check` report. The app was also started on a virtual 1366×768 display with no
webcam: it shows "No USB webcam found. Plug one in; it will connect by itself."

Still not verified here: a real Pi 5, its webcam and frame rate, lgpio on real pins
and actual servo movement. Run `main.py --check`, then HARDWARE-CHECKLIST.md.

# Version 0.3.0 validation

Validated on cloud Linux x86_64 with Python 3.12, OpenCV 4.12, Tk 8.6 and a
virtual Xorg display. **36 tests passed, none failed or skipped.**

- Ran the uploaded original `ml_camera.py` with its object list changed to Waste /
  Recycling to generate independent reference results. The new model matches its
  feature scaling, neighbour votes, nearest indices/distances, novelty limit and
  photo quiz. Background masks and colour/shape measurements match reference cases.
- Tested full-frame objects outside the previous central crop, largest-contour
  selection, and widescreen cropping without shape distortion.
- Drove the real Tk workflow at 1024×640: average ten background frames, take ten
  Waste photos and ten Recycling photos with blank names, train and move directly
  to Live. No human examples or required item groups are used.
- Tested fresh-item records, optional test isolation, old-format training backup,
  new full-frame persistence and calibration interruption when the camera disconnects.
- Tested recognised recycling → servo active / LED off; waste or an unknown item →
  servo rest / flashing LED; empty table or camera loss → rest / LED off.
- Confirmed the gpiozero mock LED actually toggles on/off and stops; repeated
  predictions do not restart the flash sequence. Tested custom pins/angles,
  settings persistence, fault cleanup, pin release and the independent watchdog.
- Tested that real GPIO can only enable in Live with a fresh trained camera, never
  in the synthetic demo, and stops on settings/navigation/reset/shutdown.
- Python compilation, installer shell syntax and the source diff checks passed.
- Inspected the refreshed Live and GPIO settings screenshots. Synthetic shapes
  demonstrate the workflow; they do not measure real-world sorting accuracy.

Not verified in this cloud machine: physical USB webcam operation, Raspberry Pi
frame rate, installation on Pi OS, actual servo movement or rubbish accuracy.
Run HARDWARE-CHECKLIST.md on the actual setup. A classifier cannot determine by
itself whether a confident prediction is factually wrong; use fresh labelled tests.
