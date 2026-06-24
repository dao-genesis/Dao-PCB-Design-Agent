#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
嘉立创 .eprj SQLite 数据库分析工具
解析嘉立创EDA项目文件的SQLite数据库结构
"""

import sqlite3
import json
import pandas as pd
from pathlib import Path

class EPRJSQLiteAnalyzer:
    def __init__(self, db_path):
        self.db_path = Path(db_path)
        self.conn = None
    
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
    
    def get_tables(self):
        """获取所有表名"""
        if not self.conn:
            return []
        
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [row[0] for row in cursor.fetchall()]
            return tables
        except Exception as e:
            print(f"获取表名失败: {e}")
            return []
    
    def get_table_schema(self, table_name):
        """获取表结构"""
        if not self.conn:
            return None
        
        try:
            cursor = self.conn.cursor()
            cursor.execute(f"PRAGMA table_info({table_name});")
            columns = cursor.fetchall()
            
            schema = []
            for col in columns:
                schema.append({
                    "column_id": col[0],
                    "name": col[1],
                    "type": col[2],
                    "not_null": bool(col[3]),
                    "default_value": col[4],
                    "primary_key": bool(col[5])
                })
            
            return schema
        except Exception as e:
            print(f"获取表结构失败 {table_name}: {e}")
            return None
    
    def get_table_data(self, table_name, limit=10):
        """获取表数据（限制条数）"""
        if not self.conn:
            return None
        
        try:
            cursor = self.conn.cursor()
            cursor.execute(f"SELECT COUNT(*) FROM {table_name};")
            total_rows = cursor.fetchone()[0]
            
            cursor.execute(f"SELECT * FROM {table_name} LIMIT {limit};")
            rows = cursor.fetchall()
            
            # 获取列名
            cursor.execute(f"PRAGMA table_info({table_name});")
            columns = [col[1] for col in cursor.fetchall()]
            
            return {
                "total_rows": total_rows,
                "sample_rows": rows,
                "columns": columns
            }
        except Exception as e:
            print(f"获取表数据失败 {table_name}: {e}")
            return None
    
    def analyze_database(self):
        """完整分析数据库"""
        if not self.connect():
            return {"error": "无法连接到数据库"}
        
        try:
            analysis = {
                "database_file": str(self.db_path),
                "file_size": self.db_path.stat().st_size,
                "tables": {}
            }
            
            # 获取所有表
            tables = self.get_tables()
            analysis["table_count"] = len(tables)
            analysis["table_names"] = tables
            
            # 分析每个表
            for table_name in tables:
                print(f"正在分析表: {table_name}")
                
                table_info = {
                    "schema": self.get_table_schema(table_name),
                    "data": self.get_table_data(table_name, limit=5)
                }
                
                analysis["tables"][table_name] = table_info
            
            return analysis
            
        except Exception as e:
            return {"error": f"分析过程中出错: {e}"}
        finally:
            self.close()
    
    def export_table_to_csv(self, table_name, output_dir="output"):
        """导出表数据到CSV文件"""
        if not self.conn:
            if not self.connect():
                return False
        
        try:
            # 创建输出目录
            output_path = Path(output_dir)
            output_path.mkdir(exist_ok=True)
            
            # 读取全部数据
            df = pd.read_sql_query(f"SELECT * FROM {table_name}", self.conn)
            
            # 保存为CSV
            csv_file = output_path / f"{table_name}.csv"
            df.to_csv(csv_file, index=False, encoding='utf-8-sig')
            
            print(f"表 {table_name} 已导出到: {csv_file}")
            return True
            
        except Exception as e:
            print(f"导出表 {table_name} 失败: {e}")
            return False
    
    def search_text_in_tables(self, search_text):
        """在所有表中搜索包含特定文本的记录"""
        if not self.conn:
            if not self.connect():
                return {}
        
        results = {}
        tables = self.get_tables()
        
        for table_name in tables:
            try:
                # 获取表结构
                schema = self.get_table_schema(table_name)
                text_columns = [col["name"] for col in schema if "text" in col["type"].lower() or "char" in col["type"].lower()]
                
                if not text_columns:
                    continue
                
                # 在文本列中搜索
                for column in text_columns:
                    cursor = self.conn.cursor()
                    query = f"SELECT * FROM {table_name} WHERE {column} LIKE ? LIMIT 10"
                    cursor.execute(query, (f"%{search_text}%",))
                    rows = cursor.fetchall()
                    
                    if rows:
                        if table_name not in results:
                            results[table_name] = {}
                        results[table_name][column] = rows
                        
            except Exception as e:
                print(f"搜索表 {table_name} 时出错: {e}")
        
        return results

def main():
    # 分析嘉立创SQLite数据库
    db_file = "嘉立创例子.eprj"
    
    print(f"正在分析 SQLite 数据库: {db_file}")
    print("=" * 60)
    
    analyzer = EPRJSQLiteAnalyzer(db_file)
    result = analyzer.analyze_database()
    
    if "error" in result:
        print(f"错误: {result['error']}")
        return
    
    # 打印基本信息
    print(f"数据库文件: {result['database_file']}")
    print(f"文件大小: {result['file_size']:,} 字节")
    print(f"表数量: {result['table_count']}")
    print(f"表名称: {', '.join(result['table_names'])}")
    print()
    
    # 打印每个表的详细信息
    for table_name, table_info in result["tables"].items():
        print(f"表: {table_name}")
        print("-" * 40)
        
        # 表结构
        if table_info["schema"]:
            print("字段结构:")
            for col in table_info["schema"]:
                pk_mark = " (主键)" if col["primary_key"] else ""
                null_mark = " (非空)" if col["not_null"] else ""
                print(f"  - {col['name']}: {col['type']}{pk_mark}{null_mark}")
        
        # 数据预览
        if table_info["data"]:
            data = table_info["data"]
            print(f"\n数据预览 (总行数: {data['total_rows']}):")
            if data["sample_rows"]:
                # 显示前几行数据
                for i, row in enumerate(data["sample_rows"][:3]):
                    print(f"  行{i+1}: {dict(zip(data['columns'], row))}")
            else:
                print("  (无数据)")
        
        print("\n")
    
    # 搜索常见的CAD相关关键词
    print("=" * 60)
    print("搜索CAD相关内容:")
    
    keywords = ["component", "part", "resistor", "capacitor", "led", "pin", "net", "wire"]
    for keyword in keywords:
        search_results = analyzer.search_text_in_tables(keyword)
        if search_results:
            print(f"\n找到包含 '{keyword}' 的记录:")
            for table, columns in search_results.items():
                for column, rows in columns.items():
                    print(f"  表 {table}.{column}: 找到 {len(rows)} 条记录")

if __name__ == "__main__":
    main()
















