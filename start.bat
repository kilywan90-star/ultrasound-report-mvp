@echo off
chcp 65001 >nul
title 超声语音报告系统 v3.0
echo =============================================
echo    超声语音报告系统 v3.0 — 全自动管线
echo =============================================
echo.
echo [1/4] 安装依赖...
pip install fastapi uvicorn pydantic python-multipart openai-whisper -q 2>nul
echo.
echo [2/4] 清理旧进程...
taskkill /f /im python.exe >nul 2>nul
timeout /t 1 >nul
echo.
echo [3/4] 启动后端 (端口 18001)...
cd /d "%~dp0backend"
start "超声后端" cmd /c "python -m uvicorn main:app --host 0.0.0.0 --port 18001"
timeout /t 4 >nul
echo.
echo [4/4] 打开浏览器...
start http://localhost:18001
echo.
echo =============================================
echo    🚀 系统已就绪!
echo    📍 http://localhost:18001
echo    📋 API: http://localhost:18001/docs
echo.
echo    全自动管线:
echo    ① 录音/输入 → ② ASR识别 → ③ 知识库修正
echo    ④ 意图识别 → ⑤ 模板匹配 → ⑥ 自动入库
echo.
echo    按任意键关闭后端...
echo =============================================
pause >nul
taskkill /f /im python.exe >nul 2>nul
