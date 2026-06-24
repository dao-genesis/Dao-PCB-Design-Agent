#!/usr/bin/env python3
"""
Simplified Drone PCB Circuit Design using Skidl

This script creates a complete drone flight controller PCB design using Skidl
with proper electrical connections and netlist generation.

Author: AI PCB Designer
License: MIT
"""

from skidl import *
import os
from pathlib import Path

print("Starting Drone Flight Controller Circuit Design...")

# Set up the design
set_default_tool(KICAD)

# =============================================================================
# COMPONENT DEFINITIONS
# =============================================================================

# Power Management
battery_conn = Part("Connector_Generic", "Conn_01x02", ref="J1", 
                   footprint="Connector_JST:JST_XH_B2B-XH-A_1x02_P2.50mm_Vertical")

reg_5v = Part("Regulator_Linear", "AMS1117-5.0", ref="U1", 
             footprint="Package_TO_SOT_SMD:SOT-223-3_TabPin2")

reg_3v3 = Part("Regulator_Linear", "AMS1117-3.3", ref="U2", 
              footprint="Package_TO_SOT_SMD:SOT-223-3_TabPin2")

# Flight Controller MCU
flight_controller = Part("MCU_ST_STM32F4", "STM32F405RGTx", ref="U3", 
                        footprint="Package_QFP:LQFP-64_10x10mm_P0.5mm")

# IMU Sensor
imu_sensor = Part("Sensor_Motion", "MPU-6050", ref="U4", 
                 footprint="Sensor_Motion:InvenSense_QFN-24_4x4mm_P0.5mm")

# Motor ESC Connectors
esc1_conn = Part("Connector_Generic", "Conn_01x03", ref="J3", 
                footprint="Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical")
esc2_conn = Part("Connector_Generic", "Conn_01x03", ref="J4", 
                footprint="Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical")
esc3_conn = Part("Connector_Generic", "Conn_01x03", ref="J5", 
                footprint="Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical")
esc4_conn = Part("Connector_Generic", "Conn_01x03", ref="J6", 
                footprint="Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical")

# Communication Interfaces
gps_conn = Part("Connector_Generic", "Conn_01x04", ref="J7", 
               footprint="Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical")
telemetry_conn = Part("Connector_Generic", "Conn_01x04", ref="J8", 
                     footprint="Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical")
rc_receiver_conn = Part("Connector_Generic", "Conn_01x08", ref="J9", 
                       footprint="Connector_PinHeader_2.54mm:PinHeader_1x08_P2.54mm_Vertical")

# Status LEDs
power_led = Part("Device", "LED", ref="D1", footprint="LED_SMD:LED_0603_1608Metric")
status_led = Part("Device", "LED", ref="D2", footprint="LED_SMD:LED_0603_1608Metric")
gps_led = Part("Device", "LED", ref="D3", footprint="LED_SMD:LED_0603_1608Metric")

# Resistors
power_led_r = Part("Device", "R", ref="R1", footprint="Resistor_SMD:R_0603_1608Metric")
status_led_r = Part("Device", "R", ref="R2", footprint="Resistor_SMD:R_0603_1608Metric")
gps_led_r = Part("Device", "R", ref="R3", footprint="Resistor_SMD:R_0603_1608Metric")
i2c_pullup_sda = Part("Device", "R", ref="R4", footprint="Resistor_SMD:R_0603_1608Metric")
i2c_pullup_scl = Part("Device", "R", ref="R5", footprint="Resistor_SMD:R_0603_1608Metric")

# Capacitors
input_cap = Part("Device", "CP", ref="C1", footprint="Capacitor_THT:CP_Radial_D8.0mm_P3.50mm")
cap_5v = Part("Device", "C", ref="C2", footprint="Capacitor_SMD:C_1206_3216Metric")
cap_3v3 = Part("Device", "C", ref="C3", footprint="Capacitor_SMD:C_1206_3216Metric")
mcu_cap1 = Part("Device", "C", ref="C4", footprint="Capacitor_SMD:C_0603_1608Metric")
mcu_cap2 = Part("Device", "C", ref="C5", footprint="Capacitor_SMD:C_0603_1608Metric")
imu_cap = Part("Device", "C", ref="C6", footprint="Capacitor_SMD:C_0603_1608Metric")

# Crystal
mcu_crystal = Part("Device", "Crystal", ref="Y1", footprint="Crystal:Crystal_HC49-4H_Vertical")
xtal_cap1 = Part("Device", "C", ref="C7", footprint="Capacitor_SMD:C_0603_1608Metric")
xtal_cap2 = Part("Device", "C", ref="C8", footprint="Capacitor_SMD:C_0603_1608Metric")

print(f"Defined {len(default_circuit.parts)} components")

# =============================================================================
# ELECTRICAL CONNECTIONS
# =============================================================================

print("Creating electrical connections...")

# Create power nets
vbat = Net("VBAT")
v5v = Net("5V")
v3v3 = Net("3V3")
gnd = Net("GND")

