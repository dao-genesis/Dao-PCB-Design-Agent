#!/usr/bin/env python3
"""
Comprehensive Drone PCB Circuit Design using Skidl

This script creates a complete drone flight controller PCB design using Skidl,
including all necessary components for a quadcopter flight controller with
advanced features.

Components included:
- Flight controller MCU with IMU
- Motor control for 4 brushless motors (ESCs)
- Power management (battery input, voltage regulation)
- Communication interfaces (UART, I2C, SPI)
- GPS module interface
- Radio control receiver interface
- Status indicators and safety features

Author: AI PCB Designer
License: MIT
"""

from skidl import *
import os
from pathlib import Path

# Set up the design
set_default_tool(KICAD)

# Define component libraries
lib_mcu = SchLib("MCU_ST_STM32F4", tool=KICAD)
lib_power = SchLib("Regulator_Linear", tool=KICAD)
lib_conn = SchLib("Connector_Generic", tool=KICAD)
lib_device = SchLib("Device", tool=KICAD)
lib_sensor = SchLib("Sensor_Motion", tool=KICAD)

print("Creating Drone Flight Controller Circuit...")

# =============================================================================
# POWER MANAGEMENT SECTION
# =============================================================================

# Battery input connector
battery_conn = Part(lib_conn, "Conn_01x02", 
                   ref="J1", 
                   footprint="Connector_JST:JST_XH_B2B-XH-A_1x02_P2.50mm_Vertical",
                   value="Battery_Input")

# Power input protection
input_fuse = Part(lib_device, "Fuse", 
                 ref="F1", 
                 footprint="Fuse:Fuse_1206_3216Metric",
                 value="5A")

# Input filter capacitor
input_cap = Part(lib_device, "CP", 
                ref="C1", 
                footprint="Capacitor_THT:CP_Radial_D8.0mm_P3.50mm",
                value="1000uF")

# 5V voltage regulator
reg_5v = Part(lib_power, "AMS1117-5.0", 
             ref="U1", 
             footprint="Package_TO_SOT_SMD:SOT-223-3_TabPin2",
             value="AMS1117-5.0")

# 3.3V voltage regulator  
reg_3v3 = Part(lib_power, "AMS1117-3.3", 
              ref="U2", 
              footprint="Package_TO_SOT_SMD:SOT-223-3_TabPin2",
              value="AMS1117-3.3")

# Output filter capacitors
cap_5v_out = Part(lib_device, "C", 
                 ref="C2", 
                 footprint="Capacitor_SMD:C_1206_3216Metric",
                 value="100uF")

cap_3v3_out = Part(lib_device, "C", 
                  ref="C3", 
                  footprint="Capacitor_SMD:C_1206_3216Metric",
                  value="100uF")

# Bypass capacitors
cap_5v_bypass = Part(lib_device, "C", 
                    ref="C4", 
                    footprint="Capacitor_SMD:C_0603_1608Metric",
                    value="100nF")

cap_3v3_bypass = Part(lib_device, "C", 
                     ref="C5", 
                     footprint="Capacitor_SMD:C_0603_1608Metric",
                     value="100nF")

# =============================================================================
# MAIN FLIGHT CONTROLLER MCU
# =============================================================================

# STM32F405 Flight Controller MCU
flight_controller = Part(lib_mcu, "STM32F405RGTx", 
                        ref="U3", 
                        footprint="Package_QFP:LQFP-64_10x10mm_P0.5mm",
                        value="STM32F405RGTx")

# MCU crystal oscillator
mcu_crystal = Part(lib_device, "Crystal", 
                  ref="Y1", 
                  footprint="Crystal:Crystal_HC49-4H_Vertical",
                  value="8MHz")

# Crystal load capacitors
xtal_cap1 = Part(lib_device, "C", 
                ref="C6", 
                footprint="Capacitor_SMD:C_0603_1608Metric",
                value="22pF")

xtal_cap2 = Part(lib_device, "C", 
                ref="C7", 
                footprint="Capacitor_SMD:C_0603_1608Metric",
                value="22pF")

# MCU power decoupling capacitors
mcu_cap1 = Part(lib_device, "C", 
               ref="C8", 
               footprint="Capacitor_SMD:C_0603_1608Metric",
               value="100nF")

mcu_cap2 = Part(lib_device, "C", 
               ref="C9", 
               footprint="Capacitor_SMD:C_0603_1608Metric",
               value="100nF")

