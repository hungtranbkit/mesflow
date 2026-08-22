// Hướng dẫn sử dụng bằng chữ -- bổ sung bên cạnh hệ thống Video hướng dẫn có
// sẵn (app.js: renderTutorials/renderEspKioskTutorial/attachGuideTabs).
//
// This file only ADDS behavior; it never edits app.js. It works by
// reassigning two globals app.js already declared as plain `function`
// statements (loaded in a classic <script>, so later assignment wins, the
// same technique pages/production-trace.js already uses for openPage):
//
//   renderTutorials  -- was "KIMEX video list body"; sidebar's openPage('tutorials')
//                        calls this by name. We capture the original under
//                        renderVideoGuideKimex, then repoint renderTutorials
//                        at the new hub (defaults to the text guide).
//   attachGuideTabs   -- was "wrap #content with the KIMEX/ESP inner tab bar".
//                        We reproduce it verbatim (so the inner tab bar is
//                        pixel-identical) but retarget its KIMEX button at
//                        renderVideoGuideKimex instead of the now-repointed
//                        renderTutorials, and additionally wrap the result
//                        with the new outer [Hướng dẫn bằng chữ][Video hướng
//                        dẫn] tab bar. renderEspKioskTutorial() (unchanged,
//                        still in app.js) calls this same attachGuideTabs at
//                        the end of its body, so the ESP tab gets the outer
//                        wrap for free.
//
// Net effect: the existing video tutorial system (manifest fetch, player,
// KIMEX/ESP sub-tabs, search/category filter) is untouched byte-for-byte --
// only reachable one click deeper, behind the new "Video hướng dẫn" tab.

const renderVideoGuideKimex = renderTutorials;

function guideTabBar(tabs, active) {
  // One nav-tab bar, built the exact way app.js's attachGuideTabs already
  // does -- re-parents whatever render already put into #content, so every
  // element id inside stays valid (nothing is destroyed, only re-nested).
  const inner = content.firstElementChild;
  const nav = document.createElement('nav');
  nav.className = 'guide-tabs mf-tabs';
  nav.innerHTML = tabs.map(t => `<button type="button" class="mf-tab ${t.key === active ? 'active' : ''}" data-tab="${t.key}">${esc(t.label)}</button>`).join('');
  [...nav.querySelectorAll('button')].forEach((btn, i) => { btn.onclick = tabs[i].onclick; });
  const shell = document.createElement('div');
  shell.className = 'page-shell';
  shell.appendChild(nav);
  if (inner) shell.appendChild(inner);
  content.innerHTML = '';
  content.appendChild(shell);
}

function attachTopGuideTabs(active) {
  guideTabBar([
    { key: 'text', label: 'Hướng dẫn bằng chữ', onclick: () => renderTextGuide() },
    { key: 'video', label: 'Video hướng dẫn', onclick: () => renderVideoGuideKimex() },
  ], active);
  if (window.AppNav?.setQuery) AppNav.setQuery({ tab: active === 'video' ? 'video' : null });
}

// Full reproduction of app.js's original attachGuideTabs, retargeted at
// renderVideoGuideKimex (not the now-repointed renderTutorials) and wrapped
// one level deeper with the new outer Text/Video tabs.
attachGuideTabs = function (active) {
  guideTabBar([
    { key: 'mesflow', label: 'KIMEX', onclick: () => renderVideoGuideKimex() },
    { key: 'esp', label: 'ESP Kiosk', onclick: () => renderEspKioskTutorial() },
  ], active);
  attachTopGuideTabs('video');
};

let guideData = null;
async function loadGuideData() {
  if (guideData) return guideData;
  const v = document.getElementById('version')?.textContent || '';
  const response = await fetch(`/static/guides/user-guide.vi.json?v=${encodeURIComponent(v)}`, { credentials: 'same-origin' });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  guideData = await response.json();
  return guideData;
}

