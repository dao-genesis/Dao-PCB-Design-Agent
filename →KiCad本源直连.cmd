@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title kicad_origin · 五脉同体 · 直连本源

echo.
echo ╔════════════════════════════════════════════════════════════════╗
echo ║  kicad_origin · 万法归宗 · 直连本源                            ║
echo ║  无为而无不为 · 一份道, 五通道, KiCad 全境贯通                  ║
echo ╚════════════════════════════════════════════════════════════════╝
echo.

if "%~1"=="" goto :menu

D:\KICAD\bin\python.exe -m kicad_origin %*
goto :end

:menu
echo  [0] 状态自检 (status)
echo  [1] 通道探活 (connect)
echo  [2] 启用 IPC server (改 config, 不重启)
echo  [3] 启用 IPC + 重启 KiCad (生效 IPC)
echo  [4] 关闭 IPC server
echo  [5] 全闭环: 仓库物流车 (build + ERC + 出图 + 注入)
echo  [6] 全闭环 + GUI 打开 + 截图
echo  [7] 仅打开仓库物流车工程
echo  [8] 仅截图当前 KiCad 全部窗口
echo  [9] 解析任意 KiCad 文件
echo.
set /p choice=请选择 [0-9, q 退出]:

if "%choice%"=="0" D:\KICAD\bin\python.exe -m kicad_origin status
if "%choice%"=="1" D:\KICAD\bin\python.exe -m kicad_origin connect
if "%choice%"=="2" D:\KICAD\bin\python.exe -m kicad_origin enable-ipc
if "%choice%"=="3" D:\KICAD\bin\python.exe -m kicad_origin enable-ipc --restart
if "%choice%"=="4" D:\KICAD\bin\python.exe -m kicad_origin disable-ipc
if "%choice%"=="5" D:\KICAD\bin\python.exe -m kicad_origin do all warehouse_logistics_vehicle --no-open --no-snap
if "%choice%"=="6" D:\KICAD\bin\python.exe -m kicad_origin do all warehouse_logistics_vehicle
if "%choice%"=="7" D:\KICAD\bin\python.exe -m kicad_origin do open "%CD%\实战\仓库车间物流车控制系统设计\04_工程源文件\KiCad工程\warehouse_logistics_vehicle.kicad_pro" --wait 4
if "%choice%"=="8" D:\KICAD\bin\python.exe -m kicad_origin do snap "%CD%\实战\仓库车间物流车控制系统设计\00_一览\kicad_screenshots\manual"
if "%choice%"=="9" (
    set /p _f=请粘贴文件路径:
    D:\KICAD\bin\python.exe -m kicad_origin parse "%_f%"
)
if /I "%choice%"=="q" goto :end

:end
echo.
pause
endlocal
