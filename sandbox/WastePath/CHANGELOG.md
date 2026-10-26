# 0.2.0 — configurable GPIO outputs

- Add GPIO output settings for Waste and Recycling: Off, LED or positional servo.
- Configure distinct BCM pins and servo active/rest angles; mappings save locally.
- Start with simulation; explicitly enable real GPIO only in Live.
- Withdraw outputs for withheld detections and camera loss; disarm on navigation,
  configuration changes, reset, shutdown or a GPIO fault.
- Add an independent 1.5-second decision-update watchdog and Stop GPIO control.
- Include GPIO wiring guidance, Raspberry Pi dependencies and 30 passing cloud
  tests with synthetic cameras and mock GPIO. Physical hardware remains unverified.
