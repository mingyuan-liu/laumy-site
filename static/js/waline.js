const serverMeta = document.querySelector('meta[name="waline-server"]');
const serverURL = serverMeta?.content?.trim();

if (serverURL) {
  const normalizedServerURL = normalizeServerURL(serverURL);
  const apiURL = `${normalizedServerURL.replace(/\/?$/, '/')}api/`;
  const pageviewSelector = '.waline-pageview-count';
  const commentSelector = '.waline-comment-count';
  const updateCurrent = document.body.dataset.walineCurrent === 'true';
  const currentPath =
    document.querySelector(`${pageviewSelector}[data-path]`)?.dataset.path ||
    decodeURIComponent(window.location.pathname);

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

  if (document.querySelector(pageviewSelector)) {
    updatePageviews();
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