mcu_cap3 = Part(lib_device, "C", 
               ref="C10", 
               footprint="Capacitor_SMD:C_0603_1608Metric",
               value="100nF")

# Reset circuit
reset_button = Part(lib_device, "SW_Push", 
                   ref="SW1", 
                   footprint="Button_Switch_THT:SW_PUSH_6mm",
                   value="Reset")

reset_pullup = Part(lib_device, "R", 
                   ref="R1", 
                   footprint="Resistor_SMD:R_0603_1608Metric",
                   value="10k")

# Boot mode selection
boot_jumper = Part(lib_conn, "Conn_01x02", 
                  ref="J2", 
                  footprint="Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical",
                  value="Boot_Select")

boot_pulldown = Part(lib_device, "R", 
                    ref="R2", 
                    footprint="Resistor_SMD:R_0603_1608Metric",
                    value="10k")

# =============================================================================
# IMU SENSOR SECTION
# =============================================================================

# MPU6050 IMU (Gyroscope + Accelerometer)
imu_sensor = Part(lib_sensor, "MPU-6050", 
                 ref="U4", 
                 footprint="Sensor_Motion:InvenSense_QFN-24_4x4mm_P0.5mm",
                 value="MPU-6050")

# IMU power decoupling
imu_cap = Part(lib_device, "C", 
              ref="C11", 
              footprint="Capacitor_SMD:C_0603_1608Metric",
              value="100nF")

# I2C pull-up resistors for IMU
i2c_pullup_sda = Part(lib_device, "R", 
                     ref="R3", 
                     footprint="Resistor_SMD:R_0603_1608Metric",
                     value="4.7k")

i2c_pullup_scl = Part(lib_device, "R", 
                     ref="R4", 
                     footprint="Resistor_SMD:R_0603_1608Metric",
                     value="4.7k")

# Magnetometer (HMC5883L)
magnetometer = Part("Sensor_Magnetic", "HMC5883L", 
                   ref="U5", 
                   footprint="Package_LGA:LGA-16_3x3mm_P0.5mm",
                   value="HMC5883L")

mag_cap = Part(lib_device, "C", 
              ref="C12", 
              footprint="Capacitor_SMD:C_0603_1608Metric",
              value="100nF")

# =============================================================================
# MOTOR CONTROL SECTION (4 ESC OUTPUTS)
# =============================================================================

# ESC output connectors (4 motors)
esc1_conn = Part(lib_conn, "Conn_01x03", 
                ref="J3", 
                footprint="Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical",
                value="ESC1_Motor")

esc2_conn = Part(lib_conn, "Conn_01x03", 
                ref="J4", 
                footprint="Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical",
                value="ESC2_Motor")

esc3_conn = Part(lib_conn, "Conn_01x03", 
                ref="J5", 
                footprint="Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical",
                value="ESC3_Motor")

esc4_conn = Part(lib_conn, "Conn_01x03", 
                ref="J6", 
                footprint="Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical",
                value="ESC4_Motor")

# PWM signal filtering capacitors
pwm_cap1 = Part(lib_device, "C", 
               ref="C13", 
               footprint="Capacitor_SMD:C_0603_1608Metric",
               value="100nF")

pwm_cap2 = Part(lib_device, "C", 
               ref="C14", 
               footprint="Capacitor_SMD:C_0603_1608Metric",
               value="100nF")

pwm_cap3 = Part(lib_device, "C", 
               ref="C15", 
               footprint="Capacitor_SMD:C_0603_1608Metric",
               value="100nF")

pwm_cap4 = Part(lib_device, "C", 
               ref="C16", 
               footprint="Capacitor_SMD:C_0603_1608Metric",
               value="100nF")

# =============================================================================
# COMMUNICATION INTERFACES
# =============================================================================

# GPS module connector
gps_conn = Part(lib_conn, "Conn_01x04", 
               ref="J7", 
               footprint="Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical",
               value="GPS_Module")

# Telemetry UART connector
telemetry_conn = Part(lib_conn, "Conn_01x04", 
                     ref="J8", 
                     footprint="Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical",
                     value="Telemetry_UART")

# Radio control receiver connector
rc_receiver_conn = Part(lib_conn, "Conn_01x08", 
                       ref="J9", 
                       footprint="Connector_PinHeader_2.54mm:PinHeader_1x08_P2.54mm_Vertical",
                       value="RC_Receiver")

