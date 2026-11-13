'use strict';
const report = JSON.parse(document.querySelector('#report-data').textContent);
const sourceFiles = new Map(report.files.map(file => [file.id, file]));
const paths = new Map(report.reading.treeFiles.map(path => [path.path, path]));
const sections = [...document.querySelectorAll('.requirement')];
const rows = [...document.querySelectorAll('.tree-file')];
const targets = report.reading.targets;
const list = document.querySelector('#tree-scroll');
const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
const mobileViewport = matchMedia('(max-width: 720px)');
const foldStates = new WeakMap();
const easing = 'cubic-bezier(0.22, 1, 0.36, 1)';
let current = 1, selectedPath = '', selectedFileId = '', queued = false, navigation = 0;

function stateFor(details) {
  if (!foldStates.has(details)) foldStates.set(details, {expanded: details.open, animation: null, pending: null, version: 0});
  return foldStates.get(details);
}
// Every fold uses the same interruptible controller. Only start/end sizes are measured.
function openingAncestors(details) {
  const result = [];
  for (let parent = details.parentElement; parent; parent = parent.parentElement) {
    if (parent.tagName === 'DETAILS') {
      const state = stateFor(parent);
      if (state.expanded && state.animation) result.push(state.animation);
    }
  }
  return result;
}
function runFold(details, expanded, animate) {
  const state = stateFor(details);
  const content = details.querySelector(':scope > [data-fold-content]');
  // Older reports and custom details may not have an animation container.
  if (!content) {
    details.open = expanded;
    details.classList.remove('is-closing');
    return Promise.resolve();
  }
  const wasOpen = details.open;
  const startHeight = wasOpen ? content.getBoundingClientRect().height : 0;
  const style = wasOpen ? getComputedStyle(content) : null;
  const startOpacity = style ? Number(style.opacity) : 0;
  const startTransform = style ? style.transform : 'translateY(-4px)';
  if (expanded && (!wasOpen || state.animation)) {
    for (const child of details.querySelectorAll('details')) {
      const childState = stateFor(child);
      if (childState.animation || childState.pending) setExpanded(child, childState.expanded, {animate: false});
    }
  }
  state.animation?.cancel();
  state.animation = null;
  details.classList.toggle('is-closing', !expanded);
  details.open = true;
  const targetHeight = expanded ? content.scrollHeight : 0;
  if (!animate || reducedMotion.matches || (startHeight === 0 && targetHeight === 0)) {
    details.open = expanded;
    details.classList.remove('is-closing');
    return Promise.resolve();
  }
  const animation = content.animate([
    {height: startHeight + 'px', opacity: startOpacity, transform: startTransform},
    {height: targetHeight + 'px', opacity: expanded ? 1 : 0, transform: expanded ? 'translateY(0)' : 'translateY(-4px)'}
  ], {duration: expanded ? 250 : 210, easing, fill: 'both'});
  state.animation = animation;
  return animation.finished.then(() => {
    if (state.animation !== animation) return;
    details.open = state.expanded;
    state.animation = null;
    details.classList.remove('is-closing');
    animation.cancel();
  }, () => {});
}
function setExpanded(details, expanded, {animate = true} = {}) {
  const state = stateFor(details);
  const immediate = !animate || reducedMotion.matches;
  if (state.expanded === expanded && !(immediate && (state.animation || state.pending))) {
    return state.pending || (state.animation ? state.animation.finished.catch(() => {}) : Promise.resolve());
  }
  state.expanded = expanded;
  details.classList.toggle('is-closing', !expanded && details.open);
  const version = ++state.version;
  state.pending = null;
  if (!immediate && openingAncestors(details).length) {
    const pending = (async () => {
      let ancestors;
      while (version === state.version && (ancestors = openingAncestors(details)).length) {
        await Promise.all(ancestors.map(animation => animation.finished.catch(() => {})));
      }
      if (version !== state.version) return;
      let visible = true;
      for (let parent = details.parentElement; parent; parent = parent.parentElement) {
        if (parent.tagName === 'DETAILS' && !stateFor(parent).expanded) visible = false;
      }
      await runFold(details, state.expanded, visible);
    })();
    state.pending = pending;
    return pending.finally(() => {if (state.pending === pending) state.pending = null;});
  }
  return runFold(details, expanded, !immediate);
}
const initializedFolds = new WeakSet();
function initializeFold(details) {
  if (initializedFolds.has(details)) return;
  initializedFolds.add(details);
  stateFor(details);
  details.querySelector(':scope > summary').addEventListener('click', event => {
    event.preventDefault();
    setExpanded(details, !stateFor(details).expanded);
  });
  details.addEventListener('toggle', event => {
    if (event.target !== details) return;
    const state = stateFor(details);
    if (!state.animation && !state.pending) state.expanded = details.open;
  });
}
for (const details of document.querySelectorAll('details')) initializeFold(details);

