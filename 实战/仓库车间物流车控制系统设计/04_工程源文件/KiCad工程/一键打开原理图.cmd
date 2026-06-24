@echo off
chcp 65001 >nul
REM 直接进入原理图编辑器
REM 由 schematic_dao.render_kicad_launcher 自动生成
setlocal
set "KICAD_BIN=D:\KICAD\bin"
set "TARGET=D:\道\道生一\一生二\PCB设计\实战\仓库车间物流车控制系统设计\04_工程源文件\KiCad工程\warehouse_logistics_vehicle.kicad_sch"
if not exist "%KICAD_BIN%\eeschema.exe" (
    echo [错误] 未找到 KiCad GUI: %KICAD_BIN%\eeschema.exe
    echo 请检查 KiCad 9 安装路径; 默认: D:\KICAD\bin\
    pause
    exit /b 1
)
if not exist "%TARGET%" (
    echo [错误] 目标文件不存在: %TARGET%
    pause
    exit /b 1
)
echo 启动 eeschema.exe ^<- %TARGET%
start "" "%KICAD_BIN%\eeschema.exe" "%TARGET%"
endlocal
