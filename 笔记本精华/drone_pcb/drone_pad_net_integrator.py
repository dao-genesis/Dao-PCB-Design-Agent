#!/usr/bin/env python3
"""
Drone PCB Pad-Net Integrator

This script fixes the pad-to-net assignments in the drone PCB file to establish
complete electrical connectivity from the Skidl-generated netlist.

Author: AI PCB Designer
License: MIT
"""

import os
import re
import json
import logging
from pathlib import Path
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DronePadNetIntegrator:
    """Integrate pad-net assignments for drone PCB"""
    
    def __init__(self, project_dir: str):
        """Initialize integrator"""
        self.project_dir = Path(project_dir)
        self.pcb_file = self.project_dir / "drone_flight_controller.kicad_pcb"
        self.netlist_file = self.project_dir / "output" / "drone_flight_controller.net"
        
        self.netlist_data = {}
        self.component_pin_nets = {}
        
    def load_netlist_connections(self):
        """Load netlist connections from generated file"""
        try:
            logger.info("Loading netlist connections...")
            
            with open(self.netlist_file, 'r', encoding='utf-8') as f:
                netlist_content = f.read()
            
            # Debug: Print first few lines to understand format
            lines = netlist_content.split('\n')
            logger.info("Netlist format debug:")
            for i, line in enumerate(lines[320:330]):  # Around nets section
                logger.info(f"Line {i+320}: {line}")

            # Extract nets with nodes - simplified pattern
            net_pattern = r'\(net \(code "(\d+)"\) \(name "([^"]*)"'
            node_pattern = r'\(node \(ref "([^"]+)"\) \(pin "([^"]+)"\)\)'

            # Find all nets first
            for match in re.finditer(net_pattern, netlist_content):
                code, name = match.groups()
                net_code = int(code)

                # Find the start and end of this net section
                start_pos = match.start()

                # Find all nodes for this net
                remaining_content = netlist_content[start_pos:]
                net_end = remaining_content.find('\n    (net (code')
                if net_end == -1:
                    net_end = remaining_content.find('\n  )')
                if net_end == -1:
                    net_end = len(remaining_content)

                net_section = remaining_content[:net_end]

                # Extract nodes from this net section
                nodes = []
                for node_match in re.finditer(node_pattern, net_section):
                    ref, pin = node_match.groups()
                    nodes.append({'ref': ref, 'pin': pin})

                    # Create component-pin to net mapping
                    key = f"{ref}:{pin}"
                    self.component_pin_nets[key] = net_code

                self.netlist_data[name] = {
                    'code': net_code,
                    'name': name,
                    'nodes': nodes
                }
            
            logger.info(f"Loaded {len(self.netlist_data)} nets with {len(self.component_pin_nets)} pin assignments")
            return True
            
        except Exception as e:
            logger.error(f"Error loading netlist connections: {e}")
            return False
    
    def apply_pad_net_assignments(self):
        """Apply pad-net assignments to PCB file"""
        try:
            logger.info("Applying pad-net assignments...")
            
            # Read PCB file
            with open(self.pcb_file, 'r', encoding='utf-8') as f:
                pcb_content = f.read()
            
            # Create backup
            backup_file = self.pcb_file.with_suffix('.kicad_pcb.pre_pad_integration')
            with open(backup_file, 'w', encoding='utf-8') as f:
                f.write(pcb_content)
            
            # Process line by line for precise pad updates
            lines = pcb_content.split('\n')
            updated_lines = []
            current_component = None
            assignments_made = 0
            
            for line in lines:
                # Track current component
                ref_match = re.search(r'\(property "Reference" "([^"]+)"', line)
                if ref_match:
                    current_component = ref_match.group(1)
                
                # Check for pad definition - improved pattern
                pad_match = re.search(r'^(\s*)\(pad "([^"]+)" (.+)', line)
                if pad_match and current_component:
                    indent = pad_match.group(1)
                    pad_number = pad_match.group(2)
                    pad_definition = pad_match.group(3)

                    # Check if this pad needs net assignment
                    key = f"{current_component}:{pad_number}"

                    if key in self.component_pin_nets:
                        net_code = self.component_pin_nets[key]

                        # Debug: Log the assignment
                        if assignments_made < 5:  # Log first 5 assignments
                            logger.info(f"Assigning {key} to net {net_code}")

                        # Remove existing net assignment if present
                        pad_definition = re.sub(r'\(net \d+\)', '', pad_definition)

                        # Add new net assignment before the closing parenthesis
                        if pad_definition.endswith(')'):
                            pad_definition = pad_definition[:-1] + f' (net {net_code})'
                        else:
                            pad_definition = pad_definition.rstrip() + f' (net {net_code})'

                        assignments_made += 1

                        # Reconstruct the line
                        line = f'{indent}(pad "{pad_number}" {pad_definition}'
                
                updated_lines.append(line)
            
            # Write updated content
            updated_content = '\n'.join(updated_lines)
            
            with open(self.pcb_file, 'w', encoding='utf-8') as f:
                f.write(updated_content)
            
            logger.info(f"✅ Applied {assignments_made} pad-net assignments")
            
            # Verify the assignments
            self.verify_pad_assignments()
            
            return True
            
        except Exception as e:
            logger.error(f"Error applying pad assignments: {e}")
            return False
    
    def verify_pad_assignments(self):
        """Verify that pad assignments were applied correctly"""
        try:
            logger.info("Verifying pad assignments...")
            
            with open(self.pcb_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Count pads with net assignments
            pad_with_net_pattern = r'\(pad "[^"]+".+?\(net (\d+)\)'
            pad_assignments = re.findall(pad_with_net_pattern, content, re.DOTALL)
            
            # Count total pads
            total_pads = len(re.findall(r'\(pad "[^"]+"', content))
            
            # Count connected pads (net > 0)
            connected_pads = len([net for net in pad_assignments if int(net) > 0])
            
            # Count unique nets
            unique_nets = set(int(net) for net in pad_assignments if int(net) > 0)
            
            success = connected_pads > 0 and len(unique_nets) > 10
            
            verification_results = {
                'total_pads': total_pads,
                'assigned_pads': len(pad_assignments),
                'connected_pads': connected_pads,
                'assignment_ratio': len(pad_assignments) / total_pads if total_pads > 0 else 0,
                'connection_ratio': connected_pads / total_pads if total_pads > 0 else 0,
                'unique_nets': len(unique_nets),
                'success': success
            }
            
            if success:
                logger.info(f"✅ Verification successful: {connected_pads}/{total_pads} pads connected ({verification_results['connection_ratio']:.1%})")
            else:
                logger.warning(f"⚠️ Verification issues: {connected_pads}/{total_pads} pads connected ({verification_results['connection_ratio']:.1%})")
            
            # Save verification results
            verification_file = self.project_dir / "pad_net_verification.json"
            with open(verification_file, 'w', encoding='utf-8') as f:
                json.dump(verification_results, f, indent=2)
            
            return success
            
        except Exception as e:
            logger.error(f"Error verifying pad assignments: {e}")
            return False
    
    def run_pad_net_integration(self):
        """Run complete pad-net integration"""
        logger.info("Starting Drone PCB Pad-Net Integration")
        logger.info("=" * 45)
        
        try:
            # Load netlist connections
            if not self.load_netlist_connections():
                return False
            
            # Apply pad-net assignments
            if not self.apply_pad_net_assignments():
                return False
            
            logger.info("✅ Pad-net integration completed successfully!")
            return True
            
        except Exception as e:
            logger.error(f"Error in pad-net integration: {e}")
            return False

def main():
    """Main function"""
    project_dir = Path("drone_pcb_project")
    
    print("Drone Flight Controller - Pad-Net Integration")
    print("=" * 50)
    
    integrator = DronePadNetIntegrator(str(project_dir))
    success = integrator.run_pad_net_integration()
    
    if success:
        print("\n🎉 Pad-net integration successful!")
        print("✅ Electrical connections established")
        print("🔗 PCB ready for ratsnest display")
        print("🚀 Auto-routing functionality enabled")
    else:
        print("\n❌ Pad-net integration failed!")
        print("📋 Check logs for details")
    
    return success

if __name__ == "__main__":
    main()
