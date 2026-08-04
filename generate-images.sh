#!/usr/bin/env bash

set -euo pipefail

root_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
output_dir="$root_dir/tmp/generated-images"

mkdir -p "$output_dir"

PYTHONPATH="$root_dir/src${PYTHONPATH:+:$PYTHONPATH}" python - "$output_dir" <<'PYTHON'
from pathlib import Path
import sys

from door_signboard import Scene, generate_image

output_dir = Path(sys.argv[1])
for scene in Scene:
    output_path = output_dir / f"{scene.value}.png"
    generate_image(scene).save(output_path)
    print(output_path)
PYTHON
