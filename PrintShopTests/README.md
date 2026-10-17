# PrintShop Integration Test Assistant

Run `python test_assistant.py` from this folder. The assistant performs automatic
hotspot/HTTP checks and pauses for human Pass/Fail confirmation for real-device
steps. Results are saved under `results/` as JSON.

Run the non-GUI automated tests with `run_automated_tests.bat`, or with
`python -m unittest -v test_automated.py`.

Automatic checks include the hotspot SSID/IP, QR URL response, web server,
SQLite tables, transfer file existence/size, user synchronization endpoint,
and administrator transfer records.

Manual checks cover real phone Wi-Fi, QR camera scanning, mobile display,
file selection/upload, administrator display, filename/size, color/copies,
and completion status because they require a real device and human confirmation.