function targetFor(path, preferredFile) {
  const available = targets.filter(target => target.path === path);
  return available.find(target => target.requirement === current && (!preferredFile || target.fileId === preferredFile)) ||
    available.find(target => !preferredFile || target.fileId === preferredFile) || available[0];
}
function updateTree() {
  for (const row of rows) {
    const path = paths.get(row.dataset.path);
    const matches = path.requirements.includes(current);
    const target = targetFor(path.path, path.path === selectedPath ? selectedFileId : undefined);
    const file = sourceFiles.get(target.fileId);
    row.classList.toggle('is-current', matches);
    row.classList.toggle('is-muted', !matches);
    // Path-only resources show a label instead of numeric count nodes.
    const additions = row.querySelector('.line-count b');
    const deletions = row.querySelector('.line-count i');
    if (additions) additions.textContent = '+' + file.add;
    if (deletions) deletions.textContent = '−' + file.delete;
    row.title = path.path + ' · ' + file.from + ' → ' + file.to;
    if (path.path === selectedPath) row.setAttribute('aria-current', 'location');
    else row.removeAttribute('aria-current');
  }
  document.querySelectorAll('[data-requirement-link]').forEach(link => {
    link.setAttribute('aria-current', String(Number(link.dataset.requirementLink) === current));
  });
}
function setCurrent(number) {
  if (current === number) return;
  current = number;
  updateTree();
}
function scrollIntoPlace(element) {
  const behavior = reducedMotion.matches ? 'instant' : 'smooth';
  if (reducedMotion.matches) {
    element.scrollIntoView({behavior, block: 'start'});
    return Promise.resolve();
  }
  return new Promise(resolve => {
    let timer;
    const finish = () => {clearTimeout(timer); document.removeEventListener('scrollend', finish); resolve();};
    document.addEventListener('scrollend', finish, {once: true});
    element.scrollIntoView({behavior, block: 'start'});
    timer = setTimeout(finish, 1100);
  });
}
async function scrollToTarget(element, token, spotlight = false) {
  const ancestors = [];
  for (let parent = element.parentElement; parent; parent = parent.parentElement) {
    if (parent.tagName === 'DETAILS') ancestors.unshift(parent);
  }
  for (const parent of ancestors) {
    if (token !== navigation) return;
    await setExpanded(parent, true);
    if (token !== navigation) return;
  }
  if (token !== navigation) return;
  await scrollIntoPlace(element);
  if (token !== navigation) return;
  if (drawerRoot.hidden) (element.querySelector('.diff-file') || element).focus?.({preventScroll: true});
  if (spotlight && !reducedMotion.matches) {
    element.classList.remove('is-spotlight');
    requestAnimationFrame(() => {if (token === navigation) element.classList.add('is-spotlight');});
  }
}
for (const card of document.querySelectorAll('.diff-card')) {
  card.addEventListener('animationend', event => {
    if (event.animationName === 'target-spotlight') card.classList.remove('is-spotlight');
  });
}
const drawerRoot = document.querySelector('.diff-drawer-root');
const drawer = drawerRoot.querySelector('.diff-drawer');
const backdrop = drawerRoot.querySelector('.diff-drawer-backdrop');
const drawerBody = drawer.querySelector('.drawer-body');
const drawerInformation = drawer.querySelector('.drawer-information');
const previousButton = drawer.querySelector('[data-drawer-prev]');
const nextButton = drawer.querySelector('[data-drawer-next]');
const closeButton = drawer.querySelector('[data-drawer-close]');
const targetMap = new Map(targets.map(target => [target.id, target]));
let drawerOpen = false, drawerTarget = null, drawerVersion = 0;
let slideAnimation = null, shadeAnimation = null, contentAnimations = [], returnFocus = null;
let desktopTreeCollapsed = document.body.classList.contains('is-tree-collapsed');

