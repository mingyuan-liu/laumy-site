#!/usr/bin/env python3
import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path
from urllib.parse import quote


def strip_number(name):
    name = re.sub(r"^[0-9]+(?:\.[0-9]+)*[-_.、\s]*", "", name)
    return name.strip() or "未分类"


def slugify(value):
    value = strip_number(value).lower().strip()
    value = re.sub(r"\s+", "-", value)
    value = re.sub(r"[\\/:*?\"<>|]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value or "item"


def split_frontmatter(text):
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---", 4)
    if end == -1:
        return {}, text
    raw = text[4:end].strip()
    body = text[end + 4 :].lstrip("\n")
    data = {}
    for line in raw.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        try:
            data[key] = json.loads(value)
        except Exception:
            data[key] = value.strip('"')
    return data, body


def yaml_value(value):
    return json.dumps(value, ensure_ascii=False)


def first_heading(body):
    match = re.search(r"^#\s+(.+)$", body, re.M)
    return match.group(1).strip() if match else ""


def drop_leading_title(body, title):
    lines = body.lstrip().splitlines()
    if not lines:
        return body
    first = lines[0].strip()
    if first.startswith("# ") and first[2:].strip() == str(title).strip():
        return "\n".join(lines[1:]).lstrip("\n")
    return body


def load_json(path, default):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default


def category_parts(root, path):
    parts = []
    parent = path.parent
    rel = parent.relative_to(root)
    if str(rel) == ".":
        return parts
    for part in rel.parts:
        if part == "assets" or part.startswith("_"):
            continue
        parts.append(strip_number(part))
    return parts


def ensure_index(dir_path, title):
    index = dir_path / "_index.md"
    if not index.exists():
        index.write_text(f"---\ntitle: {yaml_value(title)}\n---\n", encoding="utf-8")


def ensure_category_indices(root, parts):
    current = root
    for part in parts:
        current = current / slugify(part)
        current.mkdir(parents=True, exist_ok=True)
        ensure_index(current, part)


def copy_asset(src, dst):
    if dst.exists():
        src_stat = src.stat()
        dst_stat = dst.stat()
        if src_stat.st_size == dst_stat.st_size and src_stat.st_mtime_ns == dst_stat.st_mtime_ns:
            return
    shutil.copy2(src, dst)


def rewrite_assets(body, src_file, assets_output, assets_url_prefix):
    assets_dir = src_file.parent / "assets"
    if not assets_dir.exists():
        return body
    digest = hashlib.sha1(str(src_file).encode("utf-8")).hexdigest()[:12]
    dst_dir = assets_output / digest
    dst_dir.mkdir(parents=True, exist_ok=True)
    for asset in assets_dir.iterdir():
        if asset.is_file():
            copy_asset(asset, dst_dir / asset.name)
    return re.sub(r"\]\(\./assets/([^)]+)\)", rf"]({assets_url_prefix}/{digest}/\1)", body)


def add_tree_count(node, parts):
    if not parts:
        return
    title = parts[0]
    child = node["children"].setdefault(title, {"title": title, "count": 0, "children": {}})
    child["count"] += 1
    add_tree_count(child, parts[1:])


def freeze_tree(children, prefix="", level=1):
    result = []
    for title in children:
        node = children[title]
        path = f"{prefix}/{slugify(title)}"
        result.append({
            "title": title,
            "slug": slugify(title),
            "url": f"/posts/{path.strip('/')}/",
            "count": node["count"],
            "level": level,
            "children": freeze_tree(node["children"], path, level + 1),
        })
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("content_source")
    parser.add_argument("--site", default=".")
    parser.add_argument(
        "--assets-output",
        help="Directory where per-post assets are copied. Defaults to <site>/static/assets/posts.",
    )
    parser.add_argument("--assets-url-prefix", default="/assets/posts")
    args = parser.parse_args()

    source = Path(args.content_source).resolve()
    site = Path(args.site).resolve()
    assets_output = Path(args.assets_output).resolve() if args.assets_output else site / "static" / "assets" / "posts"
    assets_url_prefix = "/" + args.assets_url_prefix.strip("/")
    out = site / "content" / "posts"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    assets_output.mkdir(parents=True, exist_ok=True)

    meta = load_json(site / "data" / "export-meta.json", {})
    stats = load_json(site / "data" / "post-stats.json", {"posts": {}})
    tree_root = {"count": 0, "children": {}}

    generated = 0
    for src in sorted(source.rglob("*.md")):
        if "assets" in src.parts or src.name == "index.md" or src.name.startswith("_"):
            continue
        fm, body = split_frontmatter(src.read_text(encoding="utf-8"))
        if fm.get("status", "publish") != "publish":
            continue
        post_id = str(fm.get("id", ""))
        item_meta = meta.get(post_id, {})
        title = fm.get("title") or item_meta.get("title") or first_heading(body) or strip_number(src.stem)
        cats = category_parts(source, src)
        category = cats[-1] if cats else item_meta.get("category", "未分类")
        if not cats and category:
            cats = [category]
        add_tree_count(tree_root, cats)

        rel_dir = Path(*[slugify(p) for p in cats]) if cats else Path("uncategorized")
        dst_dir = out / rel_dir
        dst_dir.mkdir(parents=True, exist_ok=True)
        ensure_category_indices(out, cats)
        dst = dst_dir / f"{post_id or slugify(src.stem)}.md"

        body = drop_leading_title(body, title)
        body = rewrite_assets(body, src, assets_output, assets_url_prefix)
        views = stats.get("posts", {}).get(post_id, {}).get("views", 0)
        final = {
            "title": title,
            "date": fm.get("date") or item_meta.get("date") or "2000-01-01T00:00:00+00:00",
            "lastmod": fm.get("modified") or item_meta.get("modified") or fm.get("date") or "2000-01-01T00:00:00+00:00",
            "author": fm.get("author", "laumy"),
            "tags": fm.get("tags", item_meta.get("tags", [])),
            "categories": [category],
            "category": category,
            "category_path": cats,
            "category_url": f"/posts/{'/'.join(slugify(p) for p in cats)}/",
            "cover": item_meta.get("cover") or fm.get("cover") or "",
            "description": item_meta.get("description") or fm.get("description") or "",
            "views": views,
        }
        if post_id:
            final["id"] = int(post_id) if post_id.isdigit() else post_id
        if item_meta.get("url"):
            final["url"] = item_meta["url"]
            final["canonical"] = item_meta.get("canonical", "https://www.laumy.tech" + item_meta["url"])
        elif fm.get("url"):
            final["url"] = fm["url"]

        lines = ["---"]
        for key, value in final.items():
            if value == "" or value == []:
                continue
            lines.append(f"{key}: {yaml_value(value)}")
        lines.extend(["---", "", body])
        dst.write_text("\n".join(lines), encoding="utf-8")
        generated += 1

    category_tree = json.dumps(freeze_tree(tree_root["children"]), ensure_ascii=False, indent=2)
    (site / "data" / "category-tree.json").write_text(category_tree, encoding="utf-8")
    (site / "data" / "category_tree.json").write_text(category_tree, encoding="utf-8")
    stats_src = site / "data" / "post-stats.json"
    if stats_src.exists():
        (site / "data" / "post_stats.json").write_text(stats_src.read_text(encoding="utf-8"), encoding="utf-8")
    (site / "static" / "llms.txt").write_text(
        "# laumy的学习笔记\n\n"
        "这是一个中文技术博客，主要内容包括 Linux、嵌入式、AI 大模型、网络协议、机器人系统等。\n\n"
        "Sitemap: https://www.laumy.tech/sitemap.xml\n"
        "RSS: https://www.laumy.tech/index.xml\n"
        "Archive: https://www.laumy.tech/\n",
        encoding="utf-8",
    )
    print(f"Generated {generated} Hugo posts")


if __name__ == "__main__":
    main()
