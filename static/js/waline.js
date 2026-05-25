const serverMeta = document.querySelector('meta[name="waline-server"]');
const serverURL = serverMeta?.content?.trim();

if (serverURL) {
  const normalizedServerURL = normalizeServerURL(serverURL);
  const apiURL = `${normalizedServerURL.replace(/\/?$/, '/')}api/`;
  const pageviewSelector = '.waline-pageview-count';
  const totalPageviewSelector = '[data-waline-total-pageviews]';
  const commentSelector = '.waline-comment-count';
  const updateCurrent = document.body.dataset.walineCurrent === 'true';
  const currentPath =
    document.querySelector(`${pageviewSelector}[data-path]`)?.dataset.path ||
    decodeURIComponent(window.location.pathname);
  const pageviewPathsURL = '/pageview-paths.json';
  const totalPageviewStorageKey = 'laumy:pageview:total:v1';

  function normalizeServerURL(value) {
    const trimmed = value.replace(/\/+$/, '');
    if (/^(https?:)?\/\//i.test(trimmed)) return trimmed;
    if (trimmed.startsWith('/')) return `${window.location.origin}${trimmed}`;
    return `https://${trimmed}`;
  }

  function counterPath(counter) {
    return counter.dataset.path || currentPath;
  }

  function hasPageviewVisit(path) {
    try {
      return localStorage.getItem(`laumy:pageview:v2:${path}`) !== null;
    } catch {
      return false;
    }
  }

  function markPageviewVisit(path) {
    try {
      localStorage.setItem(`laumy:pageview:v2:${path}`, String(Date.now()));
    } catch {}
  }

  function readCounterData(payload, action) {
    if (payload && typeof payload === 'object' && payload.errno) {
      throw new Error(`${action} failed with ${payload.errno}: ${payload.errmsg || ''}`);
    }
    return Array.isArray(payload?.data) ? payload.data : [];
  }

  async function fetchPageviews(paths) {
    const uniquePaths = [...new Set(paths.filter(Boolean))];
    const counts = new Map();
    if (!uniquePaths.length) return counts;

    const response = await fetch(
      `${apiURL}article?path=${encodeURIComponent(uniquePaths.join(','))}&type=time&lang=${encodeURIComponent(navigator.language || 'zh-CN')}`
    );
    const data = readCounterData(await response.json(), 'Get counter');
    uniquePaths.forEach((path, index) => {
      const time = data[index]?.time;
      counts.set(path, typeof time === 'number' ? time : 0);
    });
    return counts;
  }

  async function fetchPageviewPaths() {
    const response = await fetch(pageviewPathsURL, { cache: 'no-store' });
    if (!response.ok) return [];
    const payload = await response.json();
    return Array.isArray(payload?.paths) ? payload.paths : [];
  }

  function delay(ms) {
    return new Promise((resolve) => {
      window.setTimeout(resolve, ms);
    });
  }

  async function fetchPageviewsWithRetry(paths, retries = 1) {
    let lastError;

    for (let attempt = 0; attempt <= retries; attempt += 1) {
      try {
        return await fetchPageviews(paths);
      } catch (error) {
        lastError = error;
        if (attempt < retries) await delay(250 * (attempt + 1));
      }
    }

    throw lastError;
  }

  async function mapWithConcurrency(items, limit, mapper) {
    const results = new Array(items.length);
    let nextIndex = 0;

    async function worker() {
      while (nextIndex < items.length) {
        const index = nextIndex;
        nextIndex += 1;
        results[index] = await mapper(items[index], index);
      }
    }

    await Promise.all(Array.from({ length: Math.min(limit, items.length) }, worker));
    return results;
  }

  async function fetchTotalPageviews(paths) {
    const uniquePaths = [...new Set(paths.filter(Boolean))];
    const batchSize = 25;
    const concurrency = 4;
    const chunks = [];

    for (let index = 0; index < uniquePaths.length; index += batchSize) {
      chunks.push(uniquePaths.slice(index, index + batchSize));
    }

    const countMaps = await mapWithConcurrency(
      chunks,
      concurrency,
      (chunk) => fetchPageviewsWithRetry(chunk)
    );
    let total = 0;
    countMaps.forEach((counts) => {
      counts.forEach((time) => {
        if (typeof time === 'number') total += time;
      });
    });
    return total;
  }

  async function incrementPageview(path) {
    const response = await fetch(`${apiURL}article?lang=${encodeURIComponent(navigator.language || 'zh-CN')}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path, type: 'time', action: 'inc' }),
    });
    const data = readCounterData(await response.json(), 'Update counter');
    const time = data[0]?.time;
    return typeof time === 'number' ? time : null;
  }

  function renderPageviews(counters, counts) {
    counters.forEach((counter) => {
      const time = counts.get(counterPath(counter));
      if (typeof time === 'number') counter.textContent = String(time);
    });
  }

  function cacheTotalPageviews(total) {
    try {
      localStorage.setItem(totalPageviewStorageKey, String(total));
    } catch {}
  }

  function readCachedTotalPageviews() {
    try {
      const cached = localStorage.getItem(totalPageviewStorageKey);
      return /^\d+$/.test(cached || '') ? Number(cached) : null;
    } catch {
      return null;
    }
  }

  function renderTotalPageviews(total, options = {}) {
    if (typeof total !== 'number') return;
    document.querySelectorAll(totalPageviewSelector).forEach((counter) => {
      counter.textContent = String(total);
    });
    if (options.cache !== false) cacheTotalPageviews(total);
  }

  function renderCachedTotalPageviews() {
    renderTotalPageviews(readCachedTotalPageviews(), { cache: false });
  }

  async function updatePageviews() {
    const counters = [...document.querySelectorAll(pageviewSelector)];
    if (!counters.length) return;

    const paths = counters.map(counterPath);
    const shouldUpdatePageview = updateCurrent && currentPath && !hasPageviewVisit(currentPath);

    try {
      if (shouldUpdatePageview) {
        const updatedTime = await incrementPageview(currentPath);
        markPageviewVisit(currentPath);
        const fetchPaths = updatedTime === null ? paths : paths.filter((path) => path !== currentPath);
        const counts = await fetchPageviews(fetchPaths);
        if (updatedTime !== null) counts.set(currentPath, updatedTime);
        renderPageviews(counters, counts);
        return;
      }

      renderPageviews(counters, await fetchPageviews(paths));
    } catch {
      try {
        renderPageviews(counters, await fetchPageviews(paths));
      } catch {}
    }
  }

  async function updateTotalPageviews() {
    if (!document.querySelector(totalPageviewSelector)) return;

    try {
      const paths = await fetchPageviewPaths();
      renderTotalPageviews(await fetchTotalPageviews(paths));
    } catch {}
  }

  const pageviewUpdate = document.querySelector(pageviewSelector) ? updatePageviews() : Promise.resolve();

  if (document.querySelector(totalPageviewSelector)) {
    renderCachedTotalPageviews();
    pageviewUpdate.finally(updateTotalPageviews);
  }

  if (document.querySelector(commentSelector)) {
    import('/vendor/waline/comment.js')
      .then(({ commentCount }) => {
        commentCount({
          serverURL: normalizedServerURL,
          selector: commentSelector,
        });
      })
      .catch(() => {});
  }

  const walineRoot = document.querySelector('#waline');
  if (walineRoot) {
    walineRoot.innerHTML = '<div class="waline-loading">评论加载中...</div>';
    const loadWaline = () => {
      if (walineRoot.dataset.loaded === 'true') return;
      walineRoot.dataset.loaded = 'true';

      const css = document.createElement('link');
      css.rel = 'stylesheet';
      css.href = '/vendor/waline/waline.css';
      document.head.appendChild(css);

      import('/vendor/waline/waline.js')
        .then(({ init }) => {
          walineRoot.innerHTML = '';
          init({
            el: '#waline',
            serverURL: normalizedServerURL,
            path: walineRoot.dataset.path || currentPath,
            lang: 'zh-CN',
            pageview: false,
            comment: commentSelector,
          });
        })
        .catch(() => {
          walineRoot.innerHTML = '<div class="waline-loading">评论暂时无法加载</div>';
        });
    };

    if ('IntersectionObserver' in window) {
      const observer = new IntersectionObserver((entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          observer.disconnect();
          loadWaline();
        }
      }, { rootMargin: '360px 0px' });
      observer.observe(walineRoot);
    } else {
      window.addEventListener('load', loadWaline, { once: true });
    }
  }
}