function syncMobilePanels() {
  const treeOpen = !document.body.classList.contains('is-tree-collapsed');
  document.body.classList.toggle('is-mobile-panel-open', mobileViewport.matches && (treeOpen || drawerOpen));
  drawer.setAttribute('aria-modal', String(mobileViewport.matches));
  document.querySelector('.report-main').inert = mobileViewport.matches && (treeOpen || drawerOpen);
  document.querySelector('.file-sidebar').inert = mobileViewport.matches && drawerOpen;
  document.querySelector('.tree-reopen-btn').inert = mobileViewport.matches && drawerOpen;
}
function setTreeCollapsed(collapsed) {
  document.body.classList.toggle('is-tree-collapsed', collapsed);
  for (const button of document.querySelectorAll('[data-tree-toggle]')) {
    button.setAttribute('aria-expanded', String(!collapsed));
  }
  syncMobilePanels();
}
setTreeCollapsed(mobileViewport.matches || desktopTreeCollapsed);
mobileViewport.addEventListener('change', () => {
  setTreeCollapsed(mobileViewport.matches || desktopTreeCollapsed);
});

function selectFile(target) {
  for (const card of document.querySelectorAll('.diff-card.is-active')) {
    card.classList.remove('is-active');
    card.querySelector('.diff-file').setAttribute('aria-expanded', 'false');
  }
  if (target) {
    const card = document.getElementById(target.id);
    card.classList.add('is-active');
    card.querySelector('.diff-file').setAttribute('aria-expanded', 'true');
  }
  selectedPath = target?.path || '';
  selectedFileId = target?.fileId || '';
  updateTree(false);
}
function configureSourceNavigation(target) {
  const source = drawerBody.querySelector('.single-source');
  const link = drawer.querySelector('[data-vscode-open]');
  const status = drawer.querySelector('[data-vscode-status]');
  link.removeAttribute('href'); link.setAttribute('aria-disabled', 'true');
  status.textContent = '';
  if (!source) { status.textContent = '此文件不提供源码定位'; return; }
  const lines = [...source.querySelectorAll('.source-code [data-line]')];
  const focus = Number(source.dataset.focusLine) || 1;
  const stations = lines.filter((line, i) => line.dataset.state !== 'unchanged' &&
    (!i || lines[i-1].dataset.state === 'unchanged' || Number(line.dataset.line) !== Number(lines[i-1].dataset.line) + 1));
  let position = -1;
  const select = (line, scroll) => {
    source.querySelectorAll('.review-active').forEach(el => el.classList.remove('review-active'));
    if (!line) return;
    line.classList.add('review-active');
    const n = Number(line.dataset.line);
    position = stations.findIndex(el => Number(el.dataset.line) === n);
    source.querySelector('[data-code-position]').textContent = `第 ${n} 行 · ${position >= 0 ? position+1 : '—'} / ${stations.length} 处改动`;
    // Infer project root from the standalone report location; never bake host paths into reports.
    const path = decodeURIComponent(location.pathname);
    const marker = path.lastIndexOf('/.oil-diff/');
    if (location.protocol === 'file:' && marker >= 0 && !target.path.split('/').includes('..') && !target.path.startsWith('/')) {
      const query = new URLSearchParams({root:path.slice(0, marker), path:target.path, line:String(n)});
      link.href = 'archify-vscode://open?' + query.toString();
      link.setAttribute('aria-disabled', 'false');
      status.textContent = `打开项目并定位第 ${n} 行（当前工作区文件）`;
    } else { status.textContent = '请从项目 .oil-diff 目录打开本地报告后使用 VS Code 定位'; }
    if (scroll) line.scrollIntoView({block:'nearest',inline:'nearest'});
  };
  for (const button of source.querySelectorAll('[data-select-line]')) button.addEventListener('click', () => select(button.closest('[data-line]'), false));
  for (const [selector, step] of [['[data-code-prev]', -1], ['[data-code-next]', 1]]) {
    const button = source.querySelector(selector); button.disabled = !stations.length;
    button.addEventListener('click', () => {
      const index = position < 0 ? (step > 0 ? 0 : stations.length-1) : (position + step + stations.length) % stations.length;
      select(stations[index], true);
    });
  }
  if (!lines.length) status.textContent = '没有新增目标行可定位';
  select(lines.find(el => Number(el.dataset.line) === focus && el.dataset.state !== 'unchanged') || stations[0] || lines.find(el => Number(el.dataset.line) === focus) || lines[0], false);
}