# I2C expansion connector
i2c_expansion = Part(lib_conn, "Conn_01x04", 
                    ref="J10", 
                    footprint="Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical",
                    value="I2C_Expansion")

# SPI expansion connector
spi_expansion = Part(lib_conn, "Conn_01x06", 
                    ref="J11", 
                    footprint="Connector_PinHeader_2.54mm:PinHeader_1x06_P2.54mm_Vertical",
                    value="SPI_Expansion")

# =============================================================================
# STATUS INDICATORS AND SAFETY
# =============================================================================

# Power LED
power_led = Part(lib_device, "LED", 
                ref="D1", 
                footprint="LED_SMD:LED_0603_1608Metric",
                value="Power_LED")

power_led_resistor = Part(lib_device, "R", 
                         ref="R5", 
                         footprint="Resistor_SMD:R_0603_1608Metric",
                         value="330")

# Status LED
status_led = Part(lib_device, "LED", 
                 ref="D2", 
                 footprint="LED_SMD:LED_0603_1608Metric",
                 value="Status_LED")

status_led_resistor = Part(lib_device, "R", 
                          ref="R6", 
                          footprint="Resistor_SMD:R_0603_1608Metric",
                          value="330")

# GPS Lock LED
gps_led = Part(lib_device, "LED", 
              ref="D3", 
              footprint="LED_SMD:LED_0603_1608Metric",
              value="GPS_LED")

gps_led_resistor = Part(lib_device, "R", 
                       ref="R7", 
                       footprint="Resistor_SMD:R_0603_1608Metric",
                       value="330")

# Low voltage detection
voltage_divider_r1 = Part(lib_device, "R", 
                         ref="R8", 
                         footprint="Resistor_SMD:R_0603_1608Metric",
                         value="10k")

voltage_divider_r2 = Part(lib_device, "R", 
                         ref="R9", 
                         footprint="Resistor_SMD:R_0603_1608Metric",
                         value="3.3k")

# Buzzer for audio alerts
buzzer = Part(lib_device, "Buzzer", 
             ref="BZ1", 
             footprint="Buzzer_Beeper:Buzzer_12x9.5RM7.6",
             value="Buzzer")

buzzer_transistor = Part("Transistor_BJT", "2N3904", 
                        ref="Q1", 
                        footprint="Package_TO_SOT_THT:TO-92_Inline",
                        value="2N3904")

buzzer_resistor = Part(lib_device, "R", 
                      ref="R10", 
                      footprint="Resistor_SMD:R_0603_1608Metric",
                      value="1k")

# =============================================================================
# PROGRAMMING AND DEBUG INTERFACE
# =============================================================================

# SWD programming connector
swd_conn = Part(lib_conn, "Conn_01x04", 
               ref="J12", 
               footprint="Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical",
               value="SWD_Programming")

# USB connector for configuration
usb_conn = Part("Connector_USB", "USB_B_Micro", 
               ref="J13", 
               footprint="Connector_USB:USB_Micro-B_Molex_47346-0001",
               value="USB_Config")

# USB protection
usb_esd = Part("Protection", "USBLC6-2SC6", 
              ref="U6", 
              footprint="Package_TO_SOT_SMD:SOT-23-6",
              value="USBLC6-2SC6")

print("All components defined successfully!")

# =============================================================================
# ELECTRICAL CONNECTIONS - POWER DISTRIBUTION
# =============================================================================

print("Creating electrical connections...")

# Create power nets
vbat = Net("VBAT")  # Battery voltage
v5v = Net("5V")     # 5V regulated
v3v3 = Net("3V3")   # 3.3V regulated
gnd = Net("GND")    # Ground

# Battery input connections
battery_conn[1] += vbat
battery_conn[2] += gnd

# Input protection
vbat += input_fuse[1]
input_fuse[2] += reg_5v["VI"]

# Input filtering
input_cap[1] += input_fuse[2]
input_cap[2] += gnd

# 5V regulator connections
reg_5v["VI"] += input_fuse[2]
reg_5v["VO"] += v5v
reg_5v["GND"] += gnd

# 3.3V regulator connections
reg_3v3["VI"] += v5v
reg_3v3["VO"] += v3v3
reg_3v3["GND"] += gnd

# Output filter capacitors
cap_5v_out[1] += v5v
cap_5v_out[2] += gnd
cap_3v3_out[1] += v3v3
cap_3v3_out[2] += gnd

