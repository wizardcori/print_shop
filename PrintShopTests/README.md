# PrintShop Integration Test Assistant

Run `python test_assistant.py` from this folder. The assistant performs automatic
hotspot/HTTP checks and pauses for human Pass/Fail confirmation for real-device
steps. Results are saved under `results/` as JSON.

Run all tests with [run_printshop_tests.bat](../run_printshop_tests.bat) in
the parent folder. It runs the non-GUI automated tests first and then opens
the real-device test assistant.

The automated-only command is `python -m unittest discover -v -p "test_*.py"`.

The test suite is split into [test_database.py](./test_database.py),
[test_api.py](./test_api.py), [test_transfer_rules.py](./test_transfer_rules.py),
[test_ui.py](./test_ui.py), [test_automated.py](./test_automated.py), and the
real-device assistant [test_assistant.py](./test_assistant.py).

Automatic checks include the hotspot SSID/IP, QR URL response, web server,
SQLite tables, transfer file existence/size, user synchronization endpoint,
and administrator transfer records.

Manual checks cover real phone Wi-Fi, QR camera scanning, mobile display,
file selection/upload, administrator display, filename/size, color/copies,
and completion status because they require a real device and human confirmation.
