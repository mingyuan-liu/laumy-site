#!/usr/bin/env python3
import argparse
import json
import re
import shutil
import subprocess
from collections import defaultdict
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from urllib.parse import unquote, urlparse

CATEGORY_ORDER = [
    "Linux",
    "RISC-V",
    "RTOS",
    "AI",
    "ROS系统",
    "前后端",
    "外设",
    "网络",
    "调试",
    "语言",
    "阅读",
    "其他",
]

CATEGORY_ALIASES = {"Ai": "AI", "linux": "Linux"}


def strip_number(name):
    return re.sub(r"^[0-9]+(?:\.[0-9]+)*[-_.、\s]*", "", (name or "").strip()) or "未分类"


def safe_name(name):
    name = strip_number(unescape(str(name)))
    name = re.sub(r"[\\/:*?\"<>|]+", "-", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name[:96] or "untitled"


def canonical_category(name):
    name = strip_number(name)
    return CATEGORY_ALIASES.get(name, name if name in CATEGORY_ORDER else "其他")


def category_depth(term_taxonomy_id, tax_by_tt, term_by_id):
    depth = 0
    cur = tax_by_tt.get(term_taxonomy_id)
    while cur and cur.get("parent"):
        depth += 1
        parent_term = cur["parent"]
        cur = next((t for t in tax_by_tt.values() if t["term_id"] == parent_term and t["taxonomy"] == "category"), None)
    return depth


def category_path_from_tt(term_taxonomy_id, tax_by_tt, term_by_id):
    cur = tax_by_tt.get(term_taxonomy_id)
    parts = []
    while cur:
        term = term_by_id.get(cur["term_id"])
        if term:
            parts.append(canonical_category(term["name"]) if not cur.get("parent") else strip_number(term["name"]))
        if not cur.get("parent"):
            break
        parent_term = cur["parent"]
        cur = next((t for t in tax_by_tt.values() if t["term_id"] == parent_term and t["taxonomy"] == "category"), None)
    return list(reversed(parts)) or ["其他"]


def yaml_value(value):
    return json.dumps(value, ensure_ascii=False)


def sql_unescape(value):
    out = []
    i = 0
    while i < len(value):
        ch = value[i]
        if ch == "\\" and i + 1 < len(value):
            nxt = value[i + 1]
            out.append({
                "0": "\0",
                "n": "\n",
                "r": "\r",
                "t": "\t",
                "b": "\b",
                "Z": "\x1a",
            }.get(nxt, nxt))
            i += 2
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def parse_values(values):
    rows = []
    i = 0
    n = len(values)
    while i < n:
        while i < n and values[i] not in "(":
            i += 1
        if i >= n:
            break
        i += 1
        row = []
        token = []
        in_str = False
        quoted = False
        while i < n:
            ch = values[i]
            if in_str:
                if ch == "\\" and i + 1 < n:
                    token.append(ch)
                    token.append(values[i + 1])
                    i += 2
                    continue
                if ch == "'":
                    in_str = False
                    i += 1
                    continue
                token.append(ch)
                i += 1
                continue
            if ch == "'":
                in_str = True
                quoted = True
                i += 1
                continue
            if ch == ",":
                raw = "".join(token).strip()
                row.append(sql_unescape(raw) if quoted else convert_atom(raw))
                token = []
                quoted = False
                i += 1
                continue
            if ch == ")":
                raw = "".join(token).strip()
                row.append(sql_unescape(raw) if quoted else convert_atom(raw))
                rows.append(row)
                i += 1
                break
            token.append(ch)
            i += 1
    return rows


def convert_atom(raw):
    if raw.upper() == "NULL":
        return None
    if re.fullmatch(r"-?\d+", raw or ""):
        return int(raw)
    return raw


def read_columns(sql_path, tables):
    columns = {}
    current = None
    with sql_path.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            m = re.match(r"CREATE TABLE `([^`]+)`", line)
            if m and m.group(1) in tables:
                current = m.group(1)
                columns[current] = []
                continue
            if current:
                if line.startswith(")"):
                    current = None
                    continue
                m = re.match(r"\s*`([^`]+)`", line)
                if m:
                    columns[current].append(m.group(1))
    return columns


def iter_table_rows(sql_path, table, cols):
    prefix = f"INSERT INTO `{table}` VALUES "
    with sql_path.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            if not line.startswith(prefix):
                continue
            values = line[len(prefix):].rstrip().rstrip(";")
            for row in parse_values(values):
                yield dict(zip(cols, row))


def strip_html(html):
    html = re.sub(r"<script.*?</script>", "", html or "", flags=re.S | re.I)
    html = re.sub(r"<style.*?</style>", "", html, flags=re.S | re.I)
    html = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", unescape(html)).strip()


def html_to_markdown(content):
    content = content or ""
    if not re.search(r"</?[a-zA-Z][^>]*>", content):
        return content
    content = re.sub(
        r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>\s*<img\b[^>]*src=["\']([^"\']+)["\'][^>]*(?:alt=["\']([^"\']*)["\'])?[^>]*>\s*</a>',
        lambda m: f"\n\n![{m.group(3) or ''}]({m.group(2) or m.group(1)})\n\n",
        content,
        flags=re.I | re.S,
    )
    content = re.sub(
        r'<img\b[^>]*src=["\']([^"\']+)["\'][^>]*(?:alt=["\']([^"\']*)["\'])?[^>]*>',
        lambda m: f"\n\n![{m.group(2) or ''}]({m.group(1)})\n\n",
        content,
        flags=re.I | re.S,
    )
    try:
        proc = subprocess.run(
            ["pandoc", "-f", "html", "-t", "gfm", "--wrap=none"],
            input=content,
            text=True,
            capture_output=True,
            check=True,
        )
        out = proc.stdout.strip()
        out = out.replace("\\![", "![")
        out = out.replace("\\]", "]")
        out = out.replace("\\$", "$")
        out = re.sub(r"(!\[[^\]]*\]\([^)]+\))\s+", r"\1\n\n", out)
        return out
    except Exception:
        return content


def localize_assets(markdown, post_id, source_uploads, assets_dir):
    if not source_uploads:
        return markdown
    uploads = Path(source_uploads)
    if not uploads.exists():
        return markdown
    assets_dir.mkdir(parents=True, exist_ok=True)

    def repl(match):
        alt = match.group(1)
        url = match.group(2)
        parsed = urlparse(url)
        if not parsed.netloc.endswith("laumy.tech") and not parsed.path.startswith("/wp-content/uploads/"):
            return match.group(0)
        path = unquote(parsed.path)
        prefix = "/wp-content/uploads/"
        if prefix not in path:
            return match.group(0)
        rel = path.split(prefix, 1)[1]
        src = uploads / rel
        if not src.exists():
            return match.group(0)
        dst_name = f"{post_id}-{src.name}"
        dst = assets_dir / dst_name
        if not dst.exists():
            shutil.copy2(src, dst)
        return f"![{alt}](./assets/{dst_name})"

    return re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", repl, markdown)


def first_image(html):
    m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', html or "", flags=re.I)
    if not m:
        return ""
    src = m.group(1)
    parsed = urlparse(src)
    if parsed.netloc.endswith("laumy.tech"):
        return parsed.path
    return src


def iso_utc(value):
    if not value or value == "0000-00-00 00:00:00":
        return "2000-01-01T00:00:00+00:00"
    return value.replace(" ", "T") + "+00:00"


def post_url(post):
    slug = post.get("post_name") or ""
    return f"/{post['ID']}.html/{unquote(slug)}/"


def write_index(path, title, pos, slug=None):
    path.mkdir(parents=True, exist_ok=True)
    (path / "index.md").write_text(
        f"---\nsidebar_position: {pos}\nslug: /{slug or safe_name(title).lower()}\n---\n\n# {title}\n",
        encoding="utf-8",
    )


def write_post(path, post, tags, source_uploads=None):
    title = unescape(post["post_title"] or f"post-{post['ID']}")
    body = post["post_content"] or ""
    if not body.strip() and post.get("post_password"):
        body = "> 此文章在 WordPress 中为密码保护状态，数据库导出未包含正文。"
    else:
        body = html_to_markdown(body)
        body = localize_assets(body, post["ID"], source_uploads, path.parent / "assets")
    fm = {
        "id": post["ID"],
        "title": title,
        "date": iso_utc(post.get("post_date_gmt") or post.get("post_date")),
        "modified": iso_utc(post.get("post_modified_gmt") or post.get("post_modified")),
        "tags": tags,
        "status": post["post_status"],
        "author": "laumy",
    }
    lines = ["---"]
    for k, v in fm.items():
        if v == []:
            continue
        lines.append(f"{k}: {yaml_value(v)}")
    lines += ["---", "", f"# {title}", "", body.strip(), ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sql", required=True)
    ap.add_argument("--content", required=True)
    ap.add_argument("--site", required=True)
    ap.add_argument("--uploads")
    args = ap.parse_args()

    sql = Path(args.sql)
    content = Path(args.content)
    site = Path(args.site)
    if content.exists():
        shutil.rmtree(content)
    content.mkdir(parents=True)
    (site / "data").mkdir(parents=True, exist_ok=True)

    tables = {
        "wp_posts", "wp_postmeta", "wp_terms", "wp_term_taxonomy", "wp_term_relationships",
        "wp_yoast_indexable", "wp_slim_stats"
    }
    cols = read_columns(sql, tables)
    terms = {r["term_id"]: r for r in iter_table_rows(sql, "wp_terms", cols["wp_terms"])}
    tax = {r["term_taxonomy_id"]: r for r in iter_table_rows(sql, "wp_term_taxonomy", cols["wp_term_taxonomy"])}
    category_tax = {k: v for k, v in tax.items() if v["taxonomy"] == "category"}
    rels = defaultdict(list)
    for r in iter_table_rows(sql, "wp_term_relationships", cols["wp_term_relationships"]):
        rels[r["object_id"]].append(r["term_taxonomy_id"])

    yoast = {}
    if "wp_yoast_indexable" in cols:
        for r in iter_table_rows(sql, "wp_yoast_indexable", cols["wp_yoast_indexable"]):
            if r.get("object_type") == "post" and r.get("object_id"):
                yoast[int(r["object_id"])] = r

    views = defaultdict(int)
    meta_view_keys = ("post_views_count", "views", "view_count", "_views")
    meta_views = {}
    if "wp_postmeta" in cols:
        for r in iter_table_rows(sql, "wp_postmeta", cols["wp_postmeta"]):
            pid = r.get("post_id")
            key = r.get("meta_key")
            if not isinstance(pid, int) or key not in meta_view_keys or pid in meta_views:
                continue
            try:
                value = int(str(r.get("meta_value") or "0").replace(",", ""))
            except ValueError:
                value = 0
            if value > 0:
                meta_views[pid] = value

    if "wp_slim_stats" in cols:
        for r in iter_table_rows(sql, "wp_slim_stats", cols["wp_slim_stats"]):
            pid = r.get("post_id") or r.get("content_id")
            if isinstance(pid, int) and pid > 0:
                views[pid] += 1
    views.update(meta_views)

    published = []
    drafts = []
    for post in iter_table_rows(sql, "wp_posts", cols["wp_posts"]):
        if post.get("post_type") != "post":
            continue
        if post.get("post_status") == "publish":
            published.append(post)
        elif post.get("post_status") == "draft":
            drafts.append(post)

    category_dirs = {}
    for idx, cat in enumerate(CATEGORY_ORDER, 1):
        dirname = f"{idx:02d}-{cat}"
        category_dirs[cat] = content / dirname
        write_index(category_dirs[cat], cat, idx, slug=safe_name(cat).lower())

    child_dirs = {}
    child_orders = defaultdict(dict)
    for root_idx, root in enumerate(CATEGORY_ORDER, 1):
        children = []
        root_term_ids = [t["term_id"] for t in terms.values() if canonical_category(t["name"]) == root]
        for tt in category_tax.values():
            if tt.get("parent") in root_term_ids:
                term = terms.get(tt["term_id"])
                if term:
                    children.append(strip_number(term["name"]))
        for child_idx, child in enumerate(sorted(set(children)), 1):
            child_orders[root][child] = child_idx
            child_dir = category_dirs[root] / f"{root_idx}.{child_idx}-{safe_name(child)}"
            child_dirs[(root, child)] = child_dir
            write_index(child_dir, child, child_idx, slug=f"{safe_name(root).lower()}/{safe_name(child).lower()}")

    seq = defaultdict(int)
    meta = {}
    stats = {"total_views": 0, "posts": {}}
    for post in sorted(published, key=lambda p: (p.get("post_date") or "", p["ID"])):
        category_tt_ids = []
        cats = []
        tags = []
        for tid in rels.get(post["ID"], []):
            t = tax.get(tid)
            if not t:
                continue
            term = terms.get(t["term_id"])
            if not term:
                continue
            if t["taxonomy"] == "category":
                category_tt_ids.append(tid)
                cats.append(term["name"])
            elif t["taxonomy"] == "post_tag":
                tags.append(term["name"])
        if category_tt_ids:
            chosen_tt = sorted(
                category_tt_ids,
                key=lambda tid: (-category_depth(tid, category_tax, terms), category_path_from_tt(tid, category_tax, terms)),
            )[0]
            cat_path = category_path_from_tt(chosen_tt, category_tax, terms)
        else:
            cat_path = ["其他"]
        root_cat = canonical_category(cat_path[0])
        child_cat = cat_path[1] if len(cat_path) > 1 else ""
        cat_index = CATEGORY_ORDER.index(root_cat) + 1
        if child_cat:
            child_idx = child_orders[root_cat].get(child_cat, len(child_orders[root_cat]) + 1)
            if (root_cat, child_cat) not in child_dirs:
                child_orders[root_cat][child_cat] = child_idx
                child_dirs[(root_cat, child_cat)] = category_dirs[root_cat] / f"{cat_index}.{child_idx}-{safe_name(child_cat)}"
                write_index(child_dirs[(root_cat, child_cat)], child_cat, child_idx)
            base_dir = child_dirs[(root_cat, child_cat)]
            seq_key = f"{root_cat}/{child_cat}"
            seq[seq_key] += 1
            number = f"{cat_index}.{child_idx}.{seq[seq_key]}"
        else:
            base_dir = category_dirs[root_cat]
            seq_key = root_cat
            seq[seq_key] += 1
            number = f"{cat_index}.{seq[seq_key]}"
        target = base_dir / f"{number}-{safe_name(post['post_title'])}.md"
        write_post(target, post, tags, args.uploads)

        y = yoast.get(post["ID"], {})
        url = post_url(post)
        cover = y.get("open_graph_image") or first_image(post.get("post_content") or "")
        if cover:
            parsed = urlparse(cover)
            if parsed.netloc.endswith("laumy.tech"):
                cover = parsed.path
        desc = y.get("description") or y.get("open_graph_description") or post.get("post_excerpt") or strip_html(post.get("post_content"))[:180]
        canonical = y.get("canonical") or ("https://www.laumy.tech" + url)
        meta[str(post["ID"])] = {
            "id": post["ID"],
            "title": unescape(post["post_title"] or ""),
            "url": url,
            "canonical": canonical,
            "description": desc,
            "cover": cover,
            "category": child_cat or root_cat,
            "category_path": cat_path,
            "root_category": root_cat,
            "raw_categories": cats,
            "tags": tags,
            "date": iso_utc(post.get("post_date_gmt") or post.get("post_date")),
            "modified": iso_utc(post.get("post_modified_gmt") or post.get("post_modified")),
            "source": str(target.relative_to(content)),
        }
        stats["posts"][str(post["ID"])] = {"views": views.get(post["ID"], 0)}
        stats["total_views"] += views.get(post["ID"], 0)

    (site / "data" / "export-meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    stats["generated_at"] = datetime.now(timezone.utc).isoformat()
    (site / "data" / "post-stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    (site / "data" / "category-map.yaml").write_text(
        "\n".join(f"{cat}:\n  slug: \"{safe_name(cat).lower()}\"" for cat in CATEGORY_ORDER) + "\n",
        encoding="utf-8",
    )

    if args.uploads:
        src = Path(args.uploads)
        dst = site / "static" / "wp-content" / "uploads"
        if dst.exists():
            shutil.rmtree(dst)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dst)

    print(f"Imported {len(published)} published posts and {len(drafts)} drafts from SQL")


if __name__ == "__main__":
    main()
