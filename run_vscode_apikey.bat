@echo off
chcp 65001 > nul

:: Check if the secrets/GROQ_API_KEY file exists
if not exist "secrets\GROQ_API_KEY" (
    echo [ERROR] secrets\GROQ_API_KEY file not found!
    echo Please check the file path and location.
    pause
    exit /b 1
)

:: Read the API key from the file and strip trailing spaces/newlines
for /f "tokens=*" %%a in (secrets\GROQ_API_KEY) do set GROQ_API_KEY=%%a

echo [INFO] GROQ_API_KEY successfully loaded from secrets folder.
echo [INFO] Launching VS Code...

:: Launch VS Code for the current directory (inherits the environment variable)
code .