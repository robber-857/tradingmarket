"""Copy approved application JSON artifacts to a private S3-compatible bucket.

Dry run is default; --apply uploads. Never uploads SQLite, .env, or arbitrary files.
Existing objects must match, otherwise the import stops without overwriting them.
"""
import argparse
import hashlib
from pathlib import Path
from dotenv import load_dotenv
from server.object_store import ObjectPath

ROOT = Path(__file__).resolve().parents[1]
FOLDERS = ['reports', 'market_snapshots', 'macro_snapshots', 'news_snapshots',
           'news_editions', 'option_snapshots']


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    load_dotenv(ROOT/'.env')
    files = [p for folder in FOLDERS for p in (ROOT/'server'/folder).glob('*.json')]
    print('Snapshot files:', len(files), 'bytes:', sum(p.stat().st_size for p in files))
    if not args.apply:
        print('Dry run. Cache is intentionally rebuilt from upstream; no upload performed.')
        return
    count = 0
    for path in files:
        target = ObjectPath(path.relative_to(ROOT).as_posix())
        content = path.read_text(encoding='utf-8')
        if target.exists():
            if target.read_text() != content:
                raise RuntimeError('Existing snapshot differs; import stopped')
        else:
            target.write_text(content)
        if hashlib.sha256(target.read_text().encode()).digest() != hashlib.sha256(content.encode()).digest():
            raise RuntimeError('Object verification failed')
        count += 1
    print('Verified objects:', count)


if __name__ == '__main__':
    main()
