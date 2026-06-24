#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
调试嘉立创 .eprj 数据库结构
"""

import sqlite3
import base64
import gzip

def debug_documents_table():
    """调试documents表的数据结构"""
    conn = sqlite3.connect("嘉立创例子.eprj")
    cursor = conn.cursor()
    
    # 查看documents表结构
    cursor.execute("PRAGMA table_info(documents);")
    columns = cursor.fetchall()
    print("Documents表结构:")
    for col in columns:
        print(f"  {col[1]}: {col[2]}")
    
    print("\n" + "="*60)
    
    # 查看实际数据
    cursor.execute("SELECT title, display_title, docType, length(dataStr), substr(dataStr, 1, 200) FROM documents;")
    rows = cursor.fetchall()
    
    for i, row in enumerate(rows):
        print(f"\n文档 {i+1}:")
        print(f"  标题: {row[0]} / {row[1]}")
        print(f"  类型: {row[2]}")
        print(f"  数据长度: {row[3]}")
        print(f"  数据开头: {row[4]}")
        
        # 获取完整的dataStr
        cursor.execute("SELECT dataStr FROM documents WHERE title = ?", (row[0],))
        full_data = cursor.fetchone()[0]
        
        print(f"  完整数据长度: {len(full_data)}")
        
        # 尝试解码
        if full_data.startswith('base64'):
            base64_data = full_data[6:]  # 移除'base64'前缀
            try:
                decoded = base64.b64decode(base64_data)
                print(f"  解码后长度: {len(decoded)}")
                
                # 尝试gzip解压
                try:
                    decompressed = gzip.decompress(decoded)
                    print(f"  解压后长度: {len(decompressed)}")
                    
                    # 尝试作为文本显示
                    try:
                        text = decompressed.decode('utf-8')
                        print(f"  文本内容预览: {text[:200]}...")
                    except:
                        print("  不是UTF-8文本数据")
                        
                except Exception as e:
                    print(f"  gzip解压失败: {e}")
                    # 尝试直接作为文本
                    try:
                        text = decoded.decode('utf-8')
                        print(f"  直接解码文本: {text[:200]}...")
                    except:
                        print("  不是文本数据，可能是二进制")
                        
            except Exception as e:
                print(f"  Base64解码失败: {e}")
    
    conn.close()

if __name__ == "__main__":
    debug_documents_table()
















