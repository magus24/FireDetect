# FireDetect — Autonomous Firefighting Drone (Edge AI MVP)

**Real-time fire & smoke detection on an edge GPU, closing the loop from pixels to payload release.**

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![PyTorch](https://img.shields.io/badge/PyTorch-CUDA%2012.1-EE4C2C?logo=pytorch&logoColor=white)](https://pytorch.org/)
[![YOLOv8](https://img.shields.io/badge/Ultralytics-YOLOv8-0B23A9)](https://github.com/ultralytics/ultralytics)
[![OpenCV](https://img.shields.io/badge/OpenCV-4.x-5C3EE8?logo=opencv&logoColor=white)](https://opencv.org/)
[![ESP32](https://img.shields.io/badge/ESP32-Arduino-000000?logo=espressif&logoColor=white)](https://www.espressif.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

🇬🇧 English · [🇷🇺 Русская версия](README.ru.md)

> **Status:** working MVP / proof of concept. This is a research and engineering demonstrator, **not** a certified firefighting system.

---

## Overview

FireDetect is an end-to-end prototype of the perception and payload subsystem for an autonomous firefighting drone. A camera stream is processed by a custom-trained **YOLOv8** model on an edge GPU; when fire or smoke is confirmed above a confidence threshold, the application runs a small state machine and sends a single-byte command over UART to an **ESP32**, which actuates a servo-driven capsule release mechanism.

The whole pipeline is designed to be **demoable without hardware**: if no ESP32 or serial port is present, the app keeps running and logs actuation in simulation mode. A built-in **desk test mode** lets you validate the full targeting → release loop safely indoors using ordinary objects (phone, cup, bottle) instead of a real flame.

```
 ┌──────────────────────┐     ┌──────────────────────┐     ┌──────────────────────┐
 │  Camera (OpenCV)     │ ──► │  YOLOv8n fire/smoke  │ ──► │  Confidence +        │
 │  MSMF / DirectShow   │     │  FP16 · CUDA         │     │  cooldown state      │
 └──────────────────────┘     └──────────────────────┘     └──────────┬───────────┘
                                                                      │ 'D' over UART
                                                                      ▼
 ┌──────────────────────┐     ┌──────────────────────┐     ┌──────────────────────┐
 │  Capsule released    │ ◄── │  Servo 0° → 90° (3s) │ ◄── │  ESP32 (non-blocking│
 │  from payload bay    │     │  GPIO 13 · PWM 50 Hz │     │  state machine)      │
 └──────────────────────┘     └──────────────────────┘     └──────────────────────┘
```

---

## Highlights

- **Custom 2-class detector** — `smoke` / `fire` YOLOv8n weights are included in [`models/fire_yolov8n.pt`](models/fire_yolov8n.pt), so the repository works out of the box.
- **Edge-optimised inference** — automatic CUDA detection, FP16 half-precision on GPU, model warm-up, and CPU fallback (`--cpu`).
- **Closed-loop actuation** — detection → confidence gate → cooldown gate → UART `'D'` → physical servo release.
- **Fail-safe simulation** — missing camera, serial port, or model never crashes the app; it degrades to a clearly labelled simulation/standby mode.
- **Tactical HUD** — target lock box with animated corners, live FPS/latency telemetry, servo angle gauge, mode badge, and system state.
- **Demo / desk test mode** — switches the trigger classes to COCO objects (phone, cup, bottle) for safe indoor testing; toggled live with `M`.
- **Robust Windows camera handling** — tries DirectShow, then default, then MSMF; hot-swaps camera indices at runtime with `C`.
- **Firmware-level safety** — the ESP32 runs a non-blocking state machine, ignores re-entrant drop commands, and supports an emergency `R` reset.

---

## Quick Start (Windows)

### 1. Install dependencies

Double-click **`install_dependencies.bat`**, or run:

```bat
install_dependencies.bat
```

It checks Python, creates an isolated `venv`, installs CUDA 12.1 PyTorch (with a CPU fallback), then installs `requirements.txt`.

### 2. Run

Double-click **`start_app.bat`**, or:

```bat
start_app.bat
```

Without arguments the launcher starts in **demo mode**, so the app is immediately testable at a desk. Any CLI arguments are forwarded to `src/main.py`.

### Manual launch (any OS)

```bash
python -m venv venv
# Windows: venv\Scripts\activate
source venv/bin/activate
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121  # optional GPU build
pip install -r requirements.txt
python src/main.py --demo
```

> On Linux/macOS the `.bat` helpers do not apply; use the manual commands. Audio cues are Windows-only (`winsound`) and are skipped elsewhere.

### CLI options

| Flag | Default | Description |
| --- | --- | --- |
| `--model` | `models/fire_yolov8n.pt` | Path to YOLOv8 weights |
| `--port` | `COM3` | ESP32 serial port (auto-falls back to simulation) |
| `--baud` | `115200` | Serial baud rate |
| `--camera` | `0` | Initial camera index |
| `--conf` | `0.75` | Confidence threshold for a confirmed target |
| `--cooldown` | `5.0` | Seconds between capsule drops |
| `--demo` | off | Start in desk test mode |
| `--cpu` | off | Force CPU inference |

### Keyboard controls

| Key | Action |
| --- | --- |
| `SPACE` | Manual drop test (servo 90°, hold 3 s, reset to 0°) |
| `C` | Cycle camera index `0 → 1 → 2 → 0` |
| `M` / `T` | Toggle demo mode (COCO objects ↔ fire only) |
| `S` | Mute / unmute audio cues |
| `H` | Toggle the on-screen control legend |
| `Q` / `ESC` | Exit |

---

## Hardware Setup

| Component | Suggested part | Notes |
| --- | --- | --- |
| Edge compute | Laptop with NVIDIA GPU (developed on RTX 3070 Ti) | CPU works, but expect lower FPS |
| Camera | Built-in webcam or USB camera | Index configurable at runtime |
| MCU | ESP32 Dev Module / ESP32-WROOM-32 | Any board with UART over USB |
| Actuator | SG90 / MG995 / MG996R servo | Drives the capsule hatch |
| Power | External 5 V BEC for the servo | **Do not** power the servo from the ESP32 3.3 V rail |
| Payload | Capsule + release hatch | Mechanical design is out of scope for this repo |

**Wiring:** servo signal → **GPIO 13**, servo V+ → external 5 V, servo GND and ESP32 GND → **common ground**. Status LED → GPIO 2.

### Flashing the firmware

1. Open [`firmware/drop_capsule/drop_capsule.ino`](firmware/drop_capsule/drop_capsule.ino) in the Arduino IDE.
2. Install the **ESP32Servo** library (Library Manager → “ESP32Servo” by Kevin Harrington) and the ESP32 board package.
3. Select your board and port, then upload.
4. Close the Arduino Serial Monitor before starting the Python app — the port is exclusive.

### Serial protocol

| Byte | Action |
| --- | --- |
| `D` / `d` | Drop: servo to 90°, hold 3 s, return to 0° |
| `R` / `r` | Emergency reset: immediately close and lock |
| `S` / `s` | Report current state |
| `T` / `t` | Diagnostic drop sweep |

The firmware acknowledges commands and rejects a new drop while a release cycle is still active. Timing runs on `millis()` rather than `delay()`, so the MCU stays responsive.

---

## How It Works

1. **Capture** — `LaptopCameraManager` probes backends and indices, verifies a real frame, then requests 1280×720 with a single-frame buffer.
2. **Detect** — every frame is passed to YOLOv8 at `conf=0.35` for tracking; the highest-confidence target is kept.
3. **Confirm** — a target is *locked* only at `--conf` (default 0.75). Below that, the HUD shows it as tracked, not engaged.
4. **Gate** — the drop is allowed only if the cooldown has expired, preventing cascading releases.
5. **Actuate** — `'D'` is written to the serial port. Without hardware, the same event is logged and rendered as a simulated 90° servo state.
6. **Report** — FPS, inference latency, compute device, camera index, hardware link state, and the mission state are drawn onto the HUD.

### Design decisions

- **MCU owns the timing, not the PC.** The 3-second hold is enforced on the ESP32, so a USB hiccup or app crash cannot leave the hatch open indefinitely. The Python side is fire-and-forget.
- **Simulation is a first-class mode, not an error.** It makes the project reviewable and testable on any machine without the drone hardware.
- **Separate tracking and confirmation thresholds.** Detection at 0.35 keeps the target box stable; actuation at 0.75 avoids dropping on a single noisy frame.
- **Demo mode is explicit in the HUD.** The mode badge and state text make it obvious when the system is triggering on a cup rather than fire.

---

## Repository Structure

```
FireDetect/
├── src/
│   └── main.py                 # Edge AI app: camera, inference, HUD, state machine, serial
├── firmware/
│   ├── drop_capsule.ino        # IDE-friendly mirror of the sketch
│   └── drop_capsule/
│       └── drop_capsule.ino    # ESP32 payload actuator firmware
├── models/
│   ├── fire_yolov8n.pt         # Custom YOLOv8n weights (classes: smoke, fire)
│   └── README.md               # Model notes
├── install_dependencies.bat    # Creates venv + installs CUDA PyTorch and requirements
├── start_app.bat               # Activates venv and launches the app (demo mode by default)
├── run_app.bat                 # Minimal launcher
├── requirements.txt
├── README.md
└── README.ru.md
```

---

## Model Notes

- Architecture: **YOLOv8n**, 2 classes — `0: smoke`, `1: fire`.
- Weights: [`models/fire_yolov8n.pt`](models/fire_yolov8n.pt) (≈6 MB), included for reproducibility.
- Inference: 640 px input, FP16 on CUDA, lower threshold for tracking and a higher one for engagement.
- If `models/fire_yolov8n.pt` is missing, the app downloads the stock COCO `yolov8n.pt` and automatically switches to demo/desk mode.
- The dataset and training notebook are not part of this repository; the model was trained on a fire/smoke detection dataset and is intended for demonstration, not life-safety use.

**Why isn't the model in `requirements.txt`?** `requirements.txt` lists Python packages only — model weights are not a pip dependency. The trained fire model is committed directly to `models/fire_yolov8n.pt`, so cloning the repository is enough; there is no separate download step. The stock COCO `yolov8n.pt` is intentionally not committed: Ultralytics downloads it automatically if the custom weights are missing.

---

## Limitations & Roadmap

**Known limitations**

- Single-frame detection only: no temporal smoothing, tracking, or smoke-vs-steam discrimination.
- No gimbal/target geometry: the payload is released when a target is confirmed, not when the drone is actually aligned over it.
- Windows-first tooling; audio feedback is Windows-only.
- The model has not been validated against a formal fire-safety benchmark.
- No automated tests yet.

**Roadmap**

- [ ] ByteTrack/BoT-SORT tracking and N-frame confirmation to reduce false positives
- [ ] Target bearing/range estimation for actual payload aiming
- [ ] MAVLink integration (ArduPilot/PX4) instead of a desktop-only loop
- [ ] Recorded mission logs + post-flight review tool
- [ ] Unit tests for the state machine, cooldown logic, and serial protocol
- [ ] Cross-platform launcher scripts and containerised inference

---

## Safety Notice

This project is a prototype built for research and portfolio purposes. It must not be used as a substitute for certified fire detection or suppression equipment. Never test with uncontrolled fire; use the built-in demo mode or a supervised, permitted setup with appropriate fire-safety equipment.

---

## License

Released under the [MIT License](LICENSE).
