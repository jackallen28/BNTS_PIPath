# Classroom trial on the actual Pi

Record Pi model/OS, webcam model, mounting height, lighting, bin rules and date.
Start with clean, non-hazardous props and the GPIO simulation mode.

- Install from a fresh unzip, launch from menu and desktop, and choose the right USB camera.
- At 1024×640, scroll the right panel and reach every control. Check keyboard Space
  captures a photo but still types spaces in item names and rules.
- Clear mat; check preview alignment and take background. Change lighting and camera
  position deliberately; confirm a new setup and examples are needed.
- Train at least 2 genuinely different objects per bin, at least 8 views per object;
  use more kinds for realistic sorting. Vary orientation/position without changing labels.
- Collect at least 2 different negative scene sets. Include hands from all edges,
  sleeves, a person leaning into the box and any classroom distractions. Ask consent.
- Test at least 10 previously untrained physical items per bin. Record correct bin,
  wrong bin and withheld answers separately; do not count withheld items as correct.
- Test at least 10 no-item/people scenes: empty mat, people outside the box, hand
  inside the box, held item, sleeve, face/torso if consented, fast and slow entry,
  a stationary person and different clothing. Record every unexpected bin choice.
- Try transparent/pale items, shadows, two items, partial items, unknown items and
  similar-looking items belonging to different bins. Check withholding messages.
- Disconnect/reconnect webcam while a bin label is displayed: the label must clear
  after a second without a fresh frame; UI stays usable and reconnection works.
- Save, quit, reopen. Verify saved counts and table check; retrain before testing.
  Undo/delete a set and ensure old model/test results are invalidated.
- Delete a test session and verify PiPath's student work is untouched.
- In **GPIO outputs**, check that BCM17 means physical pin 11 and BCM18 means pin
  12. Confirm duplicate output pins and invalid angles are rejected. Save and reopen
  the app; the mapping should remain, while real GPIO stays disabled.
- With power disconnected, wire the LED through its resistor and the servo with
  an appropriate external supply and common ground. Check the mechanism's clearance
  and start with small, suitable active/rest angles before fitting a gate.
- Enable real GPIO only in Live. Present Waste: LED on, servo rest. Present Recycling:
  LED off, servo active. Confirm other screens and the demo cannot activate hardware.
- Remove the item; try unknown/people/moving views and disconnect the camera. Check
  LED off and the rest-angle command while enabled. Test **Stop GPIO**, navigation,
  settings, reset and application close; these should disarm and release outputs.
  Verify movement on the actual mechanism: commanding rest does not confirm its position.
- Confirm a GPIO error leaves hardware disabled and clearly reports the problem.
  Test the decision-update watchdog with the mechanism unloaded; never assume a
  software watchdog can move an unpowered servo or handle an operating-system failure.
- Record responsiveness and memory on the target Pi. Do not infer Pi performance
  or real-world accuracy from the cloud's synthetic test results.

If people-only scenes produce bin choices, improve mounting/screens, add local
negative examples and retest. For unattended deployment, a separately validated
person/object detector or physical presence control is required.
