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
