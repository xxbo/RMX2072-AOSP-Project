"""Exercise recovery from a genuinely truncated HTTP body and reject bad ranges."""
from collections import Counter
from contextlib import contextmanager, redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import os
from pathlib import Path
import re
import sys
import threading
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts/build'))
from bounded_remotezip import BoundedRemoteFetcher
from remotezip import RemoteZip, RemoteZipError


class SmallFetcher(BoundedRemoteFetcher):
    CHUNK_BYTES = 64 * 1024
    ATTEMPTS = 2


@contextmanager
def server(data, mode):
    calls = Counter()
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_HEAD(self):
            self.send_response(200)
            self.send_header('Content-Length', len(data))
            self.end_headers()

        def do_GET(self):
            match = re.fullmatch(r'bytes=(\d+)-(\d+)', self.headers['Range'])
            start, end = map(int, match.groups())
            with lock:
                calls[(start, end)] += 1
                attempt = calls[(start, end)]
            self.send_response(206)
            returned_start = start+1 if mode == 'wrong-range' else start
            self.send_header('Content-Range', f'bytes {returned_start}-{end}/{len(data)}')
            self.send_header('Content-Length', end-start+1)
            self.end_headers()
            body = data[start:end+1]
            if mode == 'truncate' and attempt == 1:
                body = body[:len(body)//2]
            self.wfile.write(body)
            self.wfile.flush()
            self.close_connection = True

    http = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{http.server_port}/artifact.zip', calls
    finally:
        http.shutdown()
        http.server_close()
        thread.join()


class DownloadTests(unittest.TestCase):
    def test_truncated_http_retries_and_recovers_exact_zip_member(self):
        payload = os.urandom(700000)
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
            z.writestr('Image.gz', payload)
        with server(archive.getvalue(), 'truncate') as (url, calls), redirect_stdout(io.StringIO()):
            with RemoteZip(url, fetcher=SmallFetcher, support_suffix_range=False, timeout=5) as z:
                self.assertEqual(z.read('Image.gz'), payload)
            self.assertTrue(calls)
            self.assertTrue(all(count == 2 for count in calls.values()))

    def test_wrong_content_range_is_rejected_after_bounded_retries(self):
        with server(b'x'*1024, 'wrong-range') as (url, calls), redirect_stdout(io.StringIO()):
            fetcher = SmallFetcher(url, support_suffix_range=False, timeout=5)
            with self.assertRaises(RemoteZipError):
                fetcher.fetch((0, 63))
            self.assertEqual(calls[(0, 63)], 2)


if __name__ == '__main__':
    unittest.main()
