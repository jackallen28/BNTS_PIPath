# Test programs sandbox

**WastePath 0.4.0** is a standalone waste/recycling camera workshop for evaluation
before a later PiPath integration. The main PiPath application is unchanged and
nothing in this folder starts automatically.

This version restores the user's original ML Camera recognition method. Teach ten
Waste and ten Recycling photos; no people training is needed. After training,
Live opens the servo bin for recognised recycling and flashes an LED for waste or
unrecognised items. Custom GPIO pins and angles are supported.

- Read [WastePath/README.md](WastePath/README.md) for the workflow and wiring.
- Download [WastePath-GPIO-RaspberryPi-v0.3.0.zip](WastePath-GPIO-RaspberryPi-v0.3.0.zip)
  for the updated test program, or download this branch and open `sandbox/WastePath`.
- Run `bash install.sh` inside the WastePath folder on Raspberry Pi OS Desktop.
- For a camera-free walkthrough run `/usr/bin/python3 main.py --demo`.
- Enable real GPIO explicitly in Live after setup and training.

When upgrading from 0.1/0.2, take a new background photo and retrain once: earlier
cropped training is backed up before replacement. GPIO mappings are preserved.
Normal data is stored separately in `~/WastePath`; keep it when replacing the app.
Physical camera, GPIO, servo travel and accuracy still need checking on the target Pi.