function stripDiacritics(s) {
  return String(s || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
}

function guideBlockHtml(block) {
  switch (block.type) {
    case 'h3': return `<h3>${esc(block.text)}</h3>`;
    case 'p': return `<p>${esc(block.text)}</p>`;
    case 'note': return `<div class="guide-note">${esc(block.text)}</div>`;
    case 'example': return `<div class="guide-example"><span>Ví dụ</span>${esc(block.text).replace(/\n/g, '<br>')}</div>`;
    case 'diagram': return `<pre class="guide-diagram">${esc(block.text)}</pre>`;
    case 'list': return `<ul>${(block.items || []).map(x => `<li>${esc(x)}</li>`).join('')}</ul>`;
    case 'steps': return `<ol class="guide-steps">${(block.items || []).map(x => `<li>${esc(x)}</li>`).join('')}</ol>`;
    case 'table': return `<div class="table-wrap guide-table-wrap"><table><thead><tr>${(block.headers || []).map(h => `<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${(block.rows || []).map(row => `<tr>${row.map(cell => `<td>${esc(cell)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
    default: return '';
  }
}

function guideBlockText(block) {
  // Flat searchable text for a block, regardless of shape.
  return [block.text, ...(block.items || []), ...(block.headers || []), ...((block.rows || []).flat())].filter(Boolean).join(' ');
}

async function renderTextGuide() {
  title.textContent = 'Hướng dẫn';
  subtitle.textContent = 'Tài liệu hướng dẫn thao tác và ý nghĩa dữ liệu trong hệ thống.';
  content.innerHTML = `<div class="text-guide-shell">
    <section class="text-guide-hero">
      <h1>Hướng dẫn sử dụng MESFlow</h1>
      <p>Tài liệu hướng dẫn thao tác và ý nghĩa dữ liệu trong hệ thống.</p>
      <div class="text-guide-search"><input id="guideSearch" data-testid="guide-search" type="search" placeholder="Tìm trong hướng dẫn..." autocomplete="off"></div>
    </section>
    <div id="guideEmpty" class="empty" hidden><b>Không tải được nội dung hướng dẫn.</b><span></span></div>
    <div class="text-guide-layout" id="guideLayout" hidden>
      <details class="text-guide-toc" id="guideTocWrap" open>
        <summary>Mục lục</summary>
        <nav id="guideToc" aria-label="Mục lục hướng dẫn"></nav>
      </details>
      <main class="text-guide-content" id="guideContent"></main>
    </div>
  </div>`;
  attachTopGuideTabs('text');

  let data;
  try { data = await loadGuideData(); }
  catch (e) {
    const empty = document.getElementById('guideEmpty');
    empty.hidden = false;
    empty.querySelector('span').textContent = e.message || 'Không đọc được tài liệu hướng dẫn.';
    return;
  }
  const sections = data.sections || [];
  const layout = document.getElementById('guideLayout');
  const toc = document.getElementById('guideToc');
  const contentHost = document.getElementById('guideContent');
  layout.hidden = false;

  toc.innerHTML = sections.map(s => `<a href="#guide-${esc(s.id)}" data-goto="${esc(s.id)}">${esc(s.title)}</a>`).join('');
  contentHost.innerHTML = sections.map(s => `<details class="guide-card" id="guide-${esc(s.id)}" open>
      <summary><h2>${esc(s.title)}</h2></summary>
      <div class="guide-card-body">${(s.content || []).map(guideBlockHtml).join('')}</div>
    </details>`).join('');

  const cards = [...contentHost.querySelectorAll('.guide-card')];
  const gotoSection = id => {
    const card = document.getElementById(`guide-${id}`);
    if (!card) return;
    card.open = true;
    card.scrollIntoView({ behavior: 'smooth', block: 'start' });
    if (window.matchMedia('(max-width: 900px)').matches) document.getElementById('guideTocWrap').open = false;
  };
  toc.querySelectorAll('[data-goto]').forEach(a => a.addEventListener('click', e => { e.preventDefault(); gotoSection(a.dataset.goto); }));

  const search = document.getElementById('guideSearch');
  const draw = () => {
    const raw = (search.value || '').trim();
    const q = stripDiacritics(raw);
    let matchCount = 0;
    cards.forEach(card => {
      const s = sections.find(x => `guide-${x.id}` === card.id);
      const haystack = stripDiacritics([s.title, ...(s.keywords || []), ...(s.content || []).map(guideBlockText)].join(' '));
      const match = !q || haystack.includes(q);
      card.hidden = !match;
      if (match) matchCount += 1;
    });
    toc.querySelectorAll('[data-goto]').forEach(a => {
      const card = document.getElementById(`guide-${a.dataset.goto}`);
      a.classList.toggle('is-hidden', !!card?.hidden);
    });
    contentHost.dataset.emptySearch = matchCount === 0 && q ? '1' : '';
  };
  search.oninput = draw;

  // Deep link: ?page=tutorials&tab=text#guide-<id> opens straight on that
  // section (the fetch above is async, so the browser's own hash-scroll on
  // load can miss the target -- do it ourselves once content exists).
  const hashId = (location.hash || '').replace(/^#guide-/, '');
  if (hashId && document.getElementById(`guide-${hashId}`)) gotoSection(hashId);
}

// Sidebar's "Hướng dẫn" item calls openPage('tutorials') -> renderTutorials()
// by name (app.js, unchanged). Repoint it at the new hub now that
// renderVideoGuideKimex above has already captured the original body, and
// now that renderTextGuide is defined. Defaults to the text guide unless the
// current URL already asked for the video tab (deep link / tab switch).
renderTutorials = function () {
  const wantsVideo = new URLSearchParams(location.search).get('tab') === 'video';
  return wantsVideo ? renderVideoGuideKimex() : renderTextGuide();
};
