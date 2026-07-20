(() => {
  const status = document.querySelector("[data-search-status]");
  const results = document.querySelector("[data-search-results]");
  const query = new URLSearchParams(window.location.search).get("q")?.trim() || "";

  document.querySelectorAll('.search-box input[name="q"]').forEach(input => {
    input.value = query;
  });

  if (!query) {
    status.textContent = "请输入关键词后搜索。";
    return;
  }

  const normalizedQuery = query.toLocaleLowerCase();
  const terms = normalizedQuery.split(/\s+/).filter(Boolean);

  const excerpt = (item) => {
    const text = (item.content || item.summary || "").replace(/\s+/g, " ").trim();
    const lowerText = text.toLocaleLowerCase();
    const positions = terms.map(term => lowerText.indexOf(term)).filter(position => position >= 0);
    const matchAt = positions.length ? Math.min(...positions) : 0;
    const start = Math.max(0, matchAt - 60);
    const end = Math.min(text.length, start + 220);
    return `${start > 0 ? "…" : ""}${text.slice(start, end)}${end < text.length ? "…" : ""}`;
  };

  const score = (item) => {
    const title = (item.title || "").toLocaleLowerCase();
    const category = (item.category || "").toLocaleLowerCase();
    const summary = (item.summary || "").toLocaleLowerCase();
    const content = (item.content || "").toLocaleLowerCase();
    const haystack = `${title}\n${category}\n${summary}\n${content}`;

    if (!terms.every(term => haystack.includes(term))) return 0;

    let value = 1;
    if (title === normalizedQuery) value += 1000;
    for (const term of terms) {
      if (title.includes(term)) value += 100;
      if (category.includes(term)) value += 30;
      if (summary.includes(term)) value += 10;
    }
    return value;
  };

  const renderResult = (item) => {
    const article = document.createElement("article");
    article.className = "search-result";

    const heading = document.createElement("h2");
    const link = document.createElement("a");
    link.href = item.url;
    link.textContent = item.title;
    heading.append(link);

    const description = document.createElement("p");
    description.textContent = excerpt(item);

    const meta = document.createElement("div");
    meta.className = "meta";
    const parts = [item.date, item.category].filter(Boolean);
    meta.textContent = parts.join(" · ");

    article.append(heading, description, meta);
    return article;
  };

  fetch("/index.json", { credentials: "same-origin" })
    .then(response => {
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return response.json();
    })
    .then(index => {
      const matches = index
        .map(item => ({ item, score: score(item) }))
        .filter(match => match.score > 0)
        .sort((a, b) => b.score - a.score || b.item.date.localeCompare(a.item.date));

      status.textContent = matches.length
        ? `找到 ${matches.length} 篇与“${query}”相关的文章`
        : `没有找到与“${query}”相关的文章`;

      const fragment = document.createDocumentFragment();
      matches.forEach(match => fragment.append(renderResult(match.item)));
      results.append(fragment);
    })
    .catch(error => {
      console.error("Search index load failed", error);
      status.textContent = "搜索索引加载失败，请稍后重试。";
    });
})();