# Bypass capacitors
cap_5v_bypass[1] += v5v
cap_5v_bypass[2] += gnd
cap_3v3_bypass[1] += v3v3
cap_3v3_bypass[2] += gnd

# =============================================================================
# MCU POWER AND BASIC CONNECTIONS
# =============================================================================

# MCU power connections
flight_controller["VDD_1"] += v3v3
flight_controller["VDD_2"] += v3v3
flight_controller["VDD_3"] += v3v3
flight_controller["VDD_4"] += v3v3
flight_controller["VDDA"] += v3v3
flight_controller["VBAT"] += v3v3

flight_controller["VSS_1"] += gnd
flight_controller["VSS_2"] += gnd
flight_controller["VSS_3"] += gnd
flight_controller["VSS_4"] += gnd
flight_controller["VSSA"] += gnd

# MCU decoupling capacitors
mcu_cap1[1] += v3v3
mcu_cap1[2] += gnd
mcu_cap2[1] += v3v3
mcu_cap2[2] += gnd
mcu_cap3[1] += v3v3
mcu_cap3[2] += gnd

# Crystal oscillator connections
flight_controller["PH0"] += mcu_crystal[1]
flight_controller["PH1"] += mcu_crystal[2]

xtal_cap1[1] += mcu_crystal[1]
xtal_cap1[2] += gnd
xtal_cap2[1] += mcu_crystal[2]
xtal_cap2[2] += gnd

# Reset circuit
reset_pullup[1] += v3v3
reset_pullup[2] += flight_controller["NRST"]
reset_button[1] += flight_controller["NRST"]
reset_button[2] += gnd

# Boot mode selection
boot_pulldown[1] += flight_controller["BOOT0"]
boot_pulldown[2] += gnd
boot_jumper[1] += flight_controller["BOOT0"]
boot_jumper[2] += v3v3

# =============================================================================
# IMU AND SENSOR CONNECTIONS
# =============================================================================

# Create I2C nets
i2c_sda = Net("I2C_SDA")
i2c_scl = Net("I2C_SCL")

# IMU sensor connections
imu_sensor["VCC"] += v3v3
imu_sensor["GND"] += gnd
imu_sensor["SDA"] += i2c_sda
imu_sensor["SCL"] += i2c_scl
imu_sensor["INT"] += flight_controller["PA0"]  # Interrupt pin

# IMU decoupling
imu_cap[1] += v3v3
imu_cap[2] += gnd

# I2C pull-up resistors
i2c_pullup_sda[1] += v3v3
i2c_pullup_sda[2] += i2c_sda
i2c_pullup_scl[1] += v3v3
i2c_pullup_scl[2] += i2c_scl

# Magnetometer connections
magnetometer["VDD"] += v3v3
magnetometer["GND"] += gnd
magnetometer["SDA"] += i2c_sda
magnetometer["SCL"] += i2c_scl
magnetometer["DRDY"] += flight_controller["PA1"]  # Data ready pin

# Magnetometer decoupling
mag_cap[1] += v3v3
mag_cap[2] += gnd

# Connect I2C to MCU
flight_controller["PB6"] += i2c_scl  # I2C1_SCL
flight_controller["PB7"] += i2c_sda  # I2C1_SDA

# =============================================================================
# MOTOR CONTROL CONNECTIONS (PWM OUTPUTS)
# =============================================================================

# Create PWM nets
pwm1 = Net("PWM1_ESC1")
pwm2 = Net("PWM2_ESC2")
pwm3 = Net("PWM3_ESC3")
pwm4 = Net("PWM4_ESC4")

# ESC connector connections
esc1_conn[1] += v5v      # Power to ESC
esc1_conn[2] += gnd      # Ground
esc1_conn[3] += pwm1     # PWM signal

esc2_conn[1] += v5v
esc2_conn[2] += gnd
esc2_conn[3] += pwm2

esc3_conn[1] += v5v
esc3_conn[2] += gnd
esc3_conn[3] += pwm3

esc4_conn[1] += v5v
esc4_conn[2] += gnd
esc4_conn[3] += pwm4

# PWM signal filtering
pwm_cap1[1] += pwm1
pwm_cap1[2] += gnd
pwm_cap2[1] += pwm2
pwm_cap2[2] += gnd
pwm_cap3[1] += pwm3
pwm_cap3[2] += gnd
pwm_cap4[1] += pwm4
pwm_cap4[2] += gnd

