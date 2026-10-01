# Upload tools

Assemble a program with `firmware/vasm` and send it to a board's serial loader. The scripts and their options are described in [`../README.md`](../README.md).

- `compile_and_upload.sh`: assemble, then run `transfer.py`. `compile_and_upload_{wendy,michael,wendy2}.sh` fix the baud rate (and Michael's format 3 and S-records) and call it.
- `compile_and_program.sh`: assemble and burn an AT28C256 with `minipro`.
- `transfer.py`: the sender. `upload_frame.py`: the upload formats (its docstring defines them). `serial_daemon.py`: keeps the port open so an upload doesn't reset the board.
- `test_dtr.py`: a manual DTR toggle test (edit `port` and `baudrate` at the top first).

Tests: `tools/tests/test_transfer.py`, `test_upload_frame.py`, `test_upload_scripts.py`, `test_serial_daemon.py`. Needs `pyserial`.
