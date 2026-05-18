const serverMeta = document.querySelector('meta[name="waline-server"]');
const serverURL = serverMeta?.content?.trim();

if (serverURL) {
  const pageviewSelector = '.waline-pageview-count';
  const commentSelector = '.waline-comment-count';
  const updateCurrent = document.body.dataset.walineCurrent === 'true';
  const currentPath =
    document.querySelector(`${pageviewSelector}[data-path]`)?.dataset.path ||
    decodeURIComponent(window.location.pathname);
  const shouldUpdatePageview = updateCurrent && markPageviewVisit(currentPath);

  function markPageviewVisit(path) {
    try {
      const key = `laumy:pageview:${path}`;
      if (localStorage.getItem(key)) return false;
      localStorage.setItem(key, String(Date.now()));
      return true;
    } catch {
      return true;
    }
  }

  if (document.querySelector(pageviewSelector)) {
    import('/vendor/waline/pageview.js')
      .then(({ pageviewCount }) => {
        pageviewCount({
          serverURL,
          selector: pageviewSelector,
          path: currentPath,
          update: shouldUpdatePageview,
        });
      })
      .catch(() => {});
  }

  if (document.querySelector(commentSelector)) {
    import('/vendor/waline/comment.js')
      .then(({ commentCount }) => {
        commentCount({
          serverURL,
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
            serverURL,
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
