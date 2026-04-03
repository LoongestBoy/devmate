@echo off
chcp 65001 >nul
title DevMate 服务中心

echo ========================================
echo   🚀 正在唤醒 DevMate 核心微服务...
echo ========================================

:: 启动 MCP 节点 (在新窗口)
start "DevMate MCP Server" cmd /k "uv run python src/mcp_server.py"

:: 启动 Chat API (在新窗口)
start "DevMate Chat Engine" cmd /k "uv run uvicorn chat_server:app --reload --port 8080 --app-dir src"

echo.
echo ✅ 服务已全部点火！
echo 👉 请直接双击打开 web/chat.html 开始对话。
echo.
pause