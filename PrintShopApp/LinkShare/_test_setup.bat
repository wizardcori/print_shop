@echo off
setlocal
echo [T7] condition FALSE, block has closing paren in text...
if 1==0 (
    echo [Error] Failed to create virtual environment (.venv).
    echo inside
)
echo T7-reached