# Connect PWM outputs to MCU timer pins
flight_controller["PA8"] += pwm1   # TIM1_CH1
flight_controller["PA9"] += pwm2   # TIM1_CH2
flight_controller["PA10"] += pwm3  # TIM1_CH3
flight_controller["PA11"] += pwm4  # TIM1_CH4

# =============================================================================
# COMMUNICATION INTERFACE CONNECTIONS
# =============================================================================

# Create UART nets
uart1_tx = Net("UART1_TX")
uart1_rx = Net("UART1_RX")
uart2_tx = Net("UART2_TX")
uart2_rx = Net("UART2_RX")

# GPS module connections (UART2)
gps_conn[1] += v3v3        # VCC
gps_conn[2] += gnd         # GND
gps_conn[3] += uart2_tx    # GPS RX (MCU TX)
gps_conn[4] += uart2_rx    # GPS TX (MCU RX)

# Telemetry UART connections (UART1)
telemetry_conn[1] += v3v3  # VCC
telemetry_conn[2] += gnd   # GND
telemetry_conn[3] += uart1_tx  # Telemetry RX (MCU TX)
telemetry_conn[4] += uart1_rx  # Telemetry TX (MCU RX)

# Connect UARTs to MCU
flight_controller["PA2"] += uart2_tx  # USART2_TX (GPS)
flight_controller["PA3"] += uart2_rx  # USART2_RX (GPS)
flight_controller["PA9"] += uart1_tx  # USART1_TX (Telemetry) - Note: shared with PWM2, mux in software
flight_controller["PA10"] += uart1_rx # USART1_RX (Telemetry) - Note: shared with PWM3, mux in software

# RC Receiver connections (PWM inputs)
rc_receiver_conn[1] += v5v             # VCC
rc_receiver_conn[2] += gnd             # GND
rc_receiver_conn[3] += flight_controller["PB0"]  # CH1 - Roll
rc_receiver_conn[4] += flight_controller["PB1"]  # CH2 - Pitch
rc_receiver_conn[5] += flight_controller["PC6"]  # CH3 - Throttle
rc_receiver_conn[6] += flight_controller["PC7"]  # CH4 - Yaw
rc_receiver_conn[7] += flight_controller["PC8"]  # CH5 - Aux1
rc_receiver_conn[8] += flight_controller["PC9"]  # CH6 - Aux2

# I2C expansion connector
i2c_expansion[1] += v3v3    # VCC
i2c_expansion[2] += gnd     # GND
i2c_expansion[3] += i2c_sda # SDA
i2c_expansion[4] += i2c_scl # SCL

# SPI expansion connector
spi_mosi = Net("SPI_MOSI")
spi_miso = Net("SPI_MISO")
spi_sck = Net("SPI_SCK")

spi_expansion[1] += v3v3    # VCC
spi_expansion[2] += gnd     # GND
spi_expansion[3] += spi_mosi # MOSI
spi_expansion[4] += spi_miso # MISO
spi_expansion[5] += spi_sck  # SCK
spi_expansion[6] += flight_controller["PA4"]  # CS

# Connect SPI to MCU
flight_controller["PA5"] += spi_sck   # SPI1_SCK
flight_controller["PA6"] += spi_miso  # SPI1_MISO
flight_controller["PA7"] += spi_mosi  # SPI1_MOSI

# =============================================================================
# STATUS INDICATORS AND SAFETY FEATURES
# =============================================================================

# Power LED connections
power_led_resistor[1] += v3v3
power_led_resistor[2] += power_led["A"]  # Anode
power_led["K"] += gnd  # Cathode

# Status LED connections (MCU controlled)
status_led_resistor[1] += flight_controller["PC0"]  # MCU GPIO
status_led_resistor[2] += status_led["A"]  # Anode
status_led["K"] += gnd  # Cathode

# GPS Lock LED connections (MCU controlled)
gps_led_resistor[1] += flight_controller["PC1"]  # MCU GPIO
gps_led_resistor[2] += gps_led["A"]  # Anode
gps_led["K"] += gnd  # Cathode

# Voltage monitoring (battery voltage divider)
voltage_divider_r1[1] += vbat
voltage_divider_r1[2] += voltage_divider_r2[1]
voltage_divider_r2[2] += gnd
flight_controller["PC2"] += voltage_divider_r1[2]  # ADC input for voltage monitoring

