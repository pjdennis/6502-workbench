import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import debug  # noqa: E402


class FakeSerial:
    def __init__(self, answers=()):
        self.written, self.answers = b"", [a.encode() for a in answers]

    def write(self, data):
        self.written += data

    def readline(self, deadline):
        return self.answers.pop(0) if self.answers else b""


class DebugPortTest(unittest.TestCase):
    def port(self, *answers):
        self.ser = FakeSerial(answers)
        return debug.DebugPort(self.ser)

    def test_commands_and_data_as_lines(self):
        p = self.port()
        p.command(0x11)
        p.data(0x2A, 0x00, 0xEF)
        self.assertEqual(self.ser.written, b"C11\nD2A00EF\n")

    def test_long_data_is_split_into_lines(self):
        p = self.port()
        p.data(*range(40))
        lines = self.ser.written.split(b"\n")[:-1]
        self.assertEqual([len(line) for line in lines], [1 + 64, 1 + 16])

    def test_read_the_reply_queue(self):
        p = self.port("r414243\r\n")
        self.assertEqual(p.read(3), [0x41, 0x42, 0x43])
        self.assertEqual(self.ser.written, b"R03\n")

    def test_lines_from_michael_are_skipped(self):
        p = self.port("FPGA BUS CHECK\r\n", "r00\r\n")
        self.assertEqual(p.read(), [0x00])

    def test_status(self):
        p = self.port("s88\r\n")
        self.assertEqual(p.status(), 0x88)
        self.assertEqual(self.ser.written, b"S\n")

    def test_no_answer(self):
        p = self.port()
        with self.assertRaises(debug.NoAnswer):
            p.status()

    def test_a_serial_timeout_is_no_answer(self):
        p = self.port()
        def timeout(deadline):
            raise TimeoutError("no response from board")
        self.ser.readline = timeout
        with self.assertRaises(debug.NoAnswer):
            p.read()

    def test_display_command_is_disp_command_then_its_bytes(self):
        p = self.port()
        p.disp_command(0x2A, 0x00, 0x00, 0x01, 0x3F)
        self.assertEqual(self.ser.written, b"C11\nD2A0000013F\n")

    def test_id(self):
        p = self.port("r4D420101\r\n")
        self.assertEqual(p.id(), ("MB", 1, 0x01))
        self.assertEqual(self.ser.written, b"C01\nR04\n")


if __name__ == "__main__":
    unittest.main()
