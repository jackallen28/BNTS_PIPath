# Test programs sandbox

This branch contains **WastePath**, a standalone waste-versus-recycling machine
learning camera workshop with configurable LED and servo GPIO outputs.

It is a test program for evaluation before a later PiPath integration. Existing
PiPath application files are unchanged. No sandbox program is launched automatically.

- Open [WastePath/README.md](WastePath/README.md) for installation and the student workflow.
- Download [WastePath-GPIO-RaspberryPi.zip](WastePath-GPIO-RaspberryPi.zip) for just the test program.
- Or download this branch as a ZIP and open the `sandbox/WastePath` folder.
- On Raspberry Pi OS Desktop, run `bash install.sh` inside the WastePath folder.
- Camera-free demo: `/usr/bin/python3 main.py --demo` after installation.
- Real GPIO starts disabled; enable it explicitly in Live after configuring outputs.

Training data is stored separately in `~/WastePath` by default. Do not replace that
student-data folder when updating application files. Physical camera, GPIO, servo
travel and real-world sorting accuracy still require validation on the target Pi.
