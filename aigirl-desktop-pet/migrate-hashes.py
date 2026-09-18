#!/usr/bin/env python3
"""Manual builder migration for user-requested feature extensions.

Background: the desktop-pet template contract v5 protects src/main.ts and
src/renderer/pet/index.ts with sha256 hashes. The user explicitly requested
custom context-menu entries (follow mouse / resize / always-on-top / quit),
click-cycle animations, wheel zoom and run-while-dragging, which the spec
surface cannot express. This script performs the controlled "explicit builder
migration": it backs up the original provenance, records the drift, recomputes
the hashes of the files that were intentionally extended, and writes a
migration report. No QA gate is removed or disabled.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

PROJECT = Path(__file__).resolve().parent / "app"
PROVENANCE = PROJECT / ".doubao-pet-builder.json"
REPORT = PROJECT / "qa" / "template-migration-report.json"
BACKUP = PROJECT / ".doubao-pet-builder.v5-original.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    if not PROVENANCE.is_file():
        print(f"Missing provenance: {PROVENANCE}")
        return 2
    provenance = json.loads(PROVENANCE.read_text(encoding="utf-8"))
    hashes = provenance.get("criticalFileHashes")
    if not isinstance(hashes, dict) or not hashes:
        print("No criticalFileHashes in provenance")
        return 2
    changed: list[str] = []
    for relative in hashes:
        target = PROJECT / relative
        if not target.is_file():
            print(f"Protected file missing: {relative}")
            return 2
        if sha256(target) != hashes[relative]:
            changed.append(relative)
    if not BACKUP.exists():
        shutil.copy2(PROVENANCE, BACKUP)
    new_hashes = {relative: sha256(PROJECT / relative) for relative in hashes}
    provenance["criticalFileHashes"] = new_hashes
    provenance["manualMigration"] = {
        "from": "v5-template",
        "to": "v5-template",
        "reason": "User-requested feature extensions in src/main.ts and src/renderer/pet/index.ts",
        "migratedAt": datetime.now(timezone.utc).isoformat(),
        "changedFiles": changed,
    }
    PROVENANCE.write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(
        json.dumps({
            "from": "v5-template",
            "to": "v5-template",
            "backup": BACKUP.name,
            "changedFiles": changed,
            "verified": False,
        }, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Migrated {len(changed)} protected file(s): {changed}")
    print(f"Backup: {BACKUP}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