function populateDrawer(target, switching) {
  for (const animation of contentAnimations) animation.cancel();
  contentAnimations = [];
  for (const details of drawerBody.querySelectorAll('details')) {
    const state = stateFor(details);
    ++state.version;
    state.animation?.cancel();
    state.animation = null;
    state.pending = null;
  }
  const card = document.getElementById(target.id);
  drawer.querySelector('.drawer-context').textContent = target.context;
  drawer.querySelector('.drawer-file-identity').replaceChildren(card.querySelector('.file-identity').cloneNode(true));
  drawer.querySelector('.drawer-counts').replaceChildren(card.querySelector('.line-count').cloneNode(true));
  const role = drawer.querySelector('.drawer-role');
  role.textContent = target.role;
  role.hidden = !target.role;
  drawerBody.replaceChildren(document.getElementById('source-' + target.id).content.cloneNode(true));
  for (const details of drawerBody.querySelectorAll('details')) initializeFold(details);
  drawerBody.scrollTop = 0;
  configureSourceNavigation(target);
  const index = targets.indexOf(target);
  previousButton.disabled = index === 0;
  nextButton.disabled = index === targets.length - 1;
  if (switching && !reducedMotion.matches) {
    contentAnimations = [drawerInformation, drawerBody].map(element => element.animate([
      {opacity: .35, transform: 'translateY(6px)'}, {opacity: 1, transform: 'translateY(0)'}
    ], {duration: 180, easing}));
  }
}
function moveDrawer(open, {animate = true} = {}) {
  const version = ++drawerVersion;
  const wasVisible = !drawerRoot.hidden;
  const panelStyle = wasVisible ? getComputedStyle(drawer) : null;
  const start = {transform: panelStyle?.transform || 'translateX(calc(100% + 20px))', opacity: panelStyle?.opacity || '0'};
  const shadeOpacity = wasVisible ? getComputedStyle(backdrop).opacity : '0';
  slideAnimation?.cancel(); shadeAnimation?.cancel();
  slideAnimation = null; shadeAnimation = null;
  drawerRoot.hidden = false;
  drawerRoot.inert = !open;
  drawerRoot.setAttribute('aria-hidden', String(!open));
  const finish = () => {
    if (version !== drawerVersion) return;
    drawerRoot.hidden = !open;
    slideAnimation?.cancel(); shadeAnimation?.cancel();
    slideAnimation = null; shadeAnimation = null;
    if (!open && returnFocus?.isConnected) {
      const target = mobileViewport.matches && returnFocus.closest('.file-sidebar') ? document.querySelector('.tree-reopen-btn') : returnFocus;
      target.focus({preventScroll: true});
    }
  };
  if (!animate || reducedMotion.matches) {finish(); return;}
  slideAnimation = drawer.animate([start, {
    transform: open ? 'translateX(0)' : 'translateX(calc(100% + 20px))', opacity: open ? 1 : 0
  }], {duration: open ? 280 : 220, easing, fill: 'both'});
  shadeAnimation = backdrop.animate([{opacity: shadeOpacity}, {opacity: open ? 1 : 0}], {duration: 220, easing: 'ease', fill: 'both'});
  slideAnimation.finished.then(finish, () => {});
}
function openDrawer(target, trigger, {toggle = false, focus = true} = {}) {
  if (toggle && drawerOpen && drawerTarget?.id === target.id) {closeDrawer(); return;}
  const switching = drawerOpen;
  const sameTarget = drawerTarget?.id === target.id;
  drawerTarget = target;
  if (trigger) returnFocus = trigger;
  else if (!returnFocus) returnFocus = document.getElementById(target.id)?.querySelector('.diff-file');
  setCurrent(target.requirement);
  if (!sameTarget || !drawerOpen) populateDrawer(target, switching);
  selectFile(target);
  history.replaceState(null, '', '#' + target.id);
  drawerOpen = true;
  if (mobileViewport.matches) setTreeCollapsed(true);
  syncMobilePanels();
  if (!switching) moveDrawer(true);
  if (focus) closeButton.focus({preventScroll: true});
}
function closeDrawer() {
  if (!drawerOpen) return;
  ++navigation;
  drawerOpen = false;
  syncMobilePanels();
  selectFile(null);
  if (location.hash.startsWith('#diff-')) history.replaceState(null, '', '#requirement-' + current);
  moveDrawer(false);
}
function jumpToSection(number) {
  const token = ++navigation;
  setCurrent(number);
  history.replaceState(null, '', '#requirement-' + number);
  scrollToTarget(document.querySelector('#requirement-' + number), token);
}
function jumpToFile(path, fileId, trigger) {
  const target = targetFor(path, fileId);
  if (target) jumpToFileTarget(target, trigger);
}
function jumpToFileTarget(target, trigger) {
  ++navigation;
  openDrawer(target, trigger, {toggle: true});
}
for (const button of document.querySelectorAll('.diff-file')) {
  button.addEventListener('click', () => {
    ++navigation;
    openDrawer(targetMap.get(button.closest('.diff-card').id), button, {toggle: true});
  });
}
for (const section of sections) {
  section.addEventListener('click', () => setCurrent(Number(section.dataset.requirement)));
}
for (const btn of document.querySelectorAll('[data-tree-toggle]')) {
  btn.addEventListener('click', () => {
    const collapsed = !document.body.classList.contains('is-tree-collapsed');
    if (!mobileViewport.matches) desktopTreeCollapsed = collapsed;
    setTreeCollapsed(collapsed);
    if (mobileViewport.matches) {
      (collapsed ? document.querySelector('.tree-reopen-btn') : document.querySelector('.tree-toggle-btn')).focus({preventScroll: true});
    }
  });
}
for (const slider of document.querySelectorAll('.shot-slider-input')) {
  slider.addEventListener('input', () => {
    slider.closest('.shot-slider').style.setProperty('--split', slider.value + '%');
  });
}
const lightbox = document.getElementById('shot-lightbox');
if (lightbox) {
  const lbImg = lightbox.querySelector('img');
  const lbCap = lightbox.querySelector('.shot-lightbox-caption');
  const closeLb = () => {lightbox.hidden = true;};
  for (const trig of document.querySelectorAll('[data-lightbox-src], [data-shot-zoom]')) {
    trig.addEventListener('click', () => {
      lbImg.src = trig.dataset.lightboxSrc || trig.dataset.shotZoom;
      const cap = trig.dataset.lightboxCaption || trig.dataset.shotCaption || '';
      lbImg.alt = cap;
      if (lbCap) lbCap.textContent = cap;
      lightbox.hidden = false;
    });
  }
  lightbox.addEventListener('click', closeLb);
  addEventListener('keydown', event => {if (event.key === 'Escape' && !lightbox.hidden) closeLb();});
}
previousButton.addEventListener('click', () => {
  const target = targets[targets.indexOf(drawerTarget) - 1];
  if (target) {++navigation; openDrawer(target, null, {focus: false});}
});
nextButton.addEventListener('click', () => {
  const target = targets[targets.indexOf(drawerTarget) + 1];
  if (target) {++navigation; openDrawer(target, null, {focus: false});}
});
closeButton.addEventListener('click', closeDrawer);
backdrop.addEventListener('click', closeDrawer);
document.addEventListener('click', event => {
  if (drawerRoot.hidden || drawer.contains(event.target)) return;
  if (event.target.closest('.diff-file, .tree-file, [data-tree-toggle]')) return;
  event.preventDefault();
  event.stopImmediatePropagation();
  closeDrawer();
}, true);
addEventListener('keydown', event => {
  if (event.key === 'Escape' && !drawerRoot.hidden) {
    event.preventDefault();
    closeDrawer();
  } else if (event.key === 'Escape' && mobileViewport.matches && !document.body.classList.contains('is-tree-collapsed')) {
    setTreeCollapsed(true);
    document.querySelector('.tree-reopen-btn').focus({preventScroll: true});
  }
});
reducedMotion.addEventListener('change', () => {
  if (!reducedMotion.matches) return;
  for (const details of document.querySelectorAll('details')) setExpanded(details, stateFor(details).expanded, {animate: false});
  for (const animation of contentAnimations) animation.cancel();
  if (!drawerRoot.hidden) moveDrawer(drawerOpen, {animate: false});
});
for (const button of rows) button.addEventListener('click', () => jumpToFile(button.dataset.path, undefined, button));
for (const link of document.querySelectorAll('[data-requirement-link]')) {
  link.addEventListener('click', event => {event.preventDefault(); jumpToSection(Number(link.dataset.requirementLink));});
}
const stickyHost = document.querySelector('.sticky-nav-host');
const overview = document.querySelector('.overview-nav');
const overviewObserver = new IntersectionObserver(entries => {
  const visible = entries[0].boundingClientRect.bottom <= 64;
  stickyHost.classList.toggle('is-visible', visible);
  stickyHost.inert = !visible;
  stickyHost.setAttribute('aria-hidden', String(!visible));
}, {rootMargin: '-64px 0px 0px 0px'});
overviewObserver.observe(overview);
function trackScroll() {
  queued = false;
  const boundary = Math.min(180, innerHeight * .22);
  let activeRow = [sections[0]];
  let rowTop = sections[0].getBoundingClientRect().top;
  for (const section of sections.slice(1)) {
    const top = section.getBoundingClientRect().top;
    if (Math.abs(top - rowTop) < 8) {
      activeRow.push(section);
    } else if (top <= boundary) {
      activeRow = [section];
      rowTop = top;
    } else {
      break;
    }
  }
  const rowNums = activeRow.map(s => Number(s.dataset.requirement));
  if (!rowNums.includes(current)) {
    setCurrent(rowNums[0]);
  }
}
addEventListener('scroll', () => {if (!queued) {queued = true; requestAnimationFrame(trackScroll);}}, {passive: true});
addEventListener('resize', trackScroll);
updateTree();
if (location.hash) {
  const target = document.getElementById(location.hash.slice(1));
  if (target?.classList.contains('diff-card')) {
    jumpToFileTarget(targetMap.get(target.id));
  } else if (target?.classList.contains('requirement')) jumpToSection(Number(target.dataset.requirement));
  else trackScroll();
}
