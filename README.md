# PrintShop

PrintShop is a Windows desktop application for automating a print shop workflow from file upload through validation, printer routing, completion, and post-payment handover.

## Features

- **LinkBox**: Provides an HTTPS upload server that customers can access by QR code.
- **LinkShare**: Manages Internet access requests, approvals, sessions, and usage logs.
- **Integrated administration**: Combines LinkBox and LinkShare in a PySide6 desktop interface.
- **Network discovery**: Detects Internet-connected and hotspot-compatible network adapters.
- **Windows hotspot control**: Supports hotspot diagnostics and Windows WinRT tethering control, with `netsh` fallback.
- **QR access links**: Generates QR codes for the active store network and hotspot address.
- **Encrypted settings**: Protects LinkShare security data with Fernet encryption.
- **Configurable connection limit**: Applies an application-level maximum connection limit.
- **Order state machine**: Tracks `UPLOADED` through `PAID_HANDOVER` with rollback rules and audit history.
- **Automated validation**: Checks file existence, format, size, paper size, and print options before acceptance.
- **Smart printer routing**: Selects an available printer by paper/color capability and queue length.
- **Centralized pricing and audit data**: Persists orders, per-file options, notifications, state history, and print logs in SQLite.

## Technology

- Python 3.11
- PySide6
- Flask and Python `http.server`
- Pillow and qrcode
- cryptography
- psutil
- PyInstaller
- SQLite (local order and audit persistence)

## Project Structure

```text
1print_shop/
├── PrintShopApp/              # Main desktop application
│   ├── main_app.py            # Integrated application entry point
│   ├── LinkBox/               # HTTPS file upload service
│   ├── LinkShare/              # Wi-Fi access and session service
│   ├── data/                  # Local runtime data
│   └── setup.bat              # Application environment setup
├── PrintShopTests/            # Automated and real-device tests
├── secrets/                   # Local certificates and private keys (ignored)
├── github_sync.bat            # Commit and push helper
└── git_security_check.bat     # Git security file checker
```

## Requirements

- Windows 10 or later
- Python 3.11
- A Wi-Fi adapter that supports Windows Mobile Hotspot, if hotspot features are required

## Installation and Startup

Open a terminal in `PrintShopApp` and run:

```bat
setup.bat
run.bat
```

The setup script creates `.venv`, installs the required packages, creates the `secrets` folder, and generates a self-signed certificate and private key when they do not already exist.

The generated files are stored locally at:

```text
secrets/cert.pem
secrets/key.pem
```

These files are excluded by `.gitignore` and must not be committed to a public repository.

## Building LinkBox

From `PrintShopApp/LinkBox`, run:

```bat
dist.bat
```

The PyInstaller configuration includes the local certificate files in the generated distribution. Ensure the local `secrets` folder has valid files before building.

## Testing

Run the complete test workflow from the project root:

```bat
run_printshop_tests.bat
```

Run the automated test suite directly from `PrintShopTests`:

```bat
python -m unittest discover -v -p "test_*.py"
```

Some tests require a real phone connected to the Windows hotspot and include manual Pass/Fail confirmation.

## Security Checks

Before committing or pushing changes, run:

```bat
git_security_check.bat
```

The checker scans tracked file names, staged content, private-key patterns, GitHub tokens, AWS access keys, and Google API keys. It also verifies that the root `secrets` folder is ignored.

Do not commit:

- `secrets/cert.pem`
- `secrets/key.pem`
- Passwords, API keys, tokens, or production configuration
- Local databases or user data

If a private key has already been pushed, remove it from active use and generate a new one. Removing the file in a later commit does not remove it from Git history.

## GitHub Synchronization

The optional `github_sync.bat` script can initialize the repository, configure the `master` branch, install GitHub CLI with `winget` when needed, authenticate with GitHub, create the configured private repository if it does not exist, and push the current branch.

Before the first use, authenticate with GitHub CLI if prompted:

```bat
gh auth login
```

Review the output of `git_security_check.bat` before running the synchronization script.

## License

No license has been specified for this project yet.
