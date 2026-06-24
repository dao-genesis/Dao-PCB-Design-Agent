#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
嘉立创 .eprj 完整解析工具
深度分析嘉立创EDA项目文件的所有设计数据
"""

import sqlite3
import base64
import gzip
import json
import ast
from pathlib import Path
from datetime import datetime

class EPRJCompleteParser:
    def __init__(self, db_path):
        self.db_path = Path(db_path)
        self.conn = None
        self.output_dir = Path("analysis_output")
        self.output_dir.mkdir(exist_ok=True)
    
    def connect(self):
        """连接到SQLite数据库"""
        try:
            self.conn = sqlite3.connect(self.db_path)
            return True
        except Exception as e:
            print(f"连接数据库失败: {e}")
            return False
    
    def close(self):
        """关闭数据库连接"""
        if self.conn:
            self.conn.close()
    
    def decode_and_parse_data(self, base64_data):
        """解码并解析设计数据"""
        try:
            # 移除 "base64" 前缀
            if base64_data.startswith('base64'):
                base64_data = base64_data[6:]
            
            # Base64解码
            decoded_data = base64.b64decode(base64_data)
            
            # gzip解压缩
            decompressed_data = gzip.decompress(decoded_data)
            
            # 解析为文本
            text_data = decompressed_data.decode('utf-8')
            
            # 尝试解析为Python数据结构
            lines = text_data.strip().split('\n')
            parsed_objects = []
            
            for line in lines:
                if line.strip():
                    try:
                        # 尝试解析为Python列表/字典
                        obj = ast.literal_eval(line)
                        parsed_objects.append(obj)
                    except:
                        # 如果解析失败，保存原始文本
                        parsed_objects.append(line)
            
            return {
                "success": True,
                "raw_text": text_data,
                "parsed_objects": parsed_objects,
                "size_info": {
                    "base64_size": len(base64_data),
                    "decoded_size": len(decoded_data),
                    "decompressed_size": len(decompressed_data)
                }
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "raw_data": base64_data[:200] + "..." if len(base64_data) > 200 else base64_data
            }
    
    def analyze_schematic_data(self, parsed_data):
        """分析原理图数据"""
        if not parsed_data["success"]:
            return {"error": parsed_data["error"]}
        
        analysis = {
            "document_type": None,
            "version": None,
            "components": [],
            "connections": [],
            "attributes": [],
            "fonts": [],
            "other_elements": []
        }
        
        for obj in parsed_data["parsed_objects"]:
            if isinstance(obj, list) and len(obj) > 0:
                cmd_type = obj[0]
                
                if cmd_type == "DOCTYPE":
                    analysis["document_type"] = obj[1] if len(obj) > 1 else None
                    analysis["version"] = obj[2] if len(obj) > 2 else None
                
                elif cmd_type == "HEAD":
                    analysis["head_info"] = obj[1] if len(obj) > 1 else None
                
                elif cmd_type == "COMPONENT":
                    analysis["components"].append({
                        "id": obj[1] if len(obj) > 1 else None,
                        "type": obj[2] if len(obj) > 2 else None,
                        "position": (obj[3], obj[4]) if len(obj) > 4 else None,
                        "rotation": obj[5] if len(obj) > 5 else None,
                        "properties": obj[7] if len(obj) > 7 else {}
                    })
                
                elif cmd_type == "FONTSTYLE":
                    analysis["fonts"].append({
                        "id": obj[1] if len(obj) > 1 else None,
                        "properties": obj[2:] if len(obj) > 2 else []
                    })
                
                elif cmd_type == "ATTR":
                    analysis["attributes"].append({
                        "id": obj[1] if len(obj) > 1 else None,
                        "parent": obj[2] if len(obj) > 2 else None,
                        "properties": obj[3:] if len(obj) > 3 else []
                    })
                
                elif cmd_type in ["WIRE", "NET", "CONNECTION"]:
                    analysis["connections"].append({
                        "type": cmd_type,
                        "data": obj[1:] if len(obj) > 1 else []
                    })
                
                else:
                    analysis["other_elements"].append({
                        "type": cmd_type,
                        "data": obj[1:] if len(obj) > 1 else []
                    })
        
        return analysis
    
    def analyze_pcb_data(self, parsed_data):
        """分析PCB数据"""
        if not parsed_data["success"]:
            return {"error": parsed_data["error"]}
        
        analysis = {
            "document_type": None,
            "version": None,
            "layers": [],
            "components": [],
            "tracks": [],
            "vias": [],
            "other_elements": []
        }
        
        for obj in parsed_data["parsed_objects"]:
            if isinstance(obj, list) and len(obj) > 0:
                cmd_type = obj[0]
                
                if cmd_type == "DOCTYPE":
                    analysis["document_type"] = obj[1] if len(obj) > 1 else None
                    analysis["version"] = obj[2] if len(obj) > 2 else None
                
                elif cmd_type in ["LAYER", "LAYERS"]:
                    analysis["layers"].append({
                        "type": cmd_type,
                        "data": obj[1:] if len(obj) > 1 else []
                    })
                
                elif cmd_type in ["COMPONENT", "FOOTPRINT"]:
                    analysis["components"].append({
                        "type": cmd_type,
                        "data": obj[1:] if len(obj) > 1 else []
                    })
                
                elif cmd_type in ["TRACK", "TRACE"]:
                    analysis["tracks"].append({
                        "type": cmd_type,
                        "data": obj[1:] if len(obj) > 1 else []
                    })
                
                elif cmd_type in ["VIA", "HOLE"]:
                    analysis["vias"].append({
                        "type": cmd_type,
                        "data": obj[1:] if len(obj) > 1 else []
                    })
                
                else:
                    analysis["other_elements"].append({
                        "type": cmd_type,
                        "data": obj[1:] if len(obj) > 1 else []
                    })
        
        return analysis
    
    def analyze_component_data(self):
        """分析组件库数据"""
        if not self.conn:
            return []
        
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT uuid, title, display_title, description, 
                       docType, dataStr, created_at
                FROM components
                WHERE dataStr IS NOT NULL AND dataStr != ''
            """)
            
            components = []
            for row in cursor.fetchall():
                component = {
                    "uuid": row[0],
                    "title": row[1],
                    "display_title": row[2],
                    "description": row[3],
                    "docType": row[4],
                    "created_at": row[6]
                }
                
                # 解析组件数据
                if row[5]:  # dataStr
                    parsed_data = self.decode_and_parse_data(row[5])
                    if parsed_data["success"]:
                        component["design_data"] = self.analyze_schematic_data(parsed_data)
                        
                        # 保存解析后的数据
                        output_file = self.output_dir / f"component_{component['title']}.json"
                        with open(output_file, 'w', encoding='utf-8') as f:
                            json.dump({
                                "component_info": component,
                                "raw_parsed_data": parsed_data["parsed_objects"]
                            }, f, indent=2, ensure_ascii=False)
                    else:
                        component["parse_error"] = parsed_data["error"]
                
                components.append(component)
            
            return components
            
        except Exception as e:
            print(f"分析组件数据失败: {e}")
            return []
    
    def generate_complete_report(self):
        """生成完整的分析报告"""
        if not self.connect():
            return {"error": "无法连接到数据库"}
        
        try:
            print("🔍 开始完整分析...")
            
            # 1. 基本项目信息
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM projects")
            project_data = cursor.fetchone()
            
            # 2. 分析文档数据
            cursor.execute("""
                SELECT uuid, title, display_title, docType, dataStr, created_at 
                FROM documents WHERE dataStr IS NOT NULL AND dataStr != ''
            """)
            
            documents_analysis = []
            for row in cursor.fetchall():
                print(f"📄 分析文档: {row[2]} (类型: {row[3]})")
                
                doc_info = {
                    "uuid": row[0],
                    "title": row[1],
                    "display_title": row[2],
                    "docType": row[3],
                    "created_at": row[5]
                }
                
                # 解析设计数据
                parsed_data = self.decode_and_parse_data(row[4])
                
                if parsed_data["success"]:
                    if row[3] == 1:  # 原理图
                        doc_info["analysis"] = self.analyze_schematic_data(parsed_data)
                        doc_info["design_type"] = "原理图"
                    elif row[3] == 3:  # PCB
                        doc_info["analysis"] = self.analyze_pcb_data(parsed_data)
                        doc_info["design_type"] = "PCB布局"
                    else:
                        doc_info["analysis"] = {"note": "未知文档类型"}
                        doc_info["design_type"] = f"类型{row[3]}"
                    
                    # 保存详细数据
                    detail_file = self.output_dir / f"{doc_info['title']}_详细数据.json"
                    with open(detail_file, 'w', encoding='utf-8') as f:
                        json.dump({
                            "document_info": doc_info,
                            "raw_parsed_objects": parsed_data["parsed_objects"],
                            "raw_text": parsed_data["raw_text"]
                        }, f, indent=2, ensure_ascii=False)
                    
                    doc_info["detail_file"] = str(detail_file)
                    
                else:
                    doc_info["error"] = parsed_data["error"]
                
                documents_analysis.append(doc_info)
            
            # 3. 分析组件库
            print("🔧 分析组件库...")
            components_analysis = self.analyze_component_data()
            
            # 4. 生成总报告
            complete_report = {
                "analysis_time": datetime.now().isoformat(),
                "database_file": str(self.db_path),
                "project_summary": {
                    "name": "嘉立创例子",
                    "created_at": "2025-08-16 11:40:02",
                    "updated_at": "2025-08-16 19:41:45"
                },
                "documents": documents_analysis,
                "components": components_analysis,
                "analysis_statistics": {
                    "total_documents": len(documents_analysis),
                    "total_components": len(components_analysis),
                    "schematic_count": len([d for d in documents_analysis if d.get("docType") == 1]),
                    "pcb_count": len([d for d in documents_analysis if d.get("docType") == 3])
                }
            }
            
            # 保存总报告
            report_file = self.output_dir / "完整分析报告.json"
            with open(report_file, 'w', encoding='utf-8') as f:
                json.dump(complete_report, f, indent=2, ensure_ascii=False)
            
            print(f"📋 完整报告已保存到: {report_file}")
            
            return complete_report
            
        except Exception as e:
            return {"error": f"生成报告时出错: {e}"}
        finally:
            self.close()
    
    def print_summary(self, report):
        """打印分析摘要"""
        if "error" in report:
            print(f"❌ 错误: {report['error']}")
            return
        
        print("\n" + "="*80)
        print("🎯 嘉立创项目完整分析结果")
        print("="*80)
        
        print(f"\n📂 项目名称: {report['project_summary']['name']}")
        print(f"📅 创建时间: {report['project_summary']['created_at']}")
        print(f"🔄 更新时间: {report['project_summary']['updated_at']}")
        
        stats = report['analysis_statistics']
        print(f"\n📊 统计信息:")
        print(f"   📄 总文档数: {stats['total_documents']}")
        print(f"   🔧 总组件数: {stats['total_components']}")
        print(f"   📋 原理图数: {stats['schematic_count']}")
        print(f"   🖥️  PCB数: {stats['pcb_count']}")
        
        print(f"\n📄 文档详情:")
        for i, doc in enumerate(report['documents'], 1):
            print(f"   {i}. {doc['display_title']} ({doc['design_type']})")
            
            if 'analysis' in doc and 'error' not in doc['analysis']:
                analysis = doc['analysis']
                
                if doc['docType'] == 1:  # 原理图
                    print(f"      🔹 版本: {analysis.get('document_type', 'Unknown')} {analysis.get('version', '')}")
                    print(f"      🔹 组件数: {len(analysis.get('components', []))}")
                    print(f"      🔹 连接数: {len(analysis.get('connections', []))}")
                    print(f"      🔹 属性数: {len(analysis.get('attributes', []))}")
                    
                elif doc['docType'] == 3:  # PCB
                    print(f"      🔹 版本: {analysis.get('document_type', 'Unknown')} {analysis.get('version', '')}")
                    print(f"      🔹 层数: {len(analysis.get('layers', []))}")
                    print(f"      🔹 组件数: {len(analysis.get('components', []))}")
                    print(f"      🔹 走线数: {len(analysis.get('tracks', []))}")
            
            if 'detail_file' in doc:
                print(f"      📁 详细数据: {doc['detail_file']}")
        
        print(f"\n🔧 组件库详情:")
        for i, comp in enumerate(report['components'], 1):
            print(f"   {i}. {comp['display_title']}")
            if 'design_data' in comp:
                design = comp['design_data']
                if 'error' not in design:
                    print(f"      🔹 组件元素: {len(design.get('components', []))}")
                    print(f"      🔹 字体样式: {len(design.get('fonts', []))}")
        
        print(f"\n✅ 分析完成！所有详细数据已保存到 '{self.output_dir}' 目录")

def main():
    """主函数"""
    print("🚀 嘉立创 .eprj 完整解析工具启动")
    print("="*60)
    
    parser = EPRJCompleteParser("嘉立创例子.eprj")
    report = parser.generate_complete_report()
    parser.print_summary(report)

if __name__ == "__main__":
    main()