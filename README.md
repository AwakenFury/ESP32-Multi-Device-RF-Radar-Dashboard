
![ ESP32-Multi-Device-RF-Radar-Dashboard](asset//ESP32Radar.png)
![Status](https://img.shields.io/badge/status-experimental-red)
![ESP32](https://img.shields.io/badge/platform-ESP32-blue)


## ESP32 Multi-Device RF Radar Dashboard

A real-time RF situational awareness and device tracking system powered by an ESP32 and a Python tactical dashboard.

This project combines Wi-Fi, BLE, and Classic Bluetooth scanning with motion sensing, IMU orientation tracking, and magnetometer heading data to visualize nearby wireless activity on a live radar-style interface.

The ESP32 continuously scans for nearby devices, estimates relative distance using RSSI signal strength, and streams telemetry over serial to a Python desktop dashboard that renders a tactical radar display with motion trails and device persistence.

Features
 - Real-time Wi-Fi device scanning
 - BLE advertisement detection
 - Classic Bluetooth discovery
 - RSSI-based distance estimation
 - Radar-style tactical visualization
 - Device motion trails
 - OLED signal display on ESP32
 - MPU6050 orientation tracking
 - BMM150 magnetometer heading integration
 - Motion sensor detection
 - CSV logging system
 - Tamper/offline detection framework
 - Serial telemetry streaming
 - Multi-panel desktop dashboard
 - System Architecture
 - ESP32 Firmware

The ESP32 acts as the sensing and telemetry platform.

## It performs:

 - Wi-Fi network scans
 - BLE scans
 - Classic Bluetooth discovery
 - Motion detection
 - IMU orientation sampling
 - Magnetometer heading reads
 - OLED visualization
 - Serial telemetry transmission
 - Python Dashboard

The Python application receives serial telemetry from the ESP32 and renders a live tactical dashboard using Tkinter.

The dashboard includes:

 - Real-time radar sweep
 - Device persistence tracking
 - RSSI-based positioning
 - Device trail rendering
 - Signal strength visualization
 - Magnetometer telemetry display
 - Device statistics panels
 - Serial connection monitoring
 - Logging and tamper event tracking
 - Radar Logic
 - Displays nearby Wi-Fi devices and signal strength
 - BLE Devices
 - Shows detected BLE advertisements
 - Bluetooth Devices
 - Tracks nearby Classic Bluetooth devices
 - Magnetometer Feed
 - Displays live magnetic field telemetry samples

## Tactical Radar

Visualizes:

 - Estimated device positions
 - Radar sweep
 - Motion trails
 - Device persistence
 - Orientation heading
 - Logging

## Disclaimer

This project is intended for educational, research, and defensive RF visualization purposes only.

# Do not use this system to interfere with wireless communications or violate privacy laws.

Example Use Cases
 - RF visualization experiments
 - Wireless situational awareness
 - Security research
 - Sensor fusion experiments
 - Tactical UI development
 - Device density mapping
 - Embedded telemetry systems
 - Cyber-physical dashboard prototyping
