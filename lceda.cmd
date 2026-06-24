@echo off
rem LCEDA Bridge launcher - works from any CWD
rem 用法: lceda <subcmd> [args...]    例: lceda search ESP32
chcp 65001 >nul
python "%~dp0lceda_bridge\lceda_cli.py" %*
