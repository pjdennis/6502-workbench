"""firmware/programs/michael/michael_web_server.s, a web server on Michael's W5500 (on the FPGA bus), run on the
emulator with a client on the network (--add w5500 --net-request): each time the client connects and sends its
request, the server answers with the page ("Hello, world!" and a note for Angel), or 404 for any other path,
and closes the connection. The
LCD shows the address, the visits, the last request's first line and the frames that went wrong.

Run from the repo root:  python3 -m unittest discover -s tools/tests -v
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import michael_emulator  # noqa: E402

PROGRAM = os.path.join(michael_emulator.ROOT, 'firmware', 'programs', 'michael', 'michael_web_server.s')
CURL = (b'GET / HTTP/1.1\r\nHost: 192.168.8.50\r\nUser-Agent: curl/7.81.0\r\nAccept: */*\r\n\r\n')


@unittest.skipUnless(michael_emulator.AVAILABLE, 'vasm6502_oldstyle, gcc and make are needed')
class WebServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        michael_emulator.build_emulator()

    def serve(self, request=CURL, connections=2, w5500=True):
        """Runs the server for the client's connections. Returns (the emulator's report, what the server sent)"""
        with tempfile.TemporaryDirectory() as tmp:
            request_file, response_file = os.path.join(tmp, 'request'), os.path.join(tmp, 'response')
            with open(request_file, 'wb') as f:
                f.write(request)
            options = []
            if w5500:
                options = ['--add', 'w5500', '--net-request', request_file, '--net-response', response_file,
                           '--net-connections', str(connections)]
            report = michael_emulator.run(program=PROGRAM, cycle_cap=3_000_000, options=options)[1]
            response = b''
            if os.path.exists(response_file):
                with open(response_file, 'rb') as f:
                    response = f.read()
            return report, response

    def pages(self, response):
        return [b'HTTP/' + page for page in response.split(b'HTTP/')[1:]]

    def test_each_visit_gets_the_page(self):
        report, response = self.serve()
        self.assertIn('net client: port 80: 2 of 2 connections, 2 closed by the server', report)
        pages = self.pages(response)
        self.assertEqual(len(pages), 2, response)
        for n, page in enumerate(pages, 1):
            head, _, body = page.partition(b'\r\n\r\n')
            self.assertTrue(head.startswith(b'HTTP/1.0 200 OK\r\n'), head)
            self.assertIn(b'\r\nContent-Type: text/html', head)
            self.assertIn(b'<h1>Hello, world!</h1>', body)
            self.assertIn(b'Angel', body)
            self.assertIn(b'visitor number %d.' % n, body)
            self.assertTrue(body.rstrip().endswith(b'</html>'), body[-40:])
            self.assertTrue(all(32 <= b < 127 or b in b'\r\n' for b in page), 'plain ASCII')

    def test_the_lcd_shows_the_visits_and_the_request(self):
        report, _ = self.serve()
        self.assertIn('|WEB 192.168.8.50    |', report)
        self.assertIn('|SERVED 2            |', report)
        self.assertIn('|GET / HTTP/1.1      |', report)
        self.assertIn('|FAULTS 0000         |', report)
        self.assertIn('michael: w5500: ip 192.168.8.50 mask 255.255.255.0 gateway 192.168.8.1 '
                      'mac 02:65:02:00:00:01', report)
        self.assertIn('portb-contention=0', report)

    def test_a_long_request_is_read_to_its_end(self):
        """More than one read of the RX buffer (256 bytes at most each); the first line shown cut to 20"""
        request = (b'GET /a/rather/long/path/to/nowhere HTTP/1.1\r\nHost: 192.168.8.50\r\nCookie: '
                   + b'x' * 700 + b'\r\n\r\n')
        report, response = self.serve(request, connections=1)
        self.assertIn('1 of 1 connections, 1 closed by the server', report)
        self.assertEqual(len(self.pages(response)), 1)
        self.assertIn('|GET /a/rather/long/p|', report)

    def test_anything_but_the_page_is_not_found(self):
        """A browser asks for /favicon.ico too: it isn't a visit"""
        report, response = self.serve(b'GET /favicon.ico HTTP/1.1\r\nHost: 192.168.8.50\r\n\r\n', connections=1)
        self.assertIn('1 of 1 connections, 1 closed by the server', report)
        self.assertTrue(response.startswith(b'HTTP/1.0 404 Not Found\r\n'), response[:40])
        self.assertNotIn(b'Angel', response)
        self.assertIn('|SERVED 0            |', report)
        self.assertIn('|GET /favicon.ico HTT|', report)

    def test_without_the_w5500(self):
        report, _ = self.serve(w5500=False)   # the FPGA's network pins unconnected: MISO reads high
        self.assertIn('|NO W5500            |', report)


if __name__ == '__main__':
    unittest.main()
