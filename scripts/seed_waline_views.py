#!/usr/bin/env python3
"""Generate SQL to seed Waline pageview counters from Hugo frontmatter."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)


def scalar(frontmatter: str, key: str) -> str | None:
    match = re.search(rf"^{re.escape(key)}:\s*(.+?)\s*$", frontmatter, re.M)
    if not match:
        return None

    value = match.group(1).strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        value = value[1:-1]
    return value


def sql_string(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "''") + "'"


def iter_counters(content_dir: Path) -> list[tuple[str, int]]:
    counters: dict[str, int] = {}

    for md_file in sorted(content_dir.rglob("*.md")):
        text = md_file.read_text(encoding="utf-8")
        match = FRONTMATTER_RE.match(text)
        if not match:
            continue

        frontmatter = match.group(1)
        status = scalar(frontmatter, "status") or "publish"
        url = scalar(frontmatter, "url")
        views = scalar(frontmatter, "views")

        if status != "publish" or not url or not views:
            continue

        try:
            view_count = int(views)
        except ValueError:
            continue

        if view_count > 0:
            counters[url] = max(counters.get(url, 0), view_count)

    return sorted(counters.items())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "content_dir",
        nargs="?",
        default="content",
        type=Path,
        help="Hugo content directory, defaults to ./content",
    )
    parser.add_argument("--prefix", default="wl_", help="Waline table prefix")
    args = parser.parse_args()

    table = f"`{args.prefix}Counter`"
    counters = iter_counters(args.content_dir)

    print("SET NAMES utf8mb4;")
    print("START TRANSACTION;")
    for url, views in counters:
        path = sql_string(url)
        print(
            f"INSERT INTO {table} (`url`, `time`, `createdAt`, `updatedAt`) "
            f"SELECT {path}, {views}, NOW(), NOW() "
            f"WHERE NOT EXISTS (SELECT 1 FROM {table} WHERE `url` = {path});"
        )
        print(
            f"UPDATE {table} SET `time` = {views}, `updatedAt` = NOW() "
            f"WHERE `url` = {path} AND (`time` IS NULL OR `time` < {views});"
        )
    print("COMMIT;")


if __name__ == "__main__":
    main()
