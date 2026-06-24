@echo off
title �?- PCB���
echo 正在打开 PCB��� 的所有资源目�?..
echo.
echo === 台式机资�?(D:\) ===
if exist "D:\电路设计嘉立�? (start "" explorer "D:\电路设计嘉立�?) else (echo [跳过] 嘉立创EDA: D:\电路设计嘉立�?不存�?
if exist "D:\ad\ad_project" (start "" explorer "D:\ad\ad_project") else (echo [跳过] AD工程(�?: D:\ad\ad_project 不存�?
if exist "D:\keil代码" (start "" explorer "D:\keil代码") else (echo [跳过] Keil代码: D:\keil代码 不存�?
if exist "D:\电路代码" (start "" explorer "D:\电路代码") else (echo [跳过] 电路代码: D:\电路代码 不存�?
if exist "D:\proteus" (start "" explorer "D:\proteus") else (echo [跳过] Proteus: D:\proteus 不存�?
echo.
echo === 笔记本资�?(Y:\ Z:\) ===
if exist "Z:\道\AI-PCB设计" (start "" explorer "Z:\道\AI-PCB设计") else (echo [跳过] AI代码化PCB(�?: Z:\道\AI-PCB设计 不存�?
if exist "Z:\adpcbexample" (start "" explorer "Z:\adpcbexample") else (echo [跳过] AD示例(�?: Z:\adpcbexample 不存�?
if exist "Y:\嘉立创EDA" (start "" explorer "Y:\嘉立创EDA") else (echo [跳过] 嘉立创EDA(�?: Y:\嘉立创EDA 不存�?
if exist "Y:\keil_projext" (start "" explorer "Y:\keil_projext") else (echo [跳过] Keil项目(�?: Y:\keil_projext 不存�?
echo.
start "" explorer "E:\道\PCB���"
echo 全部打开完成。按任意键关�?..
pause >nul
