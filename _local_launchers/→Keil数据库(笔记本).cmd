@echo off
if exist "Y:\KEIL_DATA" (start "" explorer "Y:\KEIL_DATA") else (echo Y:\KEIL_DATA 不存在，笔记本可能未连接 & pause)
if exist "Y:\keil_projext" (start "" explorer "Y:\keil_projext") else (echo Y:\keil_projext 不存在，笔记本可能未连接 & pause)
