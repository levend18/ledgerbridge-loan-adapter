import hashlib

import httpx

from tests.unit.test_bank import BASE, HEADERS, csv_bytes
from tools.generate_synthetic import credit


def test_bank_network_stream_is_chunked_and_matches_metadata():
    with httpx.Client(base_url="http://bank:8001") as client:
        response = client.put(BASE + "/credit", headers=HEADERS, content=csv_bytes([credit(1)]))
        response.raise_for_status()
        with client.stream("GET", BASE + "/credit/records", headers=HEADERS) as stream:
            assert stream.headers["transfer-encoding"] == "chunked"
            body = b"".join(stream.iter_bytes())
        metadata = response.json()["datasets"]["credit"]
        assert metadata["sha256"] == hashlib.sha256(body).hexdigest()
        assert metadata["row_count"] == len(body.splitlines()) == 1
