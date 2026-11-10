"""Exercise the same S3 adapter used by SEC, not a replacement pathlib cache."""
from datetime import datetime, timezone
from io import BytesIO
import json

import httpx
import pytest
from botocore.exceptions import ClientError

from server import object_store, sec


@pytest.fixture
def s3_cache(monkeypatch):
    objects = {}

    class MemoryS3:
        def get_object(self, *, Bucket, Key):
            if Key not in objects:
                raise ClientError({'Error': {'Code': 'NoSuchKey'}}, 'GetObject')
            return {'Body': BytesIO(objects[Key])}

        def head_object(self, *, Bucket, Key):
            if Key not in objects:
                raise ClientError({'Error': {'Code': '404'}}, 'HeadObject')
            return {'LastModified': datetime.now(timezone.utc), 'ContentLength': len(objects[Key])}

    monkeypatch.setenv('S3_BUCKET', 'test-private')
    monkeypatch.setattr(object_store, 'client', lambda: MemoryS3())
    monkeypatch.setattr(sec, 'CACHE', object_store.ObjectPath('server/cache'))
    monkeypatch.setattr(sec, '_directory_memory', None)
    return objects


def test_object_bytes_preserve_hash_input_and_missing_file(s3_cache):
    import hashlib
    content = b'{"company":"\xe9\x9c\x81\xe6\x98\x8e", "endings":"\\r\\n"}\r\n'
    s3_cache['server/cache/facts.json'] = content
    path = object_store.ObjectPath('server/cache/facts.json')
    assert path.read_bytes() == content
    assert hashlib.sha256(path.read_bytes()).hexdigest() == hashlib.sha256(content).hexdigest()
    assert path.read_text() == content.decode('utf-8')
    with pytest.raises(FileNotFoundError):
        object_store.ObjectPath('server/cache/missing.json').read_bytes()


def test_sec_directory_and_company_facts_work_with_s3(s3_cache, monkeypatch):
    import asyncio
    import hashlib
    directory = {'fields': ['cik', 'name', 'ticker', 'exchange'],
                 'data': [[320193, 'Apple Inc.', 'AAPL', 'Nasdaq']]}
    payloads = {'company-tickers-exchange.json': directory,
                'AAPL-facts.json': {'cik': 320193, 'facts': {'us-gaap': {}}},
                'AAPL-submissions.json': {'cik': '0000320193', 'name': 'Apple Inc.'}}
    for name, payload in payloads.items():
        s3_cache['server/cache/' + name] = json.dumps(payload).encode()
    monkeypatch.setenv('SEC_USER_AGENT', 'Clarora tests test@example.invalid')

    async def no_network(*args, **kwargs):
        raise AssertionError('Valid cloud cache should not fetch SEC')

    monkeypatch.setattr(httpx.AsyncClient, 'get', no_network)

    async def exercise():
        listing = await sec.company_directory()
        company = listing['records']['AAPL']
        facts, submissions, sources = await sec.fetch_company('AAPL', company=company)
        assert facts['cik'] == 320193
        assert submissions['name'] == 'Apple Inc.'
        assert listing['source']['sha256'] == hashlib.sha256(s3_cache['server/cache/company-tickers-exchange.json']).hexdigest()
        assert sources[0]['sha256'] == hashlib.sha256(s3_cache['server/cache/AAPL-facts.json']).hexdigest()

    asyncio.run(exercise())
