"""err.py: the form of an error report."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lathec_support as support  # noqa: E402
import err  # noqa: E402


class ErrorReportTest(unittest.TestCase):
    def setUp(self):
        support.fresh()
        err.init()

    def report(self, number):
        with self.assertRaises(SystemExit) as stop:
            err.fatal(number)
        self.assertEqual(stop.exception.code, 1)
        return support.error_text()

    def test_report_names_file_line_column_number_and_text(self):
        name, _ = support.put_text(b'dir/prog.lth')
        err.set_file(name)
        err.position(12, 7)
        self.assertEqual(self.report(err.E_UNDEFINED), 'dir/prog.lth:12:7: error 40: undefined name\n')

    def test_report_without_a_position_names_only_the_file(self):
        name, _ = support.put_text(b'prog.lth')
        err.set_file(name)
        self.assertEqual(self.report(err.E_OPEN_SOURCE), 'prog.lth: error 62: cannot open the source file\n')

    def test_report_without_a_file_names_the_tool(self):
        self.assertTrue(self.report(err.E_USAGE).startswith('lathec: error 60: usage'))

    def test_every_error_number_has_exactly_one_message(self):
        numbers = sorted(v for k, v in vars(err).items() if k.startswith('E_'))
        listed = [int(line.split(b' ')[0]) for line in err.MESSAGES.splitlines()]
        self.assertEqual(listed, numbers)

    def test_a_value_can_follow_the_text(self):
        with self.assertRaises(SystemExit):
            err.fatal_value(err.E_ROWS_RECORD, 12)
        self.assertTrue(support.error_text().endswith('its size is 12\n'))

    def test_a_number_with_no_message_still_reports(self):
        self.assertEqual(self.report(250), 'lathec: error 250: \n')


if __name__ == '__main__':
    unittest.main()
