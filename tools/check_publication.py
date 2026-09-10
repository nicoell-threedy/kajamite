"""Check staged files or reachable Git history without printing private values."""
import argparse
import hashlib
from pathlib import Path
import re
import subprocess
import sys

# Fingerprints keep consumer-specific identifiers out of public source text.
PRIVATE_IDENTIFIERS = {
    'afd29ba62e801901fe960a6a03fa4d59db905fb8ff156847911aca72c00159f4',
    '73ba7e8a2b98ec921462bde295ead136b5dddb8f06307379e42296fdc426a851',
}
PATTERNS = {
    'private key': re.compile(rb'-----BEGIN (?:[A-Z ]*PRIVATE KEY)-----'),
    'credential token': re.compile(rb'\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[A-Z0-9]{16}|sk-[A-Za-z0-9_-]{20,})'),
    'machine home path': re.compile(rb'(?:/home/|/Users/|[A-Za-z]:[\\/]+Users[\\/]+)[A-Za-z0-9_.-]+'),
    'private network address': re.compile(rb'\b(?:192\.168\.|10\.|172\.(?:1[6-9]|2[0-9]|3[01])\.)\d{1,3}\.\d{1,3}\b'),
}


def reasons(data, identifiers=PRIVATE_IDENTIFIERS):
    found = {name for name, pattern in PATTERNS.items() if pattern.search(data)}
    if any(hashlib.sha256(word.lower()).hexdigest() in identifiers
           for word in re.findall(rb'[A-Za-z]+', data)):
        found.add('private identifier')
    return sorted(found)


def git(*args):
    return subprocess.check_output(['git', *args])


def check(staged=False, refs=None):
    objects = {}
    failures = []
    if staged:
        for entry in git('ls-files', '--stage', '-z').split(b'\0'):
            if not entry:
                continue
            meta, path = entry.split(b'\t', 1)
            mode, oid, stage = meta.split()
            if stage != b'0':
                failures.append('unmerged index entry')
            if reasons(path):
                failures.append('private staged path')
            if mode != b'160000':
                objects[oid.decode()] = 'blob'
    else:
        # Reject option-like refs; hooks pass full object IDs.
        refs = refs or ['HEAD']
        if any(ref.startswith('-') for ref in refs):
            raise ValueError('invalid revision')
        for entry in git('rev-list', '--objects', *refs).splitlines():
            oid, _, path = entry.partition(b' ')
            if reasons(path):
                failures.append('private history path')
            objects[oid.decode()] = None
    for oid, kind in objects.items():
        kind = kind or git('cat-file', '-t', oid).decode().strip()
        if kind not in ('blob', 'commit', 'tag'):
            continue
        for reason in reasons(git('cat-file', kind, oid)):
            failures.append(f'{kind} {oid[:12]}: {reason}')
    return sorted(set(failures))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--staged', action='store_true')
    parser.add_argument('--pre-push', action='store_true')
    parser.add_argument('refs', nargs='*')
    args = parser.parse_args()
    refs = args.refs
    if args.pre_push:
        refs = [fields[1] for line in sys.stdin if (fields := line.split())
                and set(fields[1]) != {'0'}]
        if not refs:
            return 0
    failures = check(args.staged, refs)
    for failure in failures:
        print(f'Publication check failed: {failure}', file=sys.stderr)
    if not failures:
        print('Publication check passed.')
    return bool(failures)


if __name__ == '__main__':
    sys.exit(main())
