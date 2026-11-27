"""Read checked ZIP ranges in small retryable pieces, without saving old images."""
from concurrent.futures import ThreadPoolExecutor
import io
import time

import requests
from remotezip import PartialBuffer, RemoteFetcher, RemoteZipError


class BoundedRemoteFetcher(RemoteFetcher):
    CHUNK_BYTES = 256 * 1024
    MAX_RANGE_BYTES = 64 * 1024 * 1024
    WORKERS = 4
    ATTEMPTS = 3

    def _piece(self, bounds):
        start, end, total = bounds
        kwargs = self.prepare_request((start, end))
        kwargs['timeout'] = (15, 30)
        for attempt in range(self.ATTEMPTS):
            try:
                # Each worker owns its session. No shared cookies or mutable
                # request state, and no inherited broken localhost proxy.
                with requests.Session() as session:
                    session.trust_env = False
                    with session.get(self._url, stream=True, **kwargs) as response:
                        if response.status_code != 206 or response.headers.get('Content-Range') != f'bytes {start}-{end}/{total}':
                            raise RemoteZipError('Artifact server returned a different range')
                        data = response.raw.read(end-start+1)
                        if len(data) != end-start+1:
                            raise RemoteZipError('Artifact range is incomplete')
                        return data
            except (requests.RequestException, OSError, RemoteZipError) as error:
                kind = type(error).__name__
            except Exception as error:
                # urllib3 may raise ProtocolError directly through raw.read().
                # Preserve only the class, never a signed storage URL.
                kind = type(error).__name__
                if kind not in ('ProtocolError', 'ReadTimeoutError', 'IncompleteRead'):
                    raise
            if attempt+1 < self.ATTEMPTS:
                print(f'Retrying artifact bytes {start}-{end}: {kind}', flush=True)
                time.sleep(0.5)
        raise RemoteZipError(f'Artifact bytes {start}-{end} failed after {self.ATTEMPTS} attempts ({kind})') from None

    def fetch(self, data_range, stream=False):
        if not hasattr(self, '_checked_total'):
            self._checked_total = self.get_file_size()
        total = self._checked_total
        start, end = data_range
        if start < 0 and end is None:
            start, end = max(0, total+start), total-1
        if end is None or not 0 <= start <= end < total or end-start+1 > self.MAX_RANGE_BYTES:
            raise RemoteZipError('Artifact range exceeds bounded member limits')
        ranges = [(pos, min(pos+self.CHUNK_BYTES-1, end), total)
                  for pos in range(start, end+1, self.CHUNK_BYTES)]
        with ThreadPoolExecutor(max_workers=self.WORKERS) as pool:
            data = b''.join(pool.map(self._piece, ranges))
        if len(data) != end-start+1:
            raise RemoteZipError('Assembled artifact range length differs')
        if len(ranges) > 1:
            print(f'Checked artifact range: {len(data)} bytes in {len(ranges)} pieces', flush=True)
        return PartialBuffer(io.BytesIO(data), start, len(data), stream=False)