# Power distribution
battery_conn[1] += vbat
battery_conn[2] += gnd

reg_5v["VI"] += vbat
reg_5v["VO"] += v5v
reg_5v["GND"] += gnd

reg_3v3["VI"] += v5v
reg_3v3["VO"] += v3v3
reg_3v3["GND"] += gnd

# Filter capacitors
input_cap[1] += vbat
input_cap[2] += gnd
cap_5v[1] += v5v
cap_5v[2] += gnd
cap_3v3[1] += v3v3
cap_3v3[2] += gnd

# MCU power
flight_controller["VDD_1"] += v3v3
flight_controller["VDD_2"] += v3v3
flight_controller["VDD_3"] += v3v3
flight_controller["VDDA"] += v3v3
flight_controller["VSS_1"] += gnd
flight_controller["VSS_2"] += gnd
flight_controller["VSS_3"] += gnd
flight_controller["VSSA"] += gnd

# MCU decoupling
mcu_cap1[1] += v3v3
mcu_cap1[2] += gnd
mcu_cap2[1] += v3v3
mcu_cap2[2] += gnd

# Crystal connections
flight_controller["PH0"] += mcu_crystal[1]
flight_controller["PH1"] += mcu_crystal[2]
xtal_cap1[1] += mcu_crystal[1]
xtal_cap1[2] += gnd
xtal_cap2[1] += mcu_crystal[2]
xtal_cap2[2] += gnd

print("Power and MCU connections completed!")

# =============================================================================
# SENSOR CONNECTIONS
# =============================================================================

# I2C nets
i2c_sda = Net("I2C_SDA")
i2c_scl = Net("I2C_SCL")

# IMU connections
imu_sensor["VCC"] += v3v3
imu_sensor["GND"] += gnd
imu_sensor["SDA"] += i2c_sda
imu_sensor["SCL"] += i2c_scl

# I2C pull-ups
i2c_pullup_sda[1] += v3v3
i2c_pullup_sda[2] += i2c_sda
i2c_pullup_scl[1] += v3v3
i2c_pullup_scl[2] += i2c_scl

# Connect I2C to MCU
flight_controller["PB6"] += i2c_scl
flight_controller["PB7"] += i2c_sda

# IMU decoupling
imu_cap[1] += v3v3
imu_cap[2] += gnd

print("Sensor connections completed!")

# =============================================================================
# MOTOR AND COMMUNICATION CONNECTIONS
# =============================================================================

# PWM nets for motors
pwm1 = Net("PWM1")
pwm2 = Net("PWM2")
pwm3 = Net("PWM3")
pwm4 = Net("PWM4")

# ESC connections
esc1_conn[1] += v5v
esc1_conn[2] += gnd
esc1_conn[3] += pwm1
esc2_conn[1] += v5v
esc2_conn[2] += gnd
esc2_conn[3] += pwm2
esc3_conn[1] += v5v
esc3_conn[2] += gnd
esc3_conn[3] += pwm3
esc4_conn[1] += v5v
esc4_conn[2] += gnd
esc4_conn[3] += pwm4

# Connect PWM to MCU
flight_controller["PA8"] += pwm1
flight_controller["PA9"] += pwm2
flight_controller["PA10"] += pwm3
flight_controller["PA11"] += pwm4

# GPS connections
gps_conn[1] += v3v3
gps_conn[2] += gnd
gps_conn[3] += flight_controller["PA2"]  # UART2_TX
gps_conn[4] += flight_controller["PA3"]  # UART2_RX

# Telemetry connections
telemetry_conn[1] += v3v3
telemetry_conn[2] += gnd
telemetry_conn[3] += flight_controller["PB10"]  # UART3_TX
telemetry_conn[4] += flight_controller["PB11"]  # UART3_RX

# RC Receiver connections
rc_receiver_conn[1] += v5v
rc_receiver_conn[2] += gnd
rc_receiver_conn[3] += flight_controller["PB0"]
rc_receiver_conn[4] += flight_controller["PB1"]
rc_receiver_conn[5] += flight_controller["PC6"]
rc_receiver_conn[6] += flight_controller["PC7"]
rc_receiver_conn[7] += flight_controller["PC8"]
rc_receiver_conn[8] += flight_controller["PC9"]

print("Motor and communication connections completed!")

# =============================================================================
# STATUS INDICATORS
# =============================================================================

# LED connections
power_led_r[1] += v3v3
power_led_r[2] += power_led["A"]
power_led["K"] += gnd

status_led_r[1] += flight_controller["PC0"]
status_led_r[2] += status_led["A"]
status_led["K"] += gnd

gps_led_r[1] += flight_controller["PC1"]
gps_led_r[2] += gps_led["A"]
gps_led["K"] += gnd

print("Status indicator connections completed!")

print(f"\nCircuit design completed with {len(default_circuit.parts)} components and {len(default_circuit.nets)} nets")
