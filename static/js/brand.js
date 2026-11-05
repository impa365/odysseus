// Apply the configured display name (ODYSSEUS_BRAND_NAME, exposed by the
// server as <meta name="app-brand">) to UI text that scripts create at
// runtime. Server-rendered HTML is already branded; chat content, inputs and
// editors are never rewritten.
(function () {
  const meta = document.querySelector('meta[name="app-brand"]');
  const brand = meta && meta.content ? meta.content.trim() : '';
  const DEFAULT = 'Odysseus';
  if (!brand || brand === DEFAULT) return;

  const SKIP = '#chat-history, .msg, pre, code, textarea, [contenteditable="true"], '
    + '.document-editor, .doc-editor, .note-editor, .email-body, script, style';
  const ATTRS = ['title', 'placeholder', 'aria-label', 'alt'];

  const swap = (s) => {
    if (/chat$/i.test(brand)) s = s.split(DEFAULT + ' Chat').join(brand);
    return s.split(DEFAULT).join(brand);
  };

  function fixElementAttrs(el) {
    if (el.closest && el.closest('#chat-history, .msg')) return;
    for (const a of ATTRS) {
      const v = el.getAttribute && el.getAttribute(a);
      if (v && v.includes(DEFAULT)) el.setAttribute(a, swap(v));
    }
  }

  function fixText(node) {
    const parent = node.parentElement;
    if (!parent || parent.closest(SKIP)) return;
    if (node.nodeValue && node.nodeValue.includes(DEFAULT)) node.nodeValue = swap(node.nodeValue);
  }

  function walk(root) {
    if (root.nodeType === Node.TEXT_NODE) { fixText(root); return; }
    if (root.nodeType !== Node.ELEMENT_NODE) return;
    if (root.matches && root.matches('#chat-history')) return;
    fixElementAttrs(root);
    const tw = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT, {
      acceptNode(n) {
        if (n.nodeType === Node.ELEMENT_NODE && n.matches('#chat-history')) return NodeFilter.FILTER_REJECT;
        return NodeFilter.FILTER_ACCEPT;
      },
    });
    let n = tw.nextNode();
    while (n) {
      if (n.nodeType === Node.TEXT_NODE) fixText(n); else fixElementAttrs(n);
      n = tw.nextNode();
    }
  }

  function fixTitle() {
    if (document.title.includes(DEFAULT)) document.title = swap(document.title);
  }

  function start() {
    walk(document.body);
    fixTitle();
    new MutationObserver((records) => {
      for (const r of records) {
        if (r.type === 'childList') r.addedNodes.forEach(walk);
        else if (r.type === 'characterData') fixText(r.target);
        else if (r.type === 'attributes') fixElementAttrs(r.target);
      }
    }).observe(document.body, {
      childList: true, subtree: true, characterData: true,
      attributes: true, attributeFilter: ATTRS,
    });
    const titleEl = document.querySelector('title');
    if (titleEl) new MutationObserver(fixTitle).observe(titleEl, { childList: true, characterData: true, subtree: true });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, { once: true });
  else start();
})();
