"""Private object storage via the S3 protocol (Supabase today, AWS later).

Only the small Path surface used by the existing JSON stores is implemented.
Local development keeps ordinary pathlib paths. No secrets enter object keys.
"""
from functools import lru_cache
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
import os


@lru_cache(maxsize=1)
def client():
    import boto3
    from botocore.config import Config
    return boto3.client('s3', endpoint_url=os.getenv('S3_ENDPOINT_URL') or None,
                       region_name=os.getenv('AWS_REGION', 'ap-southeast-2'),
                       config=Config(signature_version='s3v4', s3={'addressing_style': 'path'},
                                     request_checksum_calculation='when_required',
                                     response_checksum_validation='when_required',
                                     connect_timeout=10, read_timeout=30,
                                     retries={'max_attempts': 2, 'mode': 'standard'}))


class ObjectPath(PurePosixPath):
    def _key(self):
        if self.is_absolute() or '..' in self.parts:
            raise ValueError('Invalid storage key')
        return str(self)

    def mkdir(self, *args, **kwargs):
        pass  # Object stores do not have directories.

    def read_bytes(self):
        from botocore.exceptions import ClientError
        try:
            response = client().get_object(Bucket=os.environ['S3_BUCKET'], Key=self._key())
            with response['Body'] as stream:
                return stream.read()
        except ClientError as exc:
            if exc.response['Error']['Code'] in ('NoSuchKey', '404'):
                raise FileNotFoundError(str(self)) from exc
            raise

    def read_text(self, encoding='utf-8'):
        return self.read_bytes().decode(encoding)

    def write_text(self, data, encoding='utf-8'):
        client().put_object(Bucket=os.environ['S3_BUCKET'], Key=self._key(),
                            Body=data.encode(encoding), ContentType='application/json')
        return len(data)

    def stat(self):
        from botocore.exceptions import ClientError
        try:
            result = client().head_object(Bucket=os.environ['S3_BUCKET'], Key=self._key())
            return SimpleNamespace(st_mtime=result['LastModified'].timestamp(), st_size=result['ContentLength'])
        except ClientError as exc:
            if exc.response['Error']['Code'] in ('NoSuchKey', '404', 'NotFound'):
                raise FileNotFoundError(str(self)) from exc
            raise

    def exists(self):
        try:
            self.stat()
            return True
        except FileNotFoundError:
            return False

    def unlink(self, missing_ok=False):
        client().delete_object(Bucket=os.environ['S3_BUCKET'], Key=self._key())

    def replace(self, target):
        # Whole-object PUT is atomic. Avoid copy/move dependencies across S3 vendors.
        target.write_text(self.read_text())
        self.unlink()
        return target

    def glob(self, pattern):
        prefix = self._key().rstrip('/') + '/'
        paginator = client().get_paginator('list_objects_v2')
        for page in paginator.paginate(Bucket=os.environ['S3_BUCKET'], Prefix=prefix):
            for item in page.get('Contents', []):
                relative = item['Key'][len(prefix):]
                if '/' not in relative and PurePosixPath(relative).match(pattern):
                    yield ObjectPath(item['Key'])


def storage_path(relative):
    if os.getenv('CLARORA_STORAGE_BACKEND') == 's3':
        return ObjectPath(relative)
    if os.getenv('VERCEL'):
        raise RuntimeError('Vercel requires CLARORA_STORAGE_BACKEND=s3')
    return Path(__file__).resolve().parents[1] / relative
