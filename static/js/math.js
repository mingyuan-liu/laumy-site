(function () {
  const mathSelector = '.article-content';
  const ignoredParents = new Set(['SCRIPT', 'STYLE', 'TEXTAREA', 'PRE', 'CODE']);
  let renderStarted = false;

  function normalizeFormula(value) {
    return value
      .replace(/\\_/g, '_')
      .replace(/\\(?=[\[\]])/g, '');
  }

  function normalizeMathText(value) {
    return value
      .replace(/\$\$([\s\S]+?)\$\$/g, (_, body) => `$$${normalizeFormula(body)}$$`)
      .replace(/\\\[([\s\S]+?)\\\]/g, (_, body) => `\\[${normalizeFormula(body)}\\]`)
      .replace(/\\\(([\s\S]+?)\\\)/g, (_, body) => `\\(${normalizeFormula(body)}\\)`)
      .replace(/(^|[^\\])\$([^\n$]+?)\$/g, (_, prefix, body) => `${prefix}$${normalizeFormula(body)}$`);
  }

  function normalizeMathNodes(root) {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode(node) {
        const parent = node.parentElement;
        if (!parent || ignoredParents.has(parent.tagName)) return NodeFilter.FILTER_REJECT;
        return /(\$|\\\[|\\\()/.test(node.nodeValue)
          ? NodeFilter.FILTER_ACCEPT
          : NodeFilter.FILTER_REJECT;
      },
    });

    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);

    nodes.forEach((node) => {
      node.nodeValue = normalizeMathText(node.nodeValue);
    });
  }

  function renderMath() {
    if (renderStarted) return;
    renderStarted = true;

    document.querySelectorAll(mathSelector).forEach((root) => {
      normalizeMathNodes(root);
      if (!window.renderMathInElement) return;

      window.renderMathInElement(root, {
        delimiters: [
          { left: '$$', right: '$$', display: true },
          { left: '\\[', right: '\\]', display: true },
          { left: '\\(', right: '\\)', display: false },
          { left: '$', right: '$', display: false },
        ],
        ignoredTags: ['script', 'noscript', 'style', 'textarea', 'pre', 'code'],
        throwOnError: false,
      });
    });
  }

  window.__laumyRenderMath = renderMath;

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', renderMath, { once: true });
  } else {
    renderMath();
  }
})();
