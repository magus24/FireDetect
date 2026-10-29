/*
 * FireDtect - Autonomous Firefighting Drone Payload Actuator Firmware
 * ====================================================================
 * Target: ESP32 Dev Module / ESP32-WROOM-32
 * Library Requirement: ESP32Servo (by Kevin Harrington, available via Arduino Library Manager)
 * 
 * Hardware Configuration:
 *   - Servo Signal: GPIO 13 (PWM)
 *   - Status LED:   GPIO 2  (Builtin LED on most ESP32 boards)
 *   - Baud Rate:    115200 bps (UART0 via USB)
 * 
 * Communication Protocol:
 *   - 'D' : Drop Payload (rotates servo to 90 deg, holds for 3000ms, resets to 0 deg)
 *   - 'R' : Emergency Reset / Close servo immediately
 *   - 'S' : Status ping (returns current mechanism state)
 *   - 'T' : Test sweep
 */

#include <ESP32Servo.h>

// --- HARDWARE PIN DEFINITIONS ---
const int SERVO_PIN  = 13;       // Servo PWM signal line
const int STATUS_LED = 2;        // Builtin status LED (GPIO 2)

// --- ACTUATOR CALIBRATION ---
const int ANGLE_CLOSED = 0;      // Locked / flight position (degrees)
const int ANGLE_OPEN   = 90;     // Release / drop position (degrees)
const unsigned long DROP_HOLD_MS = 3000; // Duration to keep hatch open (3.0 sec)

// --- SERVO TIMING PARAMETERS (SG90 / MG995 / MG996R) ---
const int MIN_PULSE_US = 500;    // Minimum pulse width in microseconds
const int MAX_PULSE_US = 2400;   // Maximum pulse width in microseconds

// --- STATE MACHINE ---
enum PayloadState {
  STATE_IDLE_CLOSED,
  STATE_PAYLOAD_RELEASING,
  STATE_COOLDOWN
};

PayloadState currentState = STATE_IDLE_CLOSED;
unsigned long stateTimerStart = 0;

Servo payloadServo;

void setup() {
  Serial.begin(115200);
  pinMode(STATUS_LED, OUTPUT);
  digitalWrite(STATUS_LED, LOW);

  // Allocate 16-bit PWM timers for ESP32
  ESP32PWM::allocateTimer(0);
  ESP32PWM::allocateTimer(1);
  ESP32PWM::allocateTimer(2);
  ESP32PWM::allocateTimer(3);

  // Standard 50Hz PWM frequency for analog & digital hobby servos
  payloadServo.setPeriodHertz(50);
  payloadServo.attach(SERVO_PIN, MIN_PULSE_US, MAX_PULSE_US);

  // Lock payload on startup
  payloadServo.write(ANGLE_CLOSED);
  currentState = STATE_IDLE_CLOSED;

  // Visual confirmation blink
  for (int i = 0; i < 3; i++) {
    digitalWrite(STATUS_LED, HIGH);
    delay(80);
    digitalWrite(STATUS_LED, LOW);
    delay(80);
  }

  Serial.println(F("{\"system\":\"FireDtect_ESP32\",\"version\":\"1.0.0\",\"status\":\"READY\",\"pin\":13}"));
  Serial.println(F("[ESP32] FireDtect Payload Servo Subsystem Initialized."));
}

void loop() {
  // 1. Process Serial Commands from Jetson / Laptop Host
  handleSerialInput();

  // 2. Non-blocking State Machine for Servo Drop Sequencing
  updatePayloadStateMachine();
}

void handleSerialInput() {
  while (Serial.available() > 0) {
    char cmd = (char)Serial.read();

    switch (cmd) {
      case 'D': // Drop Trigger
      case 'd':
        if (currentState == STATE_IDLE_CLOSED) {
          triggerDropSequence();
        } else {
          Serial.println(F("[WARNING] Drop command ignored: Mechanism is already in active cycle."));
        }
        break;

      case 'R': // Emergency Reset / Abort
      case 'r':
        resetMechanism();
        Serial.println(F("[SAFETY] Emergency reset: Mechanism locked to CLOSED."));
        break;

      case 'S': // Query Status
      case 's':
        reportStatus();
        break;

      case 'T': // Diagnostic Test
      case 't':
        Serial.println(F("[TEST] Running self-test pulse..."));
        triggerDropSequence();
        break;

      case '\n':
      case '\r':
      case ' ':
        // Ignore whitespace
        break;

      default:
        Serial.print(F("[UNKNOWN_CMD] Received: "));
        Serial.println(cmd);
        break;
    }
  }
}

void triggerDropSequence() {
  Serial.println(F("[ACTION] Payload Drop Initiated! Opening mechanism to 90 deg..."));
  digitalWrite(STATUS_LED, HIGH);
  payloadServo.write(ANGLE_OPEN);

  currentState = STATE_PAYLOAD_RELEASING;
  stateTimerStart = millis();
}

void resetMechanism() {
  payloadServo.write(ANGLE_CLOSED);
  digitalWrite(STATUS_LED, LOW);
  currentState = STATE_IDLE_CLOSED;
}

void updatePayloadStateMachine() {
  unsigned long now = millis();

  switch (currentState) {
    case STATE_PAYLOAD_RELEASING:
      // Keep open for DROP_HOLD_MS without freezing the CPU
      if (now - stateTimerStart >= DROP_HOLD_MS) {
        Serial.println(F("[ACTION] Drop timer elapsed. Returning mechanism to 0 deg (CLOSED)..."));
        payloadServo.write(ANGLE_CLOSED);
        digitalWrite(STATUS_LED, LOW);
        currentState = STATE_IDLE_CLOSED;
        Serial.println(F("[STATUS] Mechanism CLOSED. Ready for next mission target."));
      }
      break;

    case STATE_IDLE_CLOSED:
    default:
      // In standby, ensure LED is off
      break;
  }
}

void reportStatus() {
  Serial.print(F("[STATUS] Current State: "));
  switch (currentState) {
    case STATE_IDLE_CLOSED:
      Serial.println(F("IDLE_CLOSED (READY)"));
      break;
    case STATE_PAYLOAD_RELEASING:
      Serial.print(F("RELEASING (Elapsed: "));
      Serial.print(millis() - stateTimerStart);
      Serial.println(F("ms)"));
      break;
    default:
      Serial.println(F("UNKNOWN"));
      break;
  }
}
