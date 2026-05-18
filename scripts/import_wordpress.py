#!/usr/bin/env python3
import argparse
import json
import re
import shutil
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from urllib.parse import urlparse, unquote

NS = {
    "content": "http://purl.org/rss/1.0/modules/content/",
    "dc": "http://purl.org/dc/elements/1.1/",
    "excerpt": "http://wordpress.org/export/1.2/excerpt/",
    "wp": "http://wordpress.org/export/1.2/",
}


def text(node, path, default=""):
    found = node.find(path, NS)
    return found.text if found is not None and found.text is not None else default


def clean_name(name):
    name = unescape(name or "").strip()
    name = re.sub(r"^[0-9]+(?:\.[0-9]+)*[-_.、\s]*", "", name)
    return name or "未分类"


def file_safe(name):
    name = clean_name(name)
    name = re.sub(r"[\\/:*?\"<>|]+", "-", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name[:80] or "untitled"


def first_image(html):
    match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', html or "", re.I)
    if not match:
        return ""
    src = match.group(1)
    parsed = urlparse(src)
    if parsed.netloc.endswith("laumy.tech"):
        return parsed.path
    return src


def strip_html(html):
    html = re.sub(r"<script.*?</script>", "", html or "", flags=re.S | re.I)
    html = re.sub(r"<style.*?</style>", "", html, flags=re.S | re.I)
    html = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", unescape(html)).strip()


def yaml_value(value):
    return json.dumps(value, ensure_ascii=False)


def write_markdown(out_dir, record):
    category = record["category"] or "未分类"
    target_dir = out_dir / file_safe(category)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{record['id']}-{file_safe(record['title'])}.md"
    fm = {
        "id": int(record["id"]) if str(record["id"]).isdigit() else record["id"],
        "title": record["title"],
        "date": record["date"],
        "modified": record["modified"],
        "tags": record.get("tags", []),
        "status": record.get("status", "publish"),
        "author": record.get("author", "laumy"),
    }
    lines = ["---"]
    for key, value in fm.items():
        if value == "" or value == []:
            continue
        lines.append(f"{key}: {yaml_value(value)}")
    lines.extend(["---", "", f"# {record['title']}", "", record["content"].strip(), ""])
    target.write_text("\n".join(lines), encoding="utf-8")
    record["source"] = str(target.relative_to(out_dir))
    return record


def write_post(out_dir, item):
    post_id = text(item, "wp:post_id")
    title = text(item, "title").strip() or f"post-{post_id}"
    status = text(item, "wp:status")
    post_type = text(item, "wp:post_type")
    if post_type not in {"post", "page"}:
        return None

    link = text(item, "link")
    parsed = urlparse(link)
    old_path = unquote(parsed.path)
    date = text(item, "wp:post_date_gmt") or text(item, "wp:post_date")
    modified = text(item, "wp:post_modified_gmt") or date
    content = text(item, "content:encoded")
    excerpt = text(item, "excerpt:encoded") or strip_html(content)[:180]
    creator = text(item, "dc:creator", "laumy")

    cats = []
    tags = []
    for cat in item.findall("category"):
        domain = cat.attrib.get("domain", "")
        value = (cat.text or "").strip()
        if not value:
            continue
        if domain == "category":
            cats.append(clean_name(value))
        elif domain == "post_tag":
            tags.append(clean_name(value))
    category = cats[0] if cats else "未分类"

    record = {
        "id": str(post_id),
        "title": title,
        "date": f"{date.replace(' ', 'T')}+00:00" if date else "",
        "modified": f"{modified.replace(' ', 'T')}+00:00" if modified else "",
        "tags": tags,
        "status": status,
        "author": creator,
        "content": content,
        "url": old_path,
        "canonical": link,
        "description": excerpt,
        "cover": first_image(content),
        "category": category,
        "categories": cats,
    }
    write_markdown(out_dir, record)

    return {
        "id": str(post_id),
        "title": title,
        "url": old_path,
        "canonical": link,
        "description": excerpt,
        "cover": first_image(content),
        "category": category,
        "categories": cats,
        "tags": tags,
        "status": status,
        "date": record.get("date", ""),
        "modified": record.get("modified", ""),
        "source": record.get("source", ""),
    }


def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "laumy-migration/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def import_from_api(base_url, out_dir):
    categories = {c["id"]: c["name"] for c in fetch_json(f"{base_url}/wp-json/wp/v2/categories?per_page=100")}
    tags_by_id = {t["id"]: t["name"] for t in fetch_json(f"{base_url}/wp-json/wp/v2/tags?per_page=100")}
    users = {u["id"]: u.get("name") or u.get("slug") or "laumy" for u in fetch_json(f"{base_url}/wp-json/wp/v2/users?per_page=100")}
    meta = {}
    page = 1
    while True:
        try:
            posts = fetch_json(f"{base_url}/wp-json/wp/v2/posts?per_page=100&page={page}&status=publish")
        except Exception:
            break
        if not posts:
            break
        for post in posts:
            post_id = str(post["id"])
            content = post.get("content", {}).get("rendered", "")
            yoast = post.get("yoast_head_json") or {}
            cats = [categories.get(cid, "未分类") for cid in post.get("categories", [])]
            tags = [tags_by_id.get(tid, "") for tid in post.get("tags", []) if tags_by_id.get(tid)]
            category = cats[0] if cats else "未分类"
            link = post.get("link", "")
            old_path = unquote(urlparse(link).path)
            record = {
                "id": post_id,
                "title": unescape(post.get("title", {}).get("rendered", "")).strip() or f"post-{post_id}",
                "date": post.get("date_gmt", post.get("date", "")).replace("Z", "") + "+00:00",
                "modified": post.get("modified_gmt", post.get("modified", "")).replace("Z", "") + "+00:00",
                "tags": tags,
                "status": "publish",
                "author": users.get(post.get("author"), "laumy"),
                "content": content,
                "url": old_path,
                "canonical": yoast.get("canonical") or link,
                "description": strip_html(yoast.get("og_description") or post.get("excerpt", {}).get("rendered", "") or content)[:180],
                "cover": (yoast.get("og_image") or [{}])[0].get("url", "") if isinstance(yoast.get("og_image"), list) else first_image(content),
                "category": category,
                "categories": cats,
            }
            if record["cover"]:
                parsed = urlparse(record["cover"])
                if parsed.netloc.endswith("laumy.tech"):
                    record["cover"] = parsed.path
            write_markdown(out_dir, record)
            meta[post_id] = {k: v for k, v in record.items() if k != "content"}
        page += 1
    return meta


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--wxr", help="WordPress WXR XML export")
    parser.add_argument("--wp-api", help="WordPress base URL, for example https://www.laumy.tech")
    parser.add_argument("--content", required=True, help="Output laumy-notes-content directory")
    parser.add_argument("--site", required=True, help="laumy-site directory")
    parser.add_argument("--uploads", help="Optional wp-content/uploads source")
    args = parser.parse_args()

    content_dir = Path(args.content)
    site_dir = Path(args.site)
    data_dir = site_dir / "data"
    if content_dir.exists():
        shutil.rmtree(content_dir)
    content_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)

    drafts = 0
    if args.wp_api:
        meta = import_from_api(args.wp_api.rstrip("/"), content_dir)
        imported = len(meta)
    elif args.wxr:
        tree = ET.parse(args.wxr)
        channel = tree.getroot().find("channel")
        meta = {}
        imported = 0
        for item in channel.findall("item"):
            status = text(item, "wp:status")
            post_type = text(item, "wp:post_type")
            if post_type not in {"post", "page"}:
                continue
            if status == "publish":
                result = write_post(content_dir, item)
                if result:
                    meta[result["id"]] = result
                    imported += 1
            elif status == "draft":
                drafts += 1
    else:
        raise SystemExit("Either --wp-api or --wxr is required")

    (data_dir / "export-meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    stats = {
        "total_views": 0,
        "posts": {post_id: {"views": 0} for post_id in meta},
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    (data_dir / "post-stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")

    category_map = {}
    for item in meta.values():
        category_map.setdefault(item["category"], {"slug": ""})
    (data_dir / "category-map.yaml").write_text(
        "\n".join(f"{name}:\n  slug: \"\"" for name in sorted(category_map)) + "\n",
        encoding="utf-8",
    )

    if args.uploads:
        src = Path(args.uploads)
        dst = site_dir / "static" / "wp-content" / "uploads"
        if src.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)

    print(f"Imported {imported} published items into {content_dir}")
    if drafts:
        print(f"Skipped {drafts} drafts")


if __name__ == "__main__":
    main()
