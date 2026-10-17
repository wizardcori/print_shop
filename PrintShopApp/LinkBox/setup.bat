@echo off
chcp 65001 > nul
title LinkBox Environment Setup Script

echo ===================================================
echo   Starting LinkBox (Python 3.11) Environment Setup
echo ===================================================
echo.

python -c "import sys; exit(0 if sys.version_info[:2] == (3, 11) else 1)" > nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python 3.11 is required, but a different version was found or Python is not recognized.
    echo Please ensure Python 3.11 is installed and added to your system PATH.
    goto error_exit
)

echo [1/5] Python 3.11 verification complete.
echo.

if exist .venv goto skip_venv
echo [2/5] Creating Python 3.11 virtual environment (.venv)...
python -m venv .venv
echo Virtual environment created.
goto check_packages

:skip_venv
echo [2/5] Existing virtual environment (.venv) found. Skipping.

:check_packages
echo.
echo [3/5] Checking package installation status...
call .venv\Scripts\activate.bat

python -c "import PySide6, qrcode, PIL, cryptography, psutil" > nul 2>&1
if %errorlevel% equ 0 goto skip_pip

echo [INFO] Installing required packages (PySide6, qrcode, Pillow, cryptography, psutil)...
python -m pip install --upgrade pip > nul
pip install PySide6 qrcode[pil] cryptography psutil
echo Package installation complete.
goto check_ssl

:skip_pip
echo [INFO] Required packages are already installed. Skipping installation.

:check_ssl
echo.
echo [4/5] Checking SSL certificates for HTTPS...
if exist ..\..\secrets\cert.pem if exist ..\..\secrets\key.pem goto skip_ssl

echo [INFO] Generating self-signed SSL certificates via Python...
if not exist ..\..\secrets mkdir ..\..\secrets
python -c "from cryptography import x509; from cryptography.x509.name import Name; from cryptography.hazmat.primitives import hashes; from cryptography.hazmat.primitives.asymmetric import rsa; from cryptography.hazmat.primitives import serialization; import datetime; priv_key = rsa.generate_private_key(public_exponent=65537, key_size=2048); subj = x509.Name([x509.NameAttribute(x509.oid.NameOID.COMMON_NAME, 'LinkBoxServer')]); cert = x509.CertificateBuilder().subject_name(subj).issuer_name(subj).public_key(priv_key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(datetime.datetime.now(datetime.timezone.utc)).not_valid_after(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=365)).sign(priv_key, hashes.SHA256()); open(r'..\..\secrets\cert.pem', 'wb').write(cert.public_bytes(serialization.Encoding.PEM)); open(r'..\..\secrets\key.pem', 'wb').write(priv_key.private_bytes(encoding=serialization.Encoding.PEM, format=serialization.PrivateFormat.PKCS8, encryption_algorithm=serialization.NoEncryption()))"
echo SSL certificates generated successfully in the project secrets folder.
goto create_folder

:skip_ssl
echo [INFO] SSL certificates already exist. Skipping.

:create_folder
echo.
echo [5/5] Checking and creating project folder (templates)...
if not exist templates mkdir templates

echo.
echo ===================================================
echo   LinkBox environment setup is complete!
echo   You can run 'run.bat' to start the program.
echo ===================================================
echo.
pause
exit /b

:error_exit
pause
exit /b
