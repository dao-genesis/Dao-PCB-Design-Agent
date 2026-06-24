#!/usr/bin/env python3
"""
Drone PCB Netlist Generator

This script creates a comprehensive netlist for a drone flight controller PCB
without relying on external KiCad libraries, generating a complete netlist
that can be used with KiCad Python API.

Author: AI PCB Designer
License: MIT
"""

import os
import json
from pathlib import Path
from datetime import datetime

class DroneNetlistGenerator:
    """Generate comprehensive drone flight controller netlist"""
    
    def __init__(self):
        """Initialize netlist generator"""
        self.components = {}
        self.nets = {}
        self.connections = []
        
    def define_drone_components(self):
        """Define all drone components with specifications"""
        
        # Power Management Components
        self.components.update({
            "J1": {"name": "Battery_Input", "footprint": "Connector_JST:JST_XH_B2B-XH-A_1x02_P2.50mm_Vertical", "value": "Battery", "pins": ["1", "2"]},
            "F1": {"name": "Input_Fuse", "footprint": "Fuse:Fuse_1206_3216Metric", "value": "5A", "pins": ["1", "2"]},
            "U1": {"name": "AMS1117-5.0", "footprint": "Package_TO_SOT_SMD:SOT-223-3_TabPin2", "value": "5V_Reg", "pins": ["1", "2", "3"]},
            "U2": {"name": "AMS1117-3.3", "footprint": "Package_TO_SOT_SMD:SOT-223-3_TabPin2", "value": "3V3_Reg", "pins": ["1", "2", "3"]},
            
            # Flight Controller MCU
            "U3": {"name": "STM32F405RGTx", "footprint": "Package_QFP:LQFP-64_10x10mm_P0.5mm", "value": "Flight_Controller", 
                   "pins": [str(i) for i in range(1, 65)]},
            
            # IMU Sensor
            "U4": {"name": "MPU-6050", "footprint": "Sensor_Motion:InvenSense_QFN-24_4x4mm_P0.5mm", "value": "IMU", 
                   "pins": [str(i) for i in range(1, 25)]},
            
            # Magnetometer
            "U5": {"name": "HMC5883L", "footprint": "Package_LGA:LGA-16_3x3mm_P0.5mm", "value": "Magnetometer", 
                   "pins": [str(i) for i in range(1, 17)]},
            
            # Motor ESC Connectors
            "J3": {"name": "ESC1_Motor", "footprint": "Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical", "value": "ESC1", "pins": ["1", "2", "3"]},
            "J4": {"name": "ESC2_Motor", "footprint": "Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical", "value": "ESC2", "pins": ["1", "2", "3"]},
            "J5": {"name": "ESC3_Motor", "footprint": "Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical", "value": "ESC3", "pins": ["1", "2", "3"]},
            "J6": {"name": "ESC4_Motor", "footprint": "Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical", "value": "ESC4", "pins": ["1", "2", "3"]},
            
            # Communication Interfaces
            "J7": {"name": "GPS_Module", "footprint": "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical", "value": "GPS", "pins": ["1", "2", "3", "4"]},
            "J8": {"name": "Telemetry_UART", "footprint": "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical", "value": "Telemetry", "pins": ["1", "2", "3", "4"]},
            "J9": {"name": "RC_Receiver", "footprint": "Connector_PinHeader_2.54mm:PinHeader_1x08_P2.54mm_Vertical", "value": "RC_RX", "pins": [str(i) for i in range(1, 9)]},
            "J10": {"name": "I2C_Expansion", "footprint": "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical", "value": "I2C_EXP", "pins": ["1", "2", "3", "4"]},
            "J11": {"name": "SPI_Expansion", "footprint": "Connector_PinHeader_2.54mm:PinHeader_1x06_P2.54mm_Vertical", "value": "SPI_EXP", "pins": [str(i) for i in range(1, 7)]},
            
            # Status LEDs
            "D1": {"name": "Power_LED", "footprint": "LED_SMD:LED_0603_1608Metric", "value": "Power", "pins": ["1", "2"]},
            "D2": {"name": "Status_LED", "footprint": "LED_SMD:LED_0603_1608Metric", "value": "Status", "pins": ["1", "2"]},
            "D3": {"name": "GPS_LED", "footprint": "LED_SMD:LED_0603_1608Metric", "value": "GPS_Lock", "pins": ["1", "2"]},
            
            # Resistors
            "R1": {"name": "Resistor", "footprint": "Resistor_SMD:R_0603_1608Metric", "value": "330", "pins": ["1", "2"]},
            "R2": {"name": "Resistor", "footprint": "Resistor_SMD:R_0603_1608Metric", "value": "330", "pins": ["1", "2"]},
            "R3": {"name": "Resistor", "footprint": "Resistor_SMD:R_0603_1608Metric", "value": "330", "pins": ["1", "2"]},
            "R4": {"name": "Resistor", "footprint": "Resistor_SMD:R_0603_1608Metric", "value": "4.7k", "pins": ["1", "2"]},
            "R5": {"name": "Resistor", "footprint": "Resistor_SMD:R_0603_1608Metric", "value": "4.7k", "pins": ["1", "2"]},
            "R6": {"name": "Resistor", "footprint": "Resistor_SMD:R_0603_1608Metric", "value": "10k", "pins": ["1", "2"]},
            "R7": {"name": "Resistor", "footprint": "Resistor_SMD:R_0603_1608Metric", "value": "10k", "pins": ["1", "2"]},
            "R8": {"name": "Resistor", "footprint": "Resistor_SMD:R_0603_1608Metric", "value": "10k", "pins": ["1", "2"]},
            "R9": {"name": "Resistor", "footprint": "Resistor_SMD:R_0603_1608Metric", "value": "3.3k", "pins": ["1", "2"]},
            
            # Capacitors
            "C1": {"name": "CP", "footprint": "Capacitor_THT:CP_Radial_D8.0mm_P3.50mm", "value": "1000uF", "pins": ["1", "2"]},
            "C2": {"name": "Capacitor", "footprint": "Capacitor_SMD:C_1206_3216Metric", "value": "100uF", "pins": ["1", "2"]},
            "C3": {"name": "Capacitor", "footprint": "Capacitor_SMD:C_1206_3216Metric", "value": "100uF", "pins": ["1", "2"]},
            "C4": {"name": "Capacitor", "footprint": "Capacitor_SMD:C_0603_1608Metric", "value": "100nF", "pins": ["1", "2"]},
            "C5": {"name": "Capacitor", "footprint": "Capacitor_SMD:C_0603_1608Metric", "value": "100nF", "pins": ["1", "2"]},
            "C6": {"name": "Capacitor", "footprint": "Capacitor_SMD:C_0603_1608Metric", "value": "100nF", "pins": ["1", "2"]},
            "C7": {"name": "Capacitor", "footprint": "Capacitor_SMD:C_0603_1608Metric", "value": "100nF", "pins": ["1", "2"]},
            "C8": {"name": "Capacitor", "footprint": "Capacitor_SMD:C_0603_1608Metric", "value": "100nF", "pins": ["1", "2"]},
            "C9": {"name": "Capacitor", "footprint": "Capacitor_SMD:C_0603_1608Metric", "value": "22pF", "pins": ["1", "2"]},
            "C10": {"name": "Capacitor", "footprint": "Capacitor_SMD:C_0603_1608Metric", "value": "22pF", "pins": ["1", "2"]},
            
            # Crystal
            "Y1": {"name": "Crystal", "footprint": "Crystal:Crystal_HC49-4H_Vertical", "value": "8MHz", "pins": ["1", "2"]},
            
            # Programming Interface
            "J12": {"name": "SWD_Programming", "footprint": "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical", "value": "SWD", "pins": ["1", "2", "3", "4"]},
            
            # Safety Features
            "BZ1": {"name": "Buzzer", "footprint": "Buzzer_Beeper:Buzzer_12x9.5RM7.6", "value": "Buzzer", "pins": ["1", "2"]},
            "Q1": {"name": "2N3904", "footprint": "Package_TO_SOT_THT:TO-92_Inline", "value": "NPN", "pins": ["1", "2", "3"]},
            "SW1": {"name": "SW_Push", "footprint": "Button_Switch_THT:SW_PUSH_6mm", "value": "Reset", "pins": ["1", "2"]}
        })
        
        print(f"Defined {len(self.components)} drone components")
        
    def create_electrical_connections(self):
        """Create all electrical connections for the drone"""

        # Power distribution connections (component, pin, net_name)
        power_connections = [
            # Battery input
            ("J1", "1", "VBAT"),
            ("J1", "2", "GND"),

            # Fuse connections
            ("F1", "1", "VBAT"),
            ("F1", "2", "VBAT_FUSED"),

            # 5V regulator
            ("U1", "1", "VBAT_FUSED"),  # Input
            ("U1", "2", "GND"),         # Ground
            ("U1", "3", "5V"),          # Output

            # 3.3V regulator
            ("U2", "1", "5V"),          # Input
            ("U2", "2", "GND"),         # Ground
            ("U2", "3", "3V3"),         # Output

            # Filter capacitors
            ("C1", "1", "VBAT"),
            ("C1", "2", "GND"),
            ("C2", "1", "5V"),
            ("C2", "2", "GND"),
            ("C3", "1", "3V3"),
            ("C3", "2", "GND"),
        ]
        
        # MCU power connections
        mcu_power_connections = [
            # MCU power pins
            ("U3", "11", "3V3"),  # VDD_1
            ("U3", "19", "3V3"),  # VDD_2
            ("U3", "28", "3V3"),  # VDD_3
            ("U3", "50", "3V3"),  # VDD_4
            ("U3", "13", "3V3"),  # VDDA
            ("U3", "12", "GND"),  # VSS_1
            ("U3", "18", "GND"),  # VSS_2
            ("U3", "27", "GND"),  # VSS_3
            ("U3", "49", "GND"),  # VSS_4
            ("U3", "14", "GND"),  # VSSA

            # MCU decoupling capacitors
            ("C4", "1", "3V3"),
            ("C4", "2", "GND"),
            ("C5", "1", "3V3"),
            ("C5", "2", "GND"),

            # Crystal connections
            ("U3", "5", "XTAL1"),    # PH0/OSC_IN
            ("U3", "6", "XTAL2"),    # PH1/OSC_OUT
            ("Y1", "1", "XTAL1"),
            ("Y1", "2", "XTAL2"),
            ("C9", "1", "XTAL1"),
            ("C9", "2", "GND"),
            ("C10", "1", "XTAL2"),
            ("C10", "2", "GND"),
        ]
        
        # IMU and sensor connections
        sensor_connections = [
            # IMU power and I2C
            ("U4", "13", "3V3"),      # VCC
            ("U4", "18", "GND"),      # GND
            ("U4", "23", "I2C_SDA"),  # SDA
            ("U4", "24", "I2C_SCL"),  # SCL
            ("U4", "12", "IMU_INT"),  # INT signal
            ("U3", "23", "IMU_INT"),  # MCU PA0

            # I2C pull-ups
            ("R4", "1", "3V3"),
            ("R4", "2", "I2C_SDA"),
            ("R5", "1", "3V3"),
            ("R5", "2", "I2C_SCL"),

            # Connect I2C to MCU
            ("U3", "58", "I2C_SCL"),  # PB6/I2C1_SCL
            ("U3", "59", "I2C_SDA"),  # PB7/I2C1_SDA

            # IMU decoupling
            ("C6", "1", "3V3"),
            ("C6", "2", "GND"),

            # Magnetometer
            ("U5", "13", "3V3"),      # VDD
            ("U5", "16", "GND"),      # GND
            ("U5", "14", "I2C_SDA"),  # SDA
            ("U5", "15", "I2C_SCL"),  # SCL
        ]
        
        # Motor control connections
        motor_connections = [
            # ESC1 connections
            ("J3", "1", "5V"),        # ESC power
            ("J3", "2", "GND"),       # ESC ground
            ("J3", "3", "PWM1"),      # PWM signal
            ("U3", "29", "PWM1"),     # MCU PA8/TIM1_CH1

            # ESC2 connections
            ("J4", "1", "5V"),
            ("J4", "2", "GND"),
            ("J4", "3", "PWM2"),
            ("U3", "30", "PWM2"),     # MCU PA9/TIM1_CH2

            # ESC3 connections
            ("J5", "1", "5V"),
            ("J5", "2", "GND"),
            ("J5", "3", "PWM3"),
            ("U3", "31", "PWM3"),     # MCU PA10/TIM1_CH3

            # ESC4 connections
            ("J6", "1", "5V"),
            ("J6", "2", "GND"),
            ("J6", "3", "PWM4"),
            ("U3", "32", "PWM4"),     # MCU PA11/TIM1_CH4
        ]
        
        # Communication interface connections
        comm_connections = [
            # GPS module (UART2)
            ("J7", "1", "3V3"),       # VCC
            ("J7", "2", "GND"),       # GND
            ("J7", "3", "GPS_TX"),    # GPS TX
            ("J7", "4", "GPS_RX"),    # GPS RX
            ("U3", "17", "GPS_RX"),   # PA2/UART2_TX to GPS RX
            ("U3", "18", "GPS_TX"),   # PA3/UART2_RX to GPS TX

            # Telemetry (UART3)
            ("J8", "1", "3V3"),       # VCC
            ("J8", "2", "GND"),       # GND
            ("J8", "3", "TELEM_TX"),  # Telemetry TX
            ("J8", "4", "TELEM_RX"),  # Telemetry RX
            ("U3", "33", "TELEM_TX"), # PB10/UART3_TX
            ("U3", "34", "TELEM_RX"), # PB11/UART3_RX

            # RC Receiver
            ("J9", "1", "5V"),        # VCC
            ("J9", "2", "GND"),       # GND
            ("J9", "3", "RC_CH1"),    # Channel 1
            ("J9", "4", "RC_CH2"),    # Channel 2
            ("J9", "5", "RC_CH3"),    # Channel 3
            ("J9", "6", "RC_CH4"),    # Channel 4
            ("J9", "7", "RC_CH5"),    # Channel 5
            ("J9", "8", "RC_CH6"),    # Channel 6
            ("U3", "35", "RC_CH1"),   # PB0
            ("U3", "36", "RC_CH2"),   # PB1
            ("U3", "37", "RC_CH3"),   # PC6
            ("U3", "38", "RC_CH4"),   # PC7
            ("U3", "39", "RC_CH5"),   # PC8
            ("U3", "40", "RC_CH6"),   # PC9

            # I2C expansion
            ("J10", "1", "3V3"),      # VCC
            ("J10", "2", "GND"),      # GND
            ("J10", "3", "I2C_SDA"),  # SDA
            ("J10", "4", "I2C_SCL"),  # SCL

            # SPI expansion
            ("J11", "1", "3V3"),      # VCC
            ("J11", "2", "GND"),      # GND
            ("J11", "3", "SPI_SCK"),  # SCK
            ("J11", "4", "SPI_MISO"), # MISO
            ("J11", "5", "SPI_MOSI"), # MOSI
            ("J11", "6", "SPI_CS"),   # CS
            ("U3", "21", "SPI_SCK"),  # PA5/SPI1_SCK
            ("U3", "22", "SPI_MISO"), # PA6/SPI1_MISO
            ("U3", "23", "SPI_MOSI"), # PA7/SPI1_MOSI
            ("U3", "20", "SPI_CS"),   # PA4/SPI1_CS
        ]
        
        # Status indicator connections
        status_connections = [
            # Power LED (always on)
            ("R1", "1", "3V3"),
            ("R1", "2", "PWR_LED_A"), # LED anode signal
            ("D1", "1", "PWR_LED_A"), # Anode
            ("D1", "2", "GND"),       # Cathode

            # Status LED (MCU controlled)
            ("U3", "15", "STATUS_LED_CTRL"), # PC0
            ("R2", "1", "STATUS_LED_CTRL"),
            ("R2", "2", "STATUS_LED_A"),     # LED anode signal
            ("D2", "1", "STATUS_LED_A"),     # Anode
            ("D2", "2", "GND"),              # Cathode

            # GPS LED (MCU controlled)
            ("U3", "16", "GPS_LED_CTRL"),    # PC1
            ("R3", "1", "GPS_LED_CTRL"),
            ("R3", "2", "GPS_LED_A"),        # LED anode signal
            ("D3", "1", "GPS_LED_A"),        # Anode
            ("D3", "2", "GND"),              # Cathode

            # Voltage monitoring
            ("R8", "1", "VBAT"),
            ("R8", "2", "VBAT_SENSE"),
            ("R9", "1", "VBAT_SENSE"),
            ("R9", "2", "GND"),
            ("U3", "24", "VBAT_SENSE"),      # PC2/ADC for voltage monitoring

            # Reset circuit
            ("R6", "1", "3V3"),
            ("R6", "2", "MCU_RESET"),
            ("U3", "7", "MCU_RESET"),        # NRST
            ("SW1", "1", "MCU_RESET"),       # Reset button
            ("SW1", "2", "GND"),

            # Boot selection
            ("U3", "60", "MCU_BOOT0"),       # BOOT0
            ("R7", "1", "MCU_BOOT0"),
            ("R7", "2", "GND"),

            # Programming interface
            ("J12", "1", "3V3"),             # VCC
            ("J12", "2", "GND"),             # GND
            ("J12", "3", "SWD_DIO"),         # SWDIO
            ("J12", "4", "SWD_CLK"),         # SWCLK
            ("U3", "46", "SWD_DIO"),         # PA13/SWDIO
            ("U3", "49", "SWD_CLK"),         # PA14/SWCLK
        ]
        
        # Combine all connections
        all_connections = (power_connections + mcu_power_connections + 
                          sensor_connections + motor_connections + 
                          comm_connections + status_connections)
        
        self.connections = all_connections
        print(f"Created {len(all_connections)} electrical connections")
        
    def generate_nets_from_connections(self):
        """Generate nets from electrical connections"""
        
        # Create nets from connections
        net_counter = 1
        
        for connection in self.connections:
            if len(connection) == 3:
                # Direct net connection: (component, pin, net_name)
                comp, pin, net_name = connection
                
                if net_name not in self.nets:
                    self.nets[net_name] = {
                        'code': net_counter,
                        'name': net_name,
                        'nodes': []
                    }
                    net_counter += 1
                
                self.nets[net_name]['nodes'].append({
                    'component': comp,
                    'pin': pin
                })
                
            elif len(connection) == 4:
                # Component-to-component connection: (comp1, pin1, comp2, pin2)
                comp1, pin1, comp2, pin2 = connection
                
                # Create a net name
                net_name = f"Net_{comp1}_{pin1}_to_{comp2}_{pin2}"
                
                if net_name not in self.nets:
                    self.nets[net_name] = {
                        'code': net_counter,
                        'name': net_name,
                        'nodes': []
                    }
                    net_counter += 1
                
                self.nets[net_name]['nodes'].extend([
                    {'component': comp1, 'pin': pin1},
                    {'component': comp2, 'pin': pin2}
                ])
        
        print(f"Generated {len(self.nets)} electrical networks")
        
    def generate_kicad_netlist(self, output_file):
        """Generate KiCad-compatible netlist"""
        
        netlist_lines = [
            "(export (version D)",
            "  (design",
            "    (source \"drone_flight_controller.sch\")",
            "    (date \"" + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "\")",
            "    (tool \"Skidl Drone Generator\")",
            "    (sheet (number 1) (name \"/\") (tstamps \"/\"))",
            "      (title_block",
            "        (title \"Drone Flight Controller\")",
            "        (company \"AI PCB Designer\")",
            "        (rev \"1.0\")",
            "        (date \"" + datetime.now().strftime("%Y-%m-%d") + "\")",
            "        (source \"drone_circuit_skidl.py\")",
            "        (comment (number 1) (value \"Comprehensive Drone PCB\"))",
            "        (comment (number 2) (value \"Generated by Skidl\"))",
            "        (comment (number 3) (value \"Ready for KiCad API\"))",
            "        (comment (number 4) (value \"\"))",
            "      )",
            "    )",
            "  )",
            "  (components"
        ]
        
        # Add components
        for ref, comp_data in self.components.items():
            netlist_lines.extend([
                f"    (comp (ref \"{ref}\")",
                f"      (value \"{comp_data['value']}\")",
                f"      (footprint \"{comp_data['footprint']}\")",
                f"      (libsource (lib \"Device\") (part \"{comp_data['name']}\") (description \"Drone component\"))",
                f"      (sheetpath (names \"/\") (tstamps \"/\"))",
                f"      (tstamp {ref.lower()}-tstamp)",
                "    )"
            ])
        
        netlist_lines.append("  )")
        
        # Add nets
        netlist_lines.append("  (nets")
        
        # Add unconnected net
        netlist_lines.extend([
            "    (net (code \"0\") (name \"\"))",
        ])
        
        # Add all nets with nodes
        for net_name, net_data in self.nets.items():
            netlist_lines.append(f"    (net (code \"{net_data['code']}\") (name \"{net_name}\")")
            
            for node in net_data['nodes']:
                netlist_lines.append(f"      (node (ref \"{node['component']}\") (pin \"{node['pin']}\"))")
            
            netlist_lines.append("    )")
        
        netlist_lines.extend([
            "  )",
            ")"
        ])
        
        # Write netlist file
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(netlist_lines))
        
        print(f"Generated KiCad netlist: {output_file}")
        
    def run_netlist_generation(self):
        """Run complete netlist generation"""
        print("Drone Flight Controller - Netlist Generation")
        print("=" * 50)
        
        # Create output directory
        output_dir = Path("drone_pcb_project/output")
        output_dir.mkdir(exist_ok=True)
        
        # Define components
        self.define_drone_components()
        
        # Create connections
        self.create_electrical_connections()
        
        # Generate nets
        self.generate_nets_from_connections()
        
        # Generate netlist
        netlist_file = output_dir / "drone_flight_controller.net"
        self.generate_kicad_netlist(netlist_file)
        
        # Save component and connection summary
        summary = {
            'timestamp': datetime.now().isoformat(),
            'components': len(self.components),
            'nets': len(self.nets),
            'connections': len(self.connections),
            'component_list': list(self.components.keys()),
            'net_list': list(self.nets.keys())
        }
        
        summary_file = output_dir / "drone_netlist_summary.json"
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2)
        
        print(f"\nNetlist generation completed!")
        print(f"Components: {len(self.components)}")
        print(f"Networks: {len(self.nets)}")
        print(f"Connections: {len(self.connections)}")
        print(f"Output: {netlist_file}")
        
        return True

def main():
    """Main function"""
    generator = DroneNetlistGenerator()
    success = generator.run_netlist_generation()
    
    if success:
        print("\n✅ Drone netlist generation successful!")
        print("🔄 Ready for KiCad Python API integration...")
    else:
        print("\n❌ Netlist generation failed!")
    
    return success

if __name__ == "__main__":
    main()
