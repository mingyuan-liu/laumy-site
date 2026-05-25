#!/usr/bin/env python3
import argparse
import html
import hashlib
import json
import re
import shutil
from pathlib import Path
from urllib.parse import quote

DEFAULT_COVER = "/images/default-thumb.jpg"
SITE_BASE_URL = "https://www.laumy.tech"


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


def is_truthy(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def normalize_url_path(value):
    value = str(value or "").strip()
    if not value:
        return ""
    value = re.sub(r"^https?://[^/]+", "", value)
    if not value.startswith("/"):
        value = "/" + value
    return value


def default_post_url(cats, src_file, fm):
    parts = [slugify(part) for part in cats]
    post_slug = slugify(fm.get("slug") or src_file.stem)
    return "/" + "/".join(["notes", *parts, post_slug]) + "/"


def fallback_post_url(cats, dst):
    parts = ["notes", "posts", *[slugify(part) for part in cats], dst.stem]
    return quote("/" + "/".join(parts) + "/", safe="/")


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


def should_skip_source(root, path):
    rel = path.relative_to(root)
    return any(part == "auto" for part in rel.parts)


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
        return body, ""
    digest = hashlib.sha1(str(src_file).encode("utf-8")).hexdigest()[:12]
    dst_dir = assets_output / digest
    dst_dir.mkdir(parents=True, exist_ok=True)
    for asset in assets_dir.iterdir():
        if asset.is_file():
            copy_asset(asset, dst_dir / asset.name)
    asset_url_base = f"{assets_url_prefix}/{digest}"
    body = re.sub(r"\]\(\./assets/([^)]+)\)", rf"]({asset_url_base}/\1)", body)
    body = re.sub(r"""(\b(?:src|href)=["'])\./assets/([^"']+)""", rf"\1{asset_url_base}/\2", body)
    return body, f"{asset_url_base}/"


def nginx_quote(value):
    return json.dumps(str(value), ensure_ascii=False)


def nginx_auth_lines(auth_file, indent="        "):
    return [
        f'{indent}auth_basic "laumy protected";',
        f"{indent}auth_basic_user_file {nginx_quote(auth_file)};",
    ]


def write_protected_nginx(path, routes, auth_file, assets_root):
    path.parent.mkdir(parents=True, exist_ok=True)
    page_urls = sorted({normalize_url_path(route.get("url")) for route in routes if route.get("url")})
    asset_prefixes = sorted({normalize_url_path(route.get("assets")) for route in routes if route.get("assets")})

    lines = [
        "# Generated by scripts/build_content.py. Do not edit.",
        "# This file is included by deploy/nginx/laumy-production.conf.",
    ]

    for url in page_urls:
        exact_url = url.rstrip("/") if url != "/" else url
        prefix_url = url if url.endswith("/") else url + "/"

        if exact_url != prefix_url:
            lines.extend([
                "",
                f"    location = {nginx_quote(exact_url)} {{",
                *nginx_auth_lines(auth_file),
                "        try_files $uri $uri/ =404;",
                "    }",
            ])

        lines.extend([
            "",
            f"    location ^~ {nginx_quote(prefix_url)} {{",
            *nginx_auth_lines(auth_file),
            "        try_files $uri $uri/ =404;",
            "    }",
        ])

    for prefix in asset_prefixes:
        lines.extend([
            "",
            f"    location ^~ {nginx_quote(prefix)} {{",
            *nginx_auth_lines(auth_file),
            f"        root {nginx_quote(assets_root)};",
            "        access_log off;",
            "        expires 30d;",
            '        add_header Cache-Control "public, max-age=2592000";',
            "        try_files $uri =404;",
            "    }",
        ])

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def clean_image_url(value):
    value = html.unescape(value or "").strip()
    value = value.strip("<>\"'")
    value = value.replace("\\%22", "").replace("%22", "")
    value = value.replace('\\"', "").replace("\\'", "")
    value = value.strip("<>\"' )")
    return value


def is_image_url(value):
    path = value.split("?", 1)[0].split("#", 1)[0].lower()
    return path.startswith(("/assets/posts/", "/images/")) or re.search(r"\.(?:png|jpe?g|gif|webp|svg)$", path)


def first_article_image(body):
    matches = []
    markdown_image = re.compile(r"!\[[^\]]*\]\(\s*(<[^>]+>|[^)\s]+)(?:\s+['\"][^'\"]*['\"])?\s*\)")
    html_image = re.compile(r"""<img\b[^>]*\bsrc\s*=\s*(?:"([^"]+)"|'([^']+)'|([^\s>]+))""", re.I)

    for match in markdown_image.finditer(body):
        matches.append((match.start(), match.group(1)))
    for match in html_image.finditer(body):
        matches.append((match.start(), next(group for group in match.groups() if group)))

    for _, raw_url in sorted(matches):
        url = clean_image_url(raw_url)
        if not url or "wp-content/uploads" in url or not is_image_url(url):
            continue
        return url
    return ""


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
    parser.add_argument("--protected-nginx-output", help="Write generated Nginx auth locations for protected posts.")
    parser.add_argument("--protected-auth-file", default="/etc/nginx/laumy-private.htpasswd")
    parser.add_argument("--protected-assets-root", default="/var/www/laumy-static/shared")
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
    protected_routes = []
    pageview_paths = []
    for src in sorted(source.rglob("*.md")):
        if should_skip_source(source, src):
            continue
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
        body, asset_prefix = rewrite_assets(body, src, assets_output, assets_url_prefix)
        protected = is_truthy(fm.get("protected", False))
        cover = DEFAULT_COVER if protected else (first_article_image(body) or DEFAULT_COVER)
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
            "cover": cover,
            "description": item_meta.get("description") or fm.get("description") or "",
            "views": views,
        }
        if protected:
            final["protected"] = True
        if post_id:
            final["id"] = int(post_id) if post_id.isdigit() else post_id
        if item_meta.get("url"):
            final["url"] = normalize_url_path(item_meta["url"])
            final["canonical"] = item_meta.get("canonical", "https://www.laumy.tech" + item_meta["url"])
        elif fm.get("url"):
            final["url"] = normalize_url_path(fm["url"])
            final["canonical"] = fm.get("canonical") or SITE_BASE_URL + final["url"]
        elif protected:
            final["url"] = default_post_url(cats, src, fm)
            final["canonical"] = SITE_BASE_URL + final["url"]

        if protected:
            protected_routes.append({"url": final.get("url", ""), "assets": asset_prefix})

        pageview_path = normalize_url_path(final.get("url") or fallback_post_url(cats, dst))
        if pageview_path:
            pageview_paths.append(pageview_path)

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
    (site / "static" / "pageview-paths.json").write_text(
        json.dumps({"paths": sorted(set(pageview_paths))}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (site / "static" / "llms.txt").write_text(
        "# laumy的学习笔记\n\n"
        "这是一个中文技术博客，主要内容包括 Linux、嵌入式、AI 大模型、网络协议、机器人系统等。\n\n"
        "Sitemap: https://www.laumy.tech/sitemap.xml\n"
        "RSS: https://www.laumy.tech/index.xml\n"
        "Archive: https://www.laumy.tech/\n",
        encoding="utf-8",
    )
    if args.protected_nginx_output:
        write_protected_nginx(
            Path(args.protected_nginx_output).resolve(),
            protected_routes,
            args.protected_auth_file,
            args.protected_assets_root,
        )
    print(f"Generated {generated} Hugo posts ({len(protected_routes)} protected)")


if __name__ == "__main__":
    main()
