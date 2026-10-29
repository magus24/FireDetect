#!/usr/bin/env python3
"""
FireDtect - Autonomous Firefighting Drone Edge AI Brain & Mission Control
========================================================================
Interactive Laptop Program & Edge Vision Subsystem.
Optimized for AMD Ryzen 7 6800H + NVIDIA GeForce RTX 3070 Ti Laptop GPU.

Features:
- Auto-detection & fallback for laptop webcams (MSMF / DirectShow)
- Hotkey camera switching ('C')
- Built-in Demo / Test Mode ('M') allowing safe indoor desk testing using phone/cup
- Graphical Servo Actuator HUD (0° to 90° angle gauge)
- Manual Drop Simulation ('SPACE')
- Standalone mode with non-blocking ESP32 serial communication
- Optional tactical audio feedback ('S')
"""

import os
import sys
import time
import argparse
import logging
from pathlib import Path
from typing import Optional, Tuple, List, Dict

import cv2

# Optional Windows audio feedback
try:
    import winsound
    AUDIO_AVAILABLE = True
except ImportError:
    AUDIO_AVAILABLE = False

# Optional PySerial (Graceful fallback if not yet installed)
try:
    import serial
    import serial.tools.list_ports
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False

# PyTorch & Ultralytics
try:
    import torch
    from ultralytics import YOLO
    AI_AVAILABLE = True
except ImportError:
    AI_AVAILABLE = False

# ---------------------------------------------------------------------------
# Logging Configuration
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("FireDtect")


# ---------------------------------------------------------------------------
# Hardware Controller (ESP32 Serial Interface with Instant Simulation)
# ---------------------------------------------------------------------------
class PayloadController:
    """
    Manages serial communication with the ESP32 payload servo actuator.
    Provides non-blocking simulation when disconnected.
    """

    def __init__(self, port: str = "COM3", baud_rate: int = 115200, reconnect_interval: float = 5.0):
        self.port = port
        self.baud_rate = baud_rate
        self.reconnect_interval = reconnect_interval
        self.last_reconnect_attempt = 0.0
        self.ser = None
        self.available_ports: List[str] = []

        if SERIAL_AVAILABLE:
            self._scan_ports()
            self.connect()
        else:
            logger.warning("pyserial is not installed. Operating in STANDALONE SIMULATION mode.")

    def _scan_ports(self):
        """Scans available COM ports without blocking."""
        try:
            ports = [p.device for p in serial.tools.list_ports.comports()]
            self.available_ports = ports
            if ports:
                logger.info(f"Detected hardware serial ports: {', '.join(ports)}")
            else:
                logger.info("No active COM ports detected. Running in STANDALONE SIMULATION mode.")
        except Exception:
            self.available_ports = []

    def connect(self) -> bool:
        """Attempt to establish serial connection to ESP32."""
        if not SERIAL_AVAILABLE:
            return False

        self.last_reconnect_attempt = time.time()
        # Fast check if target port is physically connected
        if self.port not in self.available_ports:
            # Check if any port looks like an ESP32 / CH340 / CP210x
            if self.available_ports:
                logger.info(f"Target port '{self.port}' not found. Available: {self.available_ports}")
            return False

        try:
            self.ser = serial.Serial(self.port, self.baud_rate, timeout=0.2, write_timeout=0.2)
            time.sleep(1.0)
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()
            logger.info(f"Connected to ESP32 on port '{self.port}' at {self.baud_rate} baud.")
            return True
        except (serial.SerialException, OSError) as e:
            logger.warning(f"Could not open ESP32 port {self.port}: {e}")
            self.ser = None
            return False

    @property
    def is_connected(self) -> bool:
        return self.ser is not None and self.ser.is_open

    def send_drop_command(self) -> bool:
        """Transmits single-byte drop trigger ('D') to microcontroller."""
        if not self.is_connected:
            self._try_reconnect()
            if not self.is_connected:
                logger.info("[SIMULATION] Payload drop command ('D') triggered in simulation mode.")
                return False

        try:
            self.ser.write(b"D")
            self.ser.flush()
            logger.info("[HARDWARE] Drop command 'D' transmitted to ESP32 servo on GPIO 13.")
            return True
        except Exception as e:
            logger.error(f"Serial write error: {e}. Switching to simulation.")
            self.close()
            return False

    def _try_reconnect(self):
        """Non-blocking reconnection check."""
        if SERIAL_AVAILABLE and time.time() - self.last_reconnect_attempt > self.reconnect_interval:
            self._scan_ports()
            if self.port in self.available_ports:
                self.connect()

    def close(self):
        if self.ser:
            try:
                self.ser.close()
            except Exception:
                pass
            self.ser = None


