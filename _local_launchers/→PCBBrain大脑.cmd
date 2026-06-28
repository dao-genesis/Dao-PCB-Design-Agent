@echo off
setlocal enabledelayedexpansion
title PCBBrain — AI PCB全自动流水线
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0pcb_brain"

echo.
echo  ████████████████████████████████████████████████████████
echo  ████  PCBBrain v5 — 两面一体·三生万物               ████
echo  ████████████████████████████████████████████████████████
echo.
echo  道生一  circuit_dna.py   电路DNA模板库 (4个模板)
echo  一生二  kicad_arm.py     KiCad pcbnew+CLI+GUI控制
echo  二生三  pcb_eye.py       截图/DRC/BOM/Gerber五感感知
echo  三生万物 pcb_server.py   两面一体HTTP服务
echo  面A(代码之名) REST API — http://localhost:9906/api/
echo  面B(软件之名) Web  UI  — http://localhost:9906/
echo  三(agent功用) AgentSense— localhost:9904 remote_agent
echo.
echo  CLI用法:
echo    python pcb_brain.py list
echo    python pcb_brain.py design stm32f103c6_dot_matrix
echo    python pcb_brain.py full stm32f103c6_dot_matrix --output D:\keil代码\stm32\pcb\
echo    python pcb_brain.py full esp32_servo_wifi
echo    python pcb_brain.py open --tool kicad
echo    python pcb_brain.py open --tool lceda
echo    python pcb_brain.py sense --pcb D:\keil代码\stm32\pcb\stm32f103c6_dot_matrix.kicad_pcb
echo    python pcb_brain.py status
echo    python pcb_brain.py serve          (Web服务 :9906)
echo    python pcb_server.py               (直接启动Web服务)
echo.

if "%1"=="serve" (
    echo  启动Web服务 → http://localhost:9906
    echo.
    start "" "http://localhost:9906"
    python pcb_server.py
) else if "%1"=="" (
    echo  选择启动模式:
    echo   [1] Web服务 (面B软件之名, 浏览器操作)
    echo   [2] CLI交互 (面A代码之名, 命令行)
    echo   [3] 环境检测
    echo.
    set /p MODE="  请输入 1/2/3: "
    if "!MODE!"=="1" (
        start "" "http://localhost:9906"
        python pcb_server.py
    ) else if "!MODE!"=="3" (
        python pcb_brain.py status
        pause
    ) else (
        python pcb_brain.py status
        echo.
        set /p CMD=">>> pcb_brain.py "
        python pcb_brain.py !CMD!
        pause
    )
) else (
    python pcb_brain.py %*
    pause
)

