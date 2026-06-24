#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
嘉立创 .eprj 设计数据提取工具
解析和提取嘉立创EDA项目文件中的实际设计数据
"""

import sqlite3
import base64
import gzip
import json
import os
from pathlib import Path
from datetime import datetime

class EPRJDataExtractor:
    def __init__(self, db_path):
        self.db_path = Path(db_path)
        self.conn = None
        self.output_dir = Path("extracted_data")
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
    
    def decode_base64_data(self, base64_data):
        """解码Base64数据并尝试解压缩"""
        try:
            # 移除 "base64" 前缀
            if base64_data.startswith('base64'):
                base64_data = base64_data[6:]
            
            # Base64解码
            decoded_data = base64.b64decode(base64_data)
            
            # 尝试gzip解压缩
            try:
                decompressed_data = gzip.decompress(decoded_data)
                return {
                    "success": True,
                    "data": decompressed_data,
                    "type": "gzip_compressed",
                    "size_original": len(base64_data),
                    "size_decoded": len(decoded_data),
                    "size_decompressed": len(decompressed_data)
                }
            except:
                # 如果不是gzip压缩，返回原始解码数据
                return {
                    "success": True,
                    "data": decoded_data,
                    "type": "raw_binary",
                    "size_original": len(base64_data),
                    "size_decoded": len(decoded_data)
                }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    def extract_project_info(self):
        """提取项目基本信息"""
        if not self.conn:
            return None
        
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT uuid, name, content, created_at, updated_at, 
                       boards, pcb_count, default_sheet
                FROM projects
            """)
            
            project = cursor.fetchone()
            if project:
                return {
                    "uuid": project[0],
                    "name": project[1],
                    "content": project[2],
                    "created_at": project[3],
                    "updated_at": project[4],
                    "boards": project[5],
                    "pcb_count": project[6],
                    "default_sheet": project[7]
                }
            return None
        except Exception as e:
            print(f"提取项目信息失败: {e}")
            return None
    
    def extract_schematics(self):
        """提取原理图信息"""
        if not self.conn:
            return []
        
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT uuid, name, display_name, description, 
                       sheet_count, created_at, updated_at
                FROM schematics
            """)
            
            schematics = []
            for row in cursor.fetchall():
                schematics.append({
                    "uuid": row[0],
                    "name": row[1],
                    "display_name": row[2],
                    "description": row[3],
                    "sheet_count": row[4],
                    "created_at": row[5],
                    "updated_at": row[6]
                })
            
            return schematics
        except Exception as e:
            print(f"提取原理图信息失败: {e}")
            return []
    
    def extract_documents(self):
        """提取文档数据（原理图和PCB设计）"""
        if not self.conn:
            return []
        
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT uuid, title, display_title, description, 
                       docType, dataStr, sheet_id, created_at
                FROM documents
                WHERE dataStr IS NOT NULL AND dataStr != ''
            """)
            
            documents = []
            for i, row in enumerate(cursor.fetchall()):
                doc_info = {
                    "uuid": row[0],
                    "title": row[1],
                    "display_title": row[2],
                    "description": row[3],
                    "docType": row[4],
                    "sheet_id": row[5],
                    "created_at": row[6],
                    "base64_data_length": len(row[7]) if row[7] else 0
                }
                
                # 解码设计数据
                if row[7]:  # dataStr
                    print(f"正在解码文档 {doc_info['display_title']} 的设计数据...")
                    decoded_result = self.decode_base64_data(row[7])
                    
                    if decoded_result["success"]:
                        doc_info["decoded_info"] = decoded_result
                        
                        # 保存解码后的数据到文件
                        doc_type_name = "schematic" if doc_info["docType"] == 1 else "pcb" if doc_info["docType"] == 3 else f"doc_type_{doc_info['docType']}"
                        filename = f"{doc_info['title']}_{doc_type_name}.data"
                        file_path = self.output_dir / filename
                        
                        with open(file_path, 'wb') as f:
                            f.write(decoded_result["data"])
                        
                        doc_info["extracted_file"] = str(file_path)
                        
                        # 尝试解析为文本（如果是文本数据）
                        try:
                            text_data = decoded_result["data"].decode('utf-8')
                            if len(text_data) < 10000:  # 只显示较短的文本
                                doc_info["text_preview"] = text_data[:500] + "..." if len(text_data) > 500 else text_data
                        except:
                            pass
                    else:
                        doc_info["decode_error"] = decoded_result["error"]
                
                documents.append(doc_info)
            
            return documents
        except Exception as e:
            print(f"提取文档数据失败: {e}")
            return []
    
    def extract_components(self):
        """提取组件信息"""
        if not self.conn:
            return []
        
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT uuid, title, display_title, description, 
                       docType, created_at, updated_at
                FROM components
                WHERE dataStr IS NOT NULL AND dataStr != ''
            """)
            
            components = []
            for row in cursor.fetchall():
                components.append({
                    "uuid": row[0],
                    "title": row[1],
                    "display_title": row[2],
                    "description": row[3],
                    "docType": row[4],
                    "created_at": row[5],
                    "updated_at": row[6]
                })
            
            return components
        except Exception as e:
            print(f"提取组件信息失败: {e}")
            return []
    
    def extract_devices(self):
        """提取设备信息"""
        if not self.conn:
            return []
        
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT uuid, title, display_title, description, 
                       symbol_type, footprint_type, created_at
                FROM devices
            """)
            
            devices = []
            for row in cursor.fetchall():
                devices.append({
                    "uuid": row[0],
                    "title": row[1],
                    "display_title": row[2],
                    "description": row[3],
                    "symbol_type": row[4],
                    "footprint_type": row[5],
                    "created_at": row[6]
                })
            
            return devices
        except Exception as e:
            print(f"提取设备信息失败: {e}")
            return []
    
    def generate_report(self):
        """生成完整的项目分析报告"""
        if not self.connect():
            return {"error": "无法连接到数据库"}
        
        try:
            report = {
                "extraction_time": datetime.now().isoformat(),
                "database_file": str(self.db_path),
                "output_directory": str(self.output_dir),
                "project_info": self.extract_project_info(),
                "schematics": self.extract_schematics(),
                "documents": self.extract_documents(),
                "components": self.extract_components(),
                "devices": self.extract_devices()
            }
            
            # 保存报告到JSON文件
            report_file = self.output_dir / "extraction_report.json"
            with open(report_file, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            
            print(f"详细报告已保存到: {report_file}")
            
            return report
            
        except Exception as e:
            return {"error": f"生成报告时出错: {e}"}
        finally:
            self.close()

def main():
    """主函数"""
    print("嘉立创 .eprj 设计数据提取工具")
    print("=" * 60)
    
    # 提取数据
    extractor = EPRJDataExtractor("嘉立创例子.eprj")
    report = extractor.generate_report()
    
    if "error" in report:
        print(f"错误: {report['error']}")
        return
    
    # 显示提取摘要
    print("\n📋 项目信息摘要")
    print("-" * 40)
    if report["project_info"]:
        proj = report["project_info"]
        print(f"项目名称: {proj['name']}")
        print(f"创建时间: {proj['created_at']}")
        print(f"更新时间: {proj['updated_at']}")
        print(f"PCB数量: {proj['pcb_count']}")
        
        # 解析boards信息
        try:
            boards_data = json.loads(proj['boards'])
            print(f"电路板: {len(boards_data)} 个")
            for i, board in enumerate(boards_data):
                print(f"  Board {i+1}: {board.get('name', 'Unknown')}")
        except:
            pass
    
    print(f"\n📄 文档数量: {len(report['documents'])}")
    for doc in report['documents']:
        doc_type = "原理图" if doc['docType'] == 1 else "PCB" if doc['docType'] == 3 else f"类型{doc['docType']}"
        print(f"  - {doc['display_title']} ({doc_type})")
        if 'extracted_file' in doc:
            print(f"    已提取到: {doc['extracted_file']}")
        if 'decoded_info' in doc:
            info = doc['decoded_info']
            print(f"    数据大小: {info.get('size_decompressed', info.get('size_decoded', 0)):,} 字节")
    
    print(f"\n🔧 原理图数量: {len(report['schematics'])}")
    for sch in report['schematics']:
        print(f"  - {sch['display_name']} (工作表数: {sch['sheet_count']})")
    
    print(f"\n📦 组件数量: {len(report['components'])}")
    for comp in report['components']:
        print(f"  - {comp['display_title']}")
    
    print(f"\n🔌 设备数量: {len(report['devices'])}")
    for dev in report['devices']:
        print(f"  - {dev['display_title']}")
    
    print(f"\n✅ 提取完成！所有数据已保存到 '{extractor.output_dir}' 目录")

if __name__ == "__main__":
    main()
