# ---------------------------------------------------------------------------
# Camera Manager (Laptop Webcams with Auto-Detection & Hotkey Switching)
# ---------------------------------------------------------------------------
class LaptopCameraManager:
    """
    Robust camera manager tailored for Windows laptop built-in webcams and USB webcams.
    Tries Media Foundation (MSMF) and DirectShow (DSHOW) with automatic fallback.
    """

    def __init__(self, requested_index: int = 0):
        self.current_index = requested_index
        self.cap: Optional[cv2.VideoCapture] = None
        self.active_index = -1
        self.open_camera(self.current_index)

    def open_camera(self, index: int) -> bool:
        """Attempts to open camera with optimal backends for Windows."""
        if self.cap is not None:
            self.cap.release()

        # On Windows, DirectShow (CAP_DSHOW) is far more stable for laptop webcams than MSMF
        backends = []
        if sys.platform.startswith("win"):
            backends = [cv2.CAP_DSHOW, cv2.CAP_ANY, cv2.CAP_MSMF]
        else:
            backends = [cv2.CAP_ANY]

        # Try requested index first, then probe 0, 1, 2
        indices_to_try = [index] + [i for i in [0, 1, 2] if i != index]

        for idx in indices_to_try:
            for backend in backends:
                try:
                    cap = cv2.VideoCapture(idx, backend)
                    if not cap.isOpened():
                        continue

                    # Try reading native frame first to verify camera feed
                    ret, test_frame = cap.read()
                    if ret and test_frame is not None and test_frame.size > 0:
                        self.cap = cap
                        self.active_index = idx
                        self.current_index = idx

                        # Optionally request 720p; if unsupported, it keeps native res safely
                        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
                        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
                        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

                        actual_w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                        actual_h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                        logger.info(f"Camera opened: Index {idx} ({actual_w}x{actual_h}) via backend {backend}")
                        return True
                    cap.release()
                except Exception as e:
                    logger.debug(f"Probing camera {idx} backend {backend} failed: {e}")

        logger.error("No functional camera stream could be acquired.")
        return False

    def switch_to_next(self) -> int:
        """Cycles to the next available camera index (0 -> 1 -> 2 -> 0)."""
        next_idx = (self.active_index + 1) % 3
        logger.info(f"Switching camera to index {next_idx}...")
        if self.open_camera(next_idx):
            return self.active_index
        # Fallback to current
        self.open_camera(self.active_index)
        return self.active_index

    def read(self):
        if self.cap and self.cap.isOpened():
            try:
                ret, frame = self.cap.read()
                if ret and frame is not None and frame.size > 0:
                    return True, frame
            except Exception as e:
                logger.warning(f"Frame capture error: {e}")
                return False, None
        return False, None

    def release(self):
        if self.cap and self.cap.isOpened():
            try:
                self.cap.release()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# FireDtect Desktop Application & Brain
# ---------------------------------------------------------------------------
class FireDetectApp:
    """
    Interactive standalone Edge AI application for fire detection and capsule drop control.
    """

    WINDOW_TITLE = "FireDtect Mission Control - Edge AI (RTX 3070 Ti)"

    # Target classes for safe indoor demo testing when fire model is not available
    DEMO_TARGET_CLASSES = ["cell phone", "bottle", "cup", "fire", "flame"]

    def __init__(
        self,
        model_path: str = "models/fire_yolov8n.pt",
        conf_threshold: float = 0.75,
        cooldown_seconds: float = 5.0,
        camera_index: int = 0,
        port: str = "COM3",
        baud_rate: int = 115200,
        use_cuda: bool = True,
        demo_mode: bool = False,
    ):
        self.conf_threshold = conf_threshold
        self.cooldown_seconds = cooldown_seconds
        self.last_drop_time = 0.0
        self.demo_mode = demo_mode
        self.sound_enabled = True
        self.show_help = True

        # Drop animation simulation
        self.simulated_servo_angle = 0  # 0 to 90 degrees
        self.servo_open_duration = 3.0   # seconds held open

        # Hardware interface
        self.hardware = PayloadController(port=port, baud_rate=baud_rate)

        # Edge Compute Device (RTX 3070 Ti)
        self.device = self._configure_device(use_cuda)
        self.use_half = self.device.startswith("cuda")

        # Load Vision AI Model
        self.model = self._load_model(model_path)
        self.fire_class_ids = self._resolve_target_classes()

        # Laptop Camera
        self.cam_manager = LaptopCameraManager(camera_index)

    def _configure_device(self, prefer_cuda: bool) -> str:
        if not AI_AVAILABLE:
            logger.warning("PyTorch/Ultralytics not installed. Vision model disabled.")
            return "cpu"

        if prefer_cuda and torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0)
            vram_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3)
            logger.info(f"Compute Engine: CUDA Hardware Acceleration -> [{gpu_name}] ({vram_gb:.1f} GB VRAM)")
            return "cuda:0"
        else:
            logger.info("Compute Engine: Running on CPU.")
            return "cpu"

    def _load_model(self, model_path: str):
        if not AI_AVAILABLE:
            return None

        resolved_path = Path(model_path)
        if not resolved_path.is_absolute():
            base_dir = Path(__file__).resolve().parent.parent
            if (base_dir / model_path).exists():
                resolved_path = base_dir / model_path

        if resolved_path.exists():
            logger.info(f"Loading custom fire model: {resolved_path}")
            model = YOLO(str(resolved_path))
        else:
            logger.warning(f"Custom model '{model_path}' not found.")
            logger.info("Initializing baseline 'yolov8n.pt'. Enabling DEMO TARGET MODE for laptop desk testing.")
            model = YOLO("yolov8n.pt")
            self.demo_mode = True  # Automatically enable demo target mode for easy testing!

        model.to(self.device)

        # Warmup pass
        try:
            dummy = torch.zeros((1, 3, 640, 640), device=self.device)
            _ = model(dummy, verbose=False)
            logger.info("CUDA Tensor Cores primed & warmed up.")
        except Exception:
            pass
            pass

        return model

    def _resolve_target_classes(self) -> List[int]:
        """Resolves class IDs to trigger on based on model and active mode."""
        if not self.model or not hasattr(self.model, "names"):
            return [0]

        names = self.model.names
        matched_ids = []

        # Check if the loaded model is a specialized Fire/Smoke model
        has_fire_class = any("fire" in str(n).lower() or "flame" in str(n).lower() for n in names.values())

        if has_fire_class:
            # Model has specialized fire/smoke classes
            for cid, name in names.items():
                clean_name = str(name).lower()
                if "fire" in clean_name or "flame" in clean_name or "smoke" in clean_name:
                    matched_ids.append(cid)
            logger.info(f"Specialized Fire/Smoke model active! Tracking classes: {[names[i] for i in matched_ids]}")
            return matched_ids

        # Otherwise standard COCO weights are loaded
        if self.demo_mode:
            for cid, name in names.items():
                clean_name = str(name).lower()
                if any(target in clean_name for target in self.DEMO_TARGET_CLASSES):
                    matched_ids.append(cid)
            logger.info(f"COCO Demo Mode active: Tracking desk objects: {[names[i] for i in matched_ids]}")
        else:
            # If user wanted fire but COCO is loaded, warn them
            logger.warning("Generic COCO model loaded (no fire class). Falling back to demo targets.")
            for cid, name in names.items():
                if any(k in str(name).lower() for k in ["cell phone", "bottle", "cup"]):
                    matched_ids.append(cid)

        if not matched_ids:
            matched_ids = [0]

        return matched_ids

    def toggle_demo_mode(self):
        """Toggles between strict Fire detection and Demo Desk testing mode."""
        self.demo_mode = not self.demo_mode
        self.fire_class_ids = self._resolve_target_classes()
        logger.info(f"Mode switched: {'DEMO DESK TEST' if self.demo_mode else 'STRICT FIRE ONLY'}")

    def trigger_drop(self, manual: bool = False):
        """Initiates payload capsule drop sequence."""
        self.last_drop_time = time.time()
        self.hardware.send_drop_command()

        # Audio cue (non-blocking beep on Windows)
        if self.sound_enabled and AUDIO_AVAILABLE:
            try:
                winsound.Beep(1500, 180)
            except Exception:
                pass

        log_prefix = "[MANUAL TEST]" if manual else "[AUTONOMOUS]"
        logger.info(f"{log_prefix} CAPSULE DROPPED! Servo actuated to 90 degrees.")

    def run(self):
        """Main application interactive GUI loop."""
        cv2.namedWindow(self.WINDOW_TITLE, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(self.WINDOW_TITLE, 1280, 720)

        logger.info("Application running. Displaying interactive Mission Control HUD.")

        prev_time = time.time()
        fps = 0.0

        try:
            while True:
                ret, frame = self.cam_manager.read()
                if not ret or frame is None:
                    # Provide an informative standby screen instead of crashing
                    frame = self._render_standby_screen()
                    cv2.imshow(self.WINDOW_TITLE, frame)
                    key = cv2.waitKey(100) & 0xFF
                    if key in [ord("q"), ord("Q"), 27]:
                        break
                    elif key in [ord("c"), ord("C")]:
                        self.cam_manager.switch_to_next()
                    continue

                loop_time = time.time()
                current_time = loop_time

                # Cooldown calculations
                time_since_drop = current_time - self.last_drop_time
                cooldown_remaining = max(0.0, self.cooldown_seconds - time_since_drop)

                # Simulated servo angle (0 to 90 degrees during drop)
                if time_since_drop < self.servo_open_duration:
                    self.simulated_servo_angle = 90
                else:
                    self.simulated_servo_angle = 0

                # 1. Edge AI Inference
                best_target = None
                infer_latency_ms = 0.0

                if self.model is not None:
                    infer_start = time.time()
                    # Run with lower threshold (0.35) for detection tracking
                    results = self.model(
                        frame,
                        stream=True,
                        verbose=False,
                        device=self.device,
                        conf=0.35,
                    )

                    highest_conf = 0.0
                    for r in results:
                        if r.boxes is None:
                            continue
                        for box in r.boxes:
                            conf = float(box.conf[0].item())
                            cls_id = int(box.cls[0].item())

                            if cls_id in self.fire_class_ids:
                                if conf > highest_conf:
                                    highest_conf = conf
                                    x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                                    label = self.model.names.get(cls_id, "Target")
                                    best_target = (x1, y1, x2, y2, conf, label)

                    infer_latency_ms = (time.time() - infer_start) * 1000.0

                # 2. State Machine Logic
                system_state = "PATROL / SCANNING"
                if best_target is not None:
                    x1, y1, x2, y2, conf, label = best_target
                    is_locked = conf >= self.conf_threshold
                    self._draw_target_box(frame, x1, y1, x2, y2, conf, label, locked=is_locked)

                    if is_locked:
                        if cooldown_remaining == 0.0:
                            system_state = f"{label.upper()} CONFIRMED -> DROPPING CAPSULE"
                            self.trigger_drop(manual=False)
                            cooldown_remaining = self.cooldown_seconds
                        else:
                            system_state = f"TARGET LOCKED (RELOAD: {cooldown_remaining:.1f}s)"
                    else:
                        system_state = f"DETECTED: {label.upper()} ({conf*100:.0f}% < {self.conf_threshold*100:.0f}%)"
                elif self.simulated_servo_angle == 90:
                    system_state = "SERVO OPEN (90 DEG) - RELEASING PAYLOAD"
                elif cooldown_remaining > 0.0:
                    system_state = f"COOLDOWN ACTIVE ({cooldown_remaining:.1f}s)"

                # 3. FPS Smoothing
                frame_delta = current_time - prev_time
                prev_time = current_time
                if frame_delta > 0:
                    fps = 0.85 * fps + 0.15 * (1.0 / frame_delta)

                # 4. Render Tactical Telemetry HUD
                self._draw_hud(frame, fps, infer_latency_ms, system_state, cooldown_remaining)

                # 5. Display Frame
                cv2.imshow(self.WINDOW_TITLE, frame)

                # 6. Interactive Keyboard Controls
                key = cv2.waitKey(1) & 0xFF
                if key in [ord("q"), ord("Q"), 27]:  # Q or ESC -> Exit
                    logger.info("Exit command received.")
                    break
                elif key == 32:  # SPACE -> Manual Drop Test
                    self.trigger_drop(manual=True)
                elif key in [ord("c"), ord("C")]:  # C -> Switch Camera
                    self.cam_manager.switch_to_next()
                elif key in [ord("m"), ord("M"), ord("t"), ord("T")]:  # M/T -> Toggle Demo Mode
                    self.toggle_demo_mode()
                elif key in [ord("s"), ord("S")]:  # S -> Sound toggle
                    self.sound_enabled = not self.sound_enabled
                    logger.info(f"Audio cues: {'ENABLED' if self.sound_enabled else 'MUTED'}")
                elif key in [ord("h"), ord("H")]:  # H -> Toggle Help
                    self.show_help = not self.show_help

        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received.")
        finally:
            self.cleanup()

    def _render_standby_screen(self):
        """Generates a clean standby screen when no camera is streaming."""
        import numpy as np
        img = np.zeros((720, 1280, 3), dtype=np.uint8)
        img[:] = (25, 25, 30)

        cv2.putText(img, "FIREDTECT // CAMERA ACQUISITION STANDBY", (300, 320),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 165, 255), 2, cv2.LINE_AA)
        cv2.putText(img, "Press [C] to switch camera index (0, 1, 2) or [Q] to quit", (320, 380),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, (200, 200, 200), 1, cv2.LINE_AA)
        return img

    def _draw_target_box(self, frame, x1: int, y1: int, x2: int, y2: int, conf: float, label: str, locked: bool = True):
        """Draws dynamic tactical target lock box with animated corners."""
        is_fire = "fire" in label.lower() or "flame" in label.lower()

        if locked:
            color = (0, 0, 255)  # Bright Red for Target Locked
            title_prefix = "TARGET LOCKED"
        else:
            color = (0, 200, 255) if is_fire else (0, 215, 255)  # Amber / Yellow for tracking
            title_prefix = "TRACKING"

        # Main box
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

        # Tactical corners
        corner_len = min(25, int((x2 - x1) / 3), int((y2 - y1) / 3))
        if corner_len > 4:
            cv2.line(frame, (x1, y1), (x1 + corner_len, y1), color, 4)
            cv2.line(frame, (x1, y1), (x1, y1 + corner_len), color, 4)
            cv2.line(frame, (x2, y1), (x2 - corner_len, y1), color, 4)
            cv2.line(frame, (x2, y1), (x2, y1 + corner_len), color, 4)
            cv2.line(frame, (x1, y2), (x1 + corner_len, y2), color, 4)
            cv2.line(frame, (x1, y2), (x1, y2 - corner_len), color, 4)
            cv2.line(frame, (x2, y2), (x2 - corner_len, y2), color, 4)
            cv2.line(frame, (x2, y2), (x2, y2 - corner_len), color, 4)

        # Crosshair marker
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        cv2.drawMarker(frame, (cx, cy), color, cv2.MARKER_CROSS, 20, 2)

        # Tactical banner
        tag = f"{title_prefix}: {label.upper()} [{conf * 100:.1f}%]"
        (bw, bh), _ = cv2.getTextSize(tag, cv2.FONT_HERSHEY_SIMPLEX, 0.65, 2)
        cv2.rectangle(frame, (x1, max(0, y1 - bh - 10)), (x1 + bw + 14, y1), color, -1)
        cv2.putText(
            frame,
            tag,
            (x1 + 6, max(18, y1 - 6)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (255, 255, 255) if locked else (0, 0, 0),
            2,
            cv2.LINE_AA,
        )

    def _draw_hud(self, frame, fps: float, latency_ms: float, state: str, cooldown: float):
        """Draws edge telemetry, graphical servo status, and on-screen keyboard controls."""
        h, w = frame.shape[:2]

        # Top Bar (Glassmorphism overlay)
        top_bar = frame[0:55, 0:w].copy()
        cv2.rectangle(frame, (0, 0), (w, 55), (15, 18, 24), -1)
        cv2.addWeighted(top_bar, 0.35, frame[0:55, 0:w], 0.65, 0, frame[0:55, 0:w])

        # Bottom Bar
        bottom_bar = frame[h - 45:h, 0:w].copy()
        cv2.rectangle(frame, (0, h - 45), (w, h), (15, 18, 24), -1)
        cv2.addWeighted(bottom_bar, 0.35, frame[h - 45:h, 0:w], 0.65, 0, frame[h - 45:h, 0:w])

        # 1. Brand & Camera Index
        cam_idx = self.cam_manager.active_index
        cv2.putText(
            frame,
            f"FIREDTECT MISSION CONTROL  |  LAPTOP CAM [{cam_idx}]",
            (16, 35),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (0, 215, 255),
            2,
            cv2.LINE_AA,
        )

        # 2. Performance Telemetry
        device_label = self.device.upper()
        if "CUDA" in device_label:
            dev_color = (0, 255, 0)
        else:
            dev_color = (180, 180, 180)

        telemetry_text = f"{fps:4.1f} FPS | {latency_ms:4.1f}ms [{device_label}]"
        cv2.putText(
            frame,
            telemetry_text,
            (w - 330, 35),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            dev_color,
            1,
            cv2.LINE_AA,
        )

        # 3. Servo Actuator Widget (Visual 0° vs 90° indicator)
        servo_color = (0, 255, 0) if self.simulated_servo_angle == 0 else (0, 0, 255)
        servo_status = f"SERVO: {self.simulated_servo_angle}* [{'LOCKED' if self.simulated_servo_angle == 0 else 'OPEN - DROPPING'}]"
        cv2.rectangle(frame, (16, 68), (270, 102), (20, 24, 30), -1)
        cv2.rectangle(frame, (16, 68), (270, 102), servo_color, 1)
        cv2.putText(
            frame,
            servo_status,
            (25, 91),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.52,
            servo_color,
            1,
            cv2.LINE_AA,
        )

        # 4. Mode Badge (Fire vs Demo Target)
        mode_label = "MODE: DEMO (PHONE/CUP)" if self.demo_mode else "MODE: FIRE DETECTION"
        mode_color = (0, 215, 255) if self.demo_mode else (0, 100, 255)
        cv2.rectangle(frame, (285, 68), (535, 102), (20, 24, 30), -1)
        cv2.rectangle(frame, (285, 68), (535, 102), mode_color, 1)
        cv2.putText(
            frame,
            mode_label,
            (295, 91),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.50,
            mode_color,
            1,
            cv2.LINE_AA,
        )

        # 5. Bottom Status: Hardware State & System State
        hw_connected = self.hardware.is_connected
        hw_text = "ESP32: CONNECTED" if hw_connected else "ESP32: OFFLINE (SIMULATION)"
        hw_color = (0, 255, 0) if hw_connected else (0, 165, 255)
        cv2.putText(
            frame,
            hw_text,
            (16, h - 16),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            hw_color,
            1,
            cv2.LINE_AA,
        )

        # State text
        state_color = (0, 0, 255) if "FIRE" in state or "DROPPING" in state else (0, 255, 128)
        if "RELOAD" in state or "COOLDOWN" in state:
            state_color = (0, 165, 255)
        cv2.putText(
            frame,
            f"STATE: {state}",
            (w // 2 - 160, h - 16),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            state_color,
            2,
            cv2.LINE_AA,
        )

        # 6. Keyboard Control Legend (Bottom Right / Side)
        if self.show_help:
            keys_text = "[SPACE] Drop Test  |  [C] Switch Cam  |  [M] Demo Mode  |  [Q] Exit"
            cv2.putText(
                frame,
                keys_text,
                (w - 530, h - 16),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.46,
                (200, 200, 200),
                1,
                cv2.LINE_AA,
            )

    def cleanup(self):
        """Release hardware and video streams safely."""
        logger.info("Cleaning up application resources...")
        self.cam_manager.release()
        cv2.destroyAllWindows()
        self.hardware.close()
        logger.info("Application terminated cleanly.")


# ---------------------------------------------------------------------------
# CLI Argument Parser
# ---------------------------------------------------------------------------
def parse_args():
    parser = argparse.ArgumentParser(description="FireDtect Mission Control Application")
    parser.add_argument(
        "--model",
        type=str,
        default="models/fire_yolov8n.pt",
        help="Path to YOLOv8 fire weights (default: models/fire_yolov8n.pt)",
    )
    parser.add_argument(
        "--port",
        type=str,
        default="COM3",
        help="Serial port for ESP32 (default: COM3)",
    )
    parser.add_argument(
        "--baud",
        type=int,
        default=115200,
        help="Serial baud rate (default: 115200)",
    )
    parser.add_argument(
        "--conf",
        type=float,
        default=0.75,
        help="Detection confidence threshold (default: 0.75)",
    )
    parser.add_argument(
        "--cooldown",
        type=float,
        default=5.0,
        help="Cooldown between capsule drops (default: 5.0 seconds)",
    )
    parser.add_argument(
        "--camera",
        type=int,
        default=0,
        help="Camera device index (default: 0 for laptop webcam)",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Start in demo target mode (triggers on phone/cup for easy desk testing)",
    )
    parser.add_argument(
        "--cpu",
        action="store_true",
        help="Force CPU execution",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    app = FireDetectApp(
        model_path=args.model,
        conf_threshold=args.conf,
        cooldown_seconds=args.cooldown,
        camera_index=args.camera,
        port=args.port,
        baud_rate=args.baud,
        use_cuda=not args.cpu,
        demo_mode=args.demo,
    )
    app.run()


if __name__ == "__main__":
    main()
