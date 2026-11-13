// Run the real drawer selection path against rows parsed from generated HTML.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const payload = JSON.parse(fs.readFileSync(0, 'utf8'));
const source = fs.readFileSync(process.argv[2] || path.join(__dirname, '../assets/report.js'), 'utf8');

function element() {
  const classes = new Set();
  const attributes = new Map();
  return {
    classList: {
      add(name) { classes.add(name); },
      remove(name) { classes.delete(name); },
      contains(name) { return classes.has(name); },
      toggle(name, enabled) { enabled ? classes.add(name) : classes.delete(name); },
    },
    setAttribute(name, value) { attributes.set(name, value); },
    removeAttribute(name) { attributes.delete(name); },
    getAttribute(name) { return attributes.get(name); },
  };
}

const rows = payload.rows.map(row => {
  const result = {...element(), dataset: {path: row.path}};
  result.add = row.add === null ? null : {textContent: row.add};
  result.delete = row.delete === null ? null : {textContent: row.delete};
  result.querySelector = selector => {
    if (selector === '.line-count b') return result.add;
    if (selector === '.line-count i') return result.delete;
    throw new Error('Unexpected tree selector: ' + selector);
  };
  return result;
});
const targets = payload.reading.targets;
const cards = new Map(targets.map(target => {
  const button = element();
  const card = {...element(), querySelector: () => button};
  return [target.id, card];
}));
const drawerRoot = {hidden: true};
const location = {hash: ''};
const ctx = vm.createContext({
  rows, targets, drawerRoot, location,
  paths: new Map(payload.reading.treeFiles.map(file => [file.path, file])),
  sourceFiles: new Map(payload.files.map(file => [file.id, file])),
  current: 1, selectedPath: '', selectedFileId: '', navigation: 0,
  drawerOpen: false, drawerTarget: null, returnFocus: null, populated: null,
  mobileViewport: {matches: false},
  document: {
    getElementById: id => cards.get(id),
    querySelectorAll(selector) {
      if (selector === '[data-requirement-link]') return [];
      if (selector === '.diff-card.is-active') return [...cards.values()].filter(card => card.classList.contains('is-active'));
      throw new Error('Unexpected document selector: ' + selector);
    },
  },
  history: {replaceState(_state, _title, hash) { location.hash = hash; }},
  syncMobilePanels() {}, setTreeCollapsed() {},
  closeButton: {focus() {}},
  // Content rendering and animation are outside this selection/visibility seam.
  populateDrawer(target) { ctx.populated = target.id; },
  moveDrawer(open) { drawerRoot.hidden = !open; },
});
const controller =
  source.slice(source.indexOf('function targetFor('), source.indexOf('function scrollIntoPlace(')) +
  source.slice(source.indexOf('function selectFile('), source.indexOf('function configureSourceNavigation(')) +
  source.slice(source.indexOf('function openDrawer('), source.indexOf('function jumpToSection('));
vm.runInContext(controller, ctx);
vm.runInContext('updateTree()', ctx); // Same initialization as the generated page.

for (let index = 0; index < targets.length; index++) {
  vm.runInContext(`openDrawer(targets[${index}], null, {focus: false})`, ctx);
  assert.equal(drawerRoot.hidden, false, 'Selecting a file must reveal the code/detail drawer');
  assert.equal(ctx.populated, targets[index].id);
  assert.equal(ctx.selectedFileId, targets[index].fileId);
  assert.equal(cards.get(targets[index].id).querySelector().getAttribute('aria-expanded'), 'true');
  const row = rows.find(row => row.dataset.path === targets[index].path);
  assert.equal(row.getAttribute('aria-current'), 'location');
}
vm.runInContext('closeDrawer()', ctx);
assert.equal(drawerRoot.hidden, true, 'Closing must remain functional after selection and switching');
vm.runInContext('openDrawer(targets[0], null, {focus: false})', ctx);
vm.runInContext('openDrawer(targets[0], null, {toggle: true, focus: false})', ctx);
assert.equal(drawerRoot.hidden, true, 'Clicking the selected file again must close the drawer');
for (const row of rows) {
  const file = payload.files.find(file => file.path === row.dataset.path);
  if (row.add) assert.equal(row.add.textContent, '+' + file.add);
  if (row.delete) assert.equal(row.delete.textContent, '−' + file.delete);
}
console.log('PASS: mixed source and path-only rows allow initialization, drawer selection, switching, and closing');
