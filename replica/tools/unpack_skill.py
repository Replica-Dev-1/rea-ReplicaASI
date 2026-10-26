"""Validate and extract a reviewed skill to a NEW directory. Does not execute anything."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'server'))
import skills

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('package')
parser.add_argument('destination')
args = parser.parse_args()
sid, package = skills.validate(Path(args.package).read_text(encoding='utf-8'))
destination = Path(args.destination).resolve()
destination.mkdir(parents=False, exist_ok=False)
for file in package['files']:
    target = destination / file['path']
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(file['content'], encoding='utf-8', newline='')
print('Verified package ' + sid + '. Extracted without execution to ' + str(destination))
print('After reviewing the files, reported test command: ' + package['tests']['command'])
