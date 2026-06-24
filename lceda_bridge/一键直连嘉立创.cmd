@echo off
chcp 65001 >nul
title LCEDA Bridge - 一键直连嘉立创
cd /d "%~dp0"

echo ========================================================
echo   LCEDA Bridge - 嘉立创EDA 底层直连桥
echo   反者道之动  道法自然  无为而无不为
echo ========================================================
echo.
echo  本脚本将依次:
echo    1. 检查环境 (python lceda_cli.py status)
echo    2. 打包扩展 (生成 dist\lceda-bridge.eext)
echo    3. 启动嘉立创EDA客户端
echo    4. 在新窗口启动 Python 桥服务器
echo.
echo  之后您只需:
echo    a. 在嘉立创EDA: 高级 -^> 扩展管理器 -^> 导入 .eext
echo    b. 启用扩展 + 勾选 "外部交互"
echo    c. 顶部菜单 -^> LCEDA Bridge -^> 启动桥接
echo.
pause

echo.
echo [Step 1] 环境检查...
python lceda_cli.py status
if errorlevel 1 goto :error
echo.

echo [Step 2] 打包扩展...
python lceda_cli.py build
if errorlevel 1 goto :error
echo.

echo [Step 3] 启动嘉立创EDA客户端...
start "" "D:\lceda-pro\lceda-pro.exe"
echo   嘉立创EDA已启动, 等待5秒后启动桥服务器...
timeout /t 5 /nobreak >nul
echo.

echo [Step 4] 启动 Python 桥服务器 (新窗口)...
start "LCEDA Bridge Server" cmd /k "chcp 65001 & python lceda_cli.py serve"
echo.

echo ========================================================
echo  ✅ 全部启动完毕
echo.
echo  下一步:
echo    1. 在嘉立创EDA: 高级 -^> 扩展管理器 -^> 导入
echo       选择: %CD%\dist\lceda-bridge.eext
echo    2. 启用扩展 + 勾选 "外部交互" 权限
echo    3. 顶部菜单 -^> LCEDA Bridge -^> 启动桥接
echo.
echo  服务器 Web UI: http://127.0.0.1:9907/
echo.
echo  Python 端调用示例:
echo    python lceda_cli.py call sys_Environment.getEditorVersion
echo    python lceda_cli.py call dmt_Project.getCurrentProjectInfo
echo ========================================================
echo.
pause
goto :eof

:error
echo.
echo ❌ 出错了, 请查看上方输出
pause
exit /b 1