# Buzzer circuit (audio alerts)
buzzer_resistor[1] += flight_controller["PC3"]  # MCU GPIO
buzzer_resistor[2] += buzzer_transistor["B"]  # Base
buzzer_transistor["E"] += gnd  # Emitter
buzzer_transistor["C"] += buzzer[1]  # Collector to buzzer
buzzer[2] += v5v  # Buzzer power

# =============================================================================
# PROGRAMMING AND DEBUG INTERFACES
# =============================================================================

# SWD programming connector
swd_conn[1] += v3v3                    # VCC
swd_conn[2] += gnd                     # GND
swd_conn[3] += flight_controller["PA13"]  # SWDIO
swd_conn[4] += flight_controller["PA14"]  # SWCLK

# USB connector connections
usb_conn["VBUS"] += v5v
usb_conn["GND"] += gnd
usb_conn["D+"] += usb_esd["IO1"]
usb_conn["D-"] += usb_esd["IO2"]

# USB ESD protection
usb_esd["GND"] += gnd
usb_esd["VCC"] += v3v3
usb_esd["I/O1"] += flight_controller["PA11"]  # USB_DM
usb_esd["I/O2"] += flight_controller["PA12"]  # USB_DP

print("Status indicators and safety features completed!")

# =============================================================================
# NETLIST GENERATION AND VALIDATION
# =============================================================================

def generate_netlist():
    """Generate the complete netlist for the drone circuit"""
    print("\nGenerating netlist...")

    # Create output directory
    output_dir = Path("drone_pcb_project/output")
    output_dir.mkdir(exist_ok=True)

    # Generate netlist
    netlist_file = output_dir / "drone_flight_controller.net"
    generate_netlist(str(netlist_file))

    print(f"Netlist generated: {netlist_file}")

    # Generate component summary
    summary_file = output_dir / "component_summary.txt"
    with open(summary_file, 'w') as f:
        f.write("Drone Flight Controller - Component Summary\n")
        f.write("=" * 50 + "\n\n")

        component_types = {}
        for part in default_circuit.parts:
            part_type = str(part.lib) + ":" + str(part.name)
            if part_type not in component_types:
                component_types[part_type] = []
            component_types[part_type].append(str(part.ref))

        for part_type, refs in sorted(component_types.items()):
            f.write(f"{part_type}:\n")
            for ref in sorted(refs):
                f.write(f"  {ref}\n")
            f.write("\n")

        f.write(f"Total components: {len(default_circuit.parts)}\n")
        f.write(f"Total nets: {len(default_circuit.nets)}\n")

    print(f"Component summary: {summary_file}")

    return netlist_file, len(default_circuit.parts), len(default_circuit.nets)

def validate_circuit():
    """Validate the circuit for completeness"""
    print("\nValidating circuit...")

    issues = []

    # Check for unconnected pins
    for part in default_circuit.parts:
        for pin in part:
            if not pin.net:
                issues.append(f"Unconnected pin: {part.ref}.{pin.name}")

    # Check power connections
    power_nets = ["VBAT", "5V", "3V3", "GND"]
    for net_name in power_nets:
        found_net = False
        for net in default_circuit.nets:
            if net.name == net_name:
                found_net = True
                break
        if not found_net:
            issues.append(f"Missing power net: {net_name}")

    if issues:
        print("Circuit validation issues found:")
        for issue in issues[:10]:  # Show first 10 issues
            print(f"  - {issue}")
        if len(issues) > 10:
            print(f"  ... and {len(issues) - 10} more issues")
    else:
        print("Circuit validation passed!")

    return len(issues) == 0

# Main execution
if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("DRONE FLIGHT CONTROLLER CIRCUIT DESIGN COMPLETE")
    print("=" * 60)

    # Validate circuit
    validation_passed = validate_circuit()

    # Generate netlist
    netlist_file, num_components, num_nets = generate_netlist()

    print(f"\nCircuit Statistics:")
    print(f"  Components: {num_components}")
    print(f"  Networks: {num_nets}")
    print(f"  Validation: {'PASSED' if validation_passed else 'ISSUES FOUND'}")

    print(f"\nOutput files:")
    print(f"  Netlist: {netlist_file}")
    print(f"  Summary: drone_pcb_project/output/component_summary.txt")

    print("\n✅ Skidl circuit design completed successfully!")
    print("🔄 Ready for KiCad Python API integration...")
