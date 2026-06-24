#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
嘉立创 .eprj 文件分析工具
尝试分析嘉立创EDA项目文件的结构
"""

import os
import struct
import json
from pathlib import Path

class EPRJAnalyzer:
    def __init__(self, file_path):
        self.file_path = Path(file_path)
        self.file_size = 0
        if self.file_path.exists():
            self.file_size = self.file_path.stat().st_size
    
    def analyze_file_header(self, num_bytes=512):
        """分析文件头部信息"""
        if not self.file_path.exists():
            return {"error": "文件不存在"}
        
        if self.file_size == 0:
            return {"error": "文件为空"}
        
        try:
            with open(self.file_path, 'rb') as f:
                header_bytes = f.read(min(num_bytes, self.file_size))
                
            # 分析文件头
            analysis = {
                "file_size": self.file_size,
                "header_bytes_count": len(header_bytes),
                "magic_number": None,
                "possible_format": None,
                "text_content": None,
                "hex_dump": header_bytes[:64].hex(' ', 2) if len(header_bytes) > 0 else "",
            }
            
            # 检查是否包含常见的文件格式标识
            if header_bytes.startswith(b'PK'):
                analysis["possible_format"] = "ZIP-based format"
                analysis["magic_number"] = "PK (ZIP)"
            elif header_bytes.startswith(b'\x7fELF'):
                analysis["possible_format"] = "ELF binary"
            elif header_bytes.startswith(b'MZ'):
                analysis["possible_format"] = "PE executable"
            elif header_bytes.startswith(b'\x89PNG'):
                analysis["possible_format"] = "PNG image"
            elif header_bytes.startswith(b'GIF8'):
                analysis["possible_format"] = "GIF image"
            elif header_bytes.startswith(b'\xff\xd8\xff'):
                analysis["possible_format"] = "JPEG image"
            elif header_bytes.startswith(b'<?xml'):
                analysis["possible_format"] = "XML document"
            elif header_bytes.startswith(b'{'):
                analysis["possible_format"] = "JSON document"
            
            # 尝试查找可能的文本内容
            try:
                # 寻找ASCII可打印字符串
                text_parts = []
                current_text = ""
                for byte in header_bytes:
                    if 32 <= byte <= 126:  # ASCII可打印字符
                        current_text += chr(byte)
                    else:
                        if len(current_text) >= 4:  # 至少4个字符的字符串
                            text_parts.append(current_text)
                        current_text = ""
                
                if len(current_text) >= 4:
                    text_parts.append(current_text)
                
                if text_parts:
                    analysis["text_content"] = text_parts[:10]  # 只显示前10个字符串
                    
            except Exception as e:
                analysis["text_analysis_error"] = str(e)
            
            return analysis
            
        except Exception as e:
            return {"error": f"读取文件时出错: {str(e)}"}
    
    def check_if_zip_based(self):
        """检查是否是基于ZIP的格式（很多CAD文件都是ZIP格式）"""
        try:
            import zipfile
            if zipfile.is_zipfile(self.file_path):
                with zipfile.ZipFile(self.file_path, 'r') as zip_ref:
                    file_list = zip_ref.namelist()
                    return {
                        "is_zip": True,
                        "files_count": len(file_list),
                        "file_list": file_list[:20]  # 只显示前20个文件
                    }
        except Exception as e:
            pass
        
        return {"is_zip": False}
    
    def analyze(self):
        """完整分析文件"""
        result = {
            "file_path": str(self.file_path),
            "exists": self.file_path.exists(),
        }
        
        if not self.file_path.exists():
            result["error"] = "文件不存在"
            return result
        
        # 基本文件信息
        result["file_info"] = {
            "size": self.file_size,
            "size_human": self._format_size(self.file_size)
        }
        
        # 文件头分析
        result["header_analysis"] = self.analyze_file_header()
        
        # ZIP格式检查
        result["zip_check"] = self.check_if_zip_based()
        
        return result
    
    def _format_size(self, size):
        """格式化文件大小"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"

def main():
    # 分析嘉立创文件
    eprj_file = "嘉立创例子.eprj"
    
    print(f"正在分析文件: {eprj_file}")
    print("=" * 50)
    
    analyzer = EPRJAnalyzer(eprj_file)
    result = analyzer.analyze()
    
    # 打印分析结果
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    # 提供建议
    print("\n" + "=" * 50)
    print("分析建议:")
    
    if result.get("file_info", {}).get("size", 0) == 0:
        print("- 文件为空，可能是一个新创建的项目文件")
    elif result.get("zip_check", {}).get("is_zip"):
        print("- 文件是ZIP格式，可能包含多个CAD相关文件")
        print("- 建议进一步解压查看内部结构")
    else:
        print("- 文件是二进制格式，需要专门的解析工具")
        print("- 建议使用嘉立创EDA客户端打开")

if __name__ == "__main__":
    main()
















