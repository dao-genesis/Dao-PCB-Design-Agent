@echo off
chcp 65001 >nul
REM 用 KiCad 工程管理器打开 (推荐入口)
REM 由 schematic_dao.render_kicad_launcher 自动生成
setlocal
set "KICAD_BIN=D:\KICAD\bin"
set "TARGET=D:\道\道生一\一生二\PCB设计\实战\仓库车间物流车控制系统设计\04_工程源文件\KiCad工程\warehouse_logistics_vehicle.kicad_pro"
if not exist "%KICAD_BIN%\kicad.exe" (
    echo [错误] 未找到 KiCad GUI: %KICAD_BIN%\kicad.exe
    echo 请检查 KiCad 9 安装路径; 默认: D:\KICAD\bin\
    pause
    exit /b 1
)
if not exist "%TARGET%" (
    echo [错误] 目标文件不存在: %TARGET%
    pause
    exit /b 1
)
echo 启动 kicad.exe ^<- %TARGET%
start "" "%KICAD_BIN%\kicad.exe" "%TARGET%"
endlocal
