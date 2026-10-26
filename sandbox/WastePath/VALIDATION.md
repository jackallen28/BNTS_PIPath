# Validation

Cloud Linux x86_64, Python 3.12, Tk 8.6 with a virtual Xorg display.

- 30 tests passed, no failures or skips, including the actual Tk workflow at
  1024×640: background → 48 measured examples → train and whole-item quiz →
  fresh tests → live labels → camera loss.
- Model tests covered known bins, ambiguity, unfamiliar items, negative examples,
  whole-item holdout and one-second stability resets.
- Vision tests covered empty scenes, people outside the inspection box, edge
  intrusion, motion and the synthetic end-to-end feature/classification pipeline.
- Storage tests covered atomic replacement, round trip, invalid versions and
  non-finite measurements. Camera tests covered fresh synthetic frames, shutdown
  and a missing webcam.
- GPIO tests exercised configurable mappings, LED/servo switching, custom angles,
  simulation without GPIO allocation, invalid/duplicate pins, atomic settings saves,
  real gpiozero PWM mock pins, pin reservation release, partial startup/write faults,
  and the independent watchdog thread. Tk integration tests confirmed Live-only
  hardware gating, demo arming rejection, settings validation/persistence, stopping
  on settings/navigation and camera loss, and restarting without restored arming.
- Separately launched the real synthetic Camera thread and Tk event loop, confirmed
  fresh frames, calibrated the empty mat and opened the teaching screen.
- Inspected the 1024×640 Live screenshot and the separate GPIO settings window
  under screenshots/. It depicts a
  synthetic shape, not a real webcam or evidence of real sorting accuracy.
- Python compilation and installer shell syntax checks passed.

Not verified here: Raspberry Pi hardware/performance, physical USB-camera operation,
installation on Raspberry Pi OS, physical GPIO/servo movement, actual waste/recycling accuracy, or real-world
person rejection. Use HARDWARE-CHECKLIST.md on the target machine before class use.
