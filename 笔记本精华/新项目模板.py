#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
SKiDL PCB设计项目模板
====================

这是一个基础的SKiDL项目模板，包含了常用的电路设计模式和最佳实践。
复制这个文件作为新项目的起点。

作者: AI PCB设计助手
创建时间: 2025
许可证: MIT
"""

from skidl import *
import sys
import os

# 添加项目根目录到Python路径，用于导入自定义库
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import config
    config.setup_kicad_environment()
except ImportError as e:
    print(f"⚠️  警告: 无法导入配置文件: {e}")
    print("请检查config.py文件是否存在")

# =============================================================================
# 项目信息配置
# =============================================================================

PROJECT_NAME = "新项目"  # 修改为您的项目名称
PROJECT_VERSION = "1.0.0"
AUTHOR = "您的名字"
DESCRIPTION = "项目描述"

# =============================================================================
# 电路参数配置
# =============================================================================

# 电源参数
VCC_VOLTAGE = 5.0  # 电源电压 (V)
VCC_CURRENT = 1.0  # 最大电流 (A)

# LED参数
LED_CURRENT = 20e-3  # LED电流 (A)
LED_VOLTAGE_DROP = 2.1  # LED压降 (V)

# 计算限流电阻
if VCC_VOLTAGE > LED_VOLTAGE_DROP:
    RESISTOR_VALUE = (VCC_VOLTAGE - LED_VOLTAGE_DROP) / LED_CURRENT
    print(f"💡 计算得出限流电阻值: {RESISTOR_VALUE:.0f}Ω")
else:
    print("⚠️  警告: 电源电压低于LED压降!")
    RESISTOR_VALUE = 330  # 默认值

# =============================================================================
# 网络定义 (电气连接)
# =============================================================================

def define_nets():
    """定义项目中使用的所有网络"""
    
    # 电源网络
    vcc = Net('VCC')
    gnd = Net('GND')
    
    # 信号网络
    led_control = Net('LED_CTRL')
    
    return {
        'vcc': vcc,
        'gnd': gnd, 
        'led_control': led_control
    }

# =============================================================================
# 元件定义
# =============================================================================

def define_components():
    """定义项目中使用的所有电子元件"""
    
    components = {}
    
    try:
        # 微控制器
        components['mcu'] = Part('MCU_Module', 'Arduino_Nano_v3.x', 
                               ref='U1',
                               footprint='Module:Arduino_Nano')
        
        # LED
        components['led1'] = Part('Device', 'LED',
                                ref='D1', 
                                footprint='LED_THT:LED_D5.0mm')
        
        # 限流电阻
        components['r1'] = Part('Device', 'R',
                              value=f'{RESISTOR_VALUE:.0f}',
                              ref='R1',
                              footprint='Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal')
        
        # 电源连接器
        components['power_conn'] = Part('Connector', 'Conn_01x02_Male',
                                      ref='J1',
                                      footprint='Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical')
        
        print(f"✅ 成功定义了 {len(components)} 个元件")
        
    except Exception as e:
        print(f"❌ 元件定义错误: {e}")
        print("请检查KiCad符号库路径配置")
        
    return components

# =============================================================================
# 电路连接
# =============================================================================

def connect_circuit(nets, components):
    """连接电路中的所有元件"""
    
    try:
        # 获取网络和元件
        vcc = nets['vcc']
        gnd = nets['gnd']
        led_control = nets['led_control']
        
        mcu = components['mcu']
        led1 = components['led1'] 
        r1 = components['r1']
        power_conn = components['power_conn']
        
        # 电源连接
        power_conn[1] += vcc  # 正极
        power_conn[2] += gnd  # 负极
        
        # 微控制器电源
        mcu['VIN'] += vcc
        mcu['GND'] += gnd
        
        # LED控制电路
        mcu['D13'] += led_control  # 使用D13引脚控制LED
        led_control += r1[1]       # 信号通过限流电阻
        r1[2] += led1['A']         # 电阻连接LED阳极
        led1['K'] += gnd           # LED阴极接地
        
        print("✅ 电路连接完成")
        
    except Exception as e:
        print(f"❌ 电路连接错误: {e}")
        raise

# =============================================================================
# 设计规则检查 (DRC)
# =============================================================================

def run_design_checks():
    """运行设计规则检查"""
    
    print("\n🔍 开始设计规则检查...")
    
    # 检查未连接的引脚
    unconnected_pins = []
    for part in default_circuit.parts:
        for pin in part.pins:
            if not pin.net:
                unconnected_pins.append(f"{part.ref}.{pin.name}")
    
    if unconnected_pins:
        print(f"⚠️  发现 {len(unconnected_pins)} 个未连接的引脚:")
        for pin in unconnected_pins[:10]:  # 只显示前10个
            print(f"   - {pin}")
        if len(unconnected_pins) > 10:
            print(f"   ... 还有 {len(unconnected_pins) - 10} 个")
    else:
        print("✅ 所有引脚都已正确连接")
    
    # 检查网络连接数
    net_stats = {}
    for net in default_circuit.nets:
        if len(net.pins) > 0:
            net_stats[net.name] = len(net.pins)
    
    print(f"\n📊 网络统计:")
    for net_name, pin_count in sorted(net_stats.items()):
        print(f"   {net_name}: {pin_count} 个连接")

# =============================================================================
# 输出生成
# =============================================================================

def generate_outputs(project_name):
    """生成项目输出文件"""
    
    # 确保输出目录存在
    output_dir = os.path.join('output', project_name)
    os.makedirs(output_dir, exist_ok=True)
    
    base_filename = os.path.join(output_dir, project_name.replace(' ', '_').lower())
    
    try:
        # 生成网表文件
        netlist_file = f"{base_filename}.net"
        generate_netlist(filename=netlist_file)
        print(f"✅ 网表文件: {netlist_file}")
        
        # 生成ERC报告
        erc_file = f"{base_filename}.erc"
        ERC(filename=erc_file)
        print(f"✅ ERC报告: {erc_file}")
        
        # 生成BOM清单
        bom_file = f"{base_filename}_bom.txt"
        generate_bom(filename=bom_file)
        print(f"✅ BOM清单: {bom_file}")
        
        return {
            'netlist': netlist_file,
            'erc': erc_file,
            'bom': bom_file
        }
        
    except Exception as e:
        print(f"❌ 输出文件生成失败: {e}")
        return None

def generate_bom(filename):
    """生成物料清单 (Bill of Materials)"""
    
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(f"# {PROJECT_NAME} - 物料清单 (BOM)\n")
        f.write(f"# 版本: {PROJECT_VERSION}\n")
        f.write(f"# 作者: {AUTHOR}\n")
        f.write(f"# 生成时间: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        
        f.write("位号\t元件值\t封装\t说明\n")
        f.write("-" * 50 + "\n")
        
        for part in default_circuit.parts:
            ref = part.ref or "?"
            value = getattr(part, 'value', part.name)
            footprint = getattr(part, 'footprint', 'Unknown')
            description = f"{part.lib}.{part.name}"
            
            f.write(f"{ref}\t{value}\t{footprint}\t{description}\n")

# =============================================================================
# 主函数
# =============================================================================

def main():
    """主函数 - 执行完整的设计流程"""
    
    print("=" * 60)
    print(f"🚀 开始 {PROJECT_NAME} 项目设计")
    print(f"📝 描述: {DESCRIPTION}")
    print(f"👤 作者: {AUTHOR}")
    print(f"📅 版本: {PROJECT_VERSION}")
    print("=" * 60)
    
    try:
        # 1. 定义网络
        print("\n1️⃣ 定义电路网络...")
        nets = define_nets()
        
        # 2. 定义元件
        print("\n2️⃣ 定义电路元件...")
        components = define_components()
        
        if not components:
            print("❌ 元件定义失败，无法继续")
            return False
        
        # 3. 连接电路
        print("\n3️⃣ 连接电路...")
        connect_circuit(nets, components)
        
        # 4. 设计规则检查
        print("\n4️⃣ 设计规则检查...")
        run_design_checks()
        
        # 5. 生成输出文件
        print("\n5️⃣ 生成输出文件...")
        outputs = generate_outputs(PROJECT_NAME)
        
        if outputs:
            print(f"\n🎉 {PROJECT_NAME} 设计完成!")
            print(f"📁 输出文件位于: output/{PROJECT_NAME.replace(' ', '_').lower()}/")
            print("\n📋 后续步骤:")
            print("1. 将网表文件导入KiCad进行PCB布局")
            print("2. 检查ERC报告中的警告和错误")
            print("3. 根据BOM清单采购元件")
            return True
        else:
            print("❌ 输出文件生成失败")
            return False
            
    except Exception as e:
        print(f"❌ 设计过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
        return False

# =============================================================================
# 脚本入口点
# =============================================================================

if __name__ == '__main__':
    # 设置默认电路
    default_circuit.name = PROJECT_NAME
    
    # 执行设计
    success = main()
    
    if success:
        print(f"\n✨ 项目 '{PROJECT_NAME}' 设计成功完成!")
    else:
        print(f"\n💥 项目 '{PROJECT_NAME}' 设计失败!")
        sys.exit(1)
















