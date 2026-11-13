// Exercise the actual fold controller without a browser or third-party packages.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../assets/report.js'), 'utf8');
const controller = source.slice(source.indexOf('function stateFor('),
  source.indexOf("for (const details of document.querySelectorAll('details')) initializeFold(details);"));

async function check(reduceMotion, hasContainer) {
  const listeners = {};
  const summary = {addEventListener(type, handler) { listeners[type] = handler; }};
  const content = {
    scrollHeight: 120,
    getBoundingClientRect() { return {height: 120}; },
    animate() { return {finished: Promise.resolve(), cancel() {}}; },
  };
  const details = {
    open: false,
    parentElement: null,
    classList: {toggle() {}, remove() {}},
    querySelector(selector) {
      if (selector === ':scope > summary') return summary;
      if (selector === ':scope > [data-fold-content]') return hasContainer ? content : null;
      throw new Error('Unexpected selector: ' + selector);
    },
    querySelectorAll() { return []; },
    addEventListener() {},
  };
  const ctx = vm.createContext({
    foldStates: new WeakMap(), reducedMotion: {matches: reduceMotion},
    easing: 'ease', getComputedStyle: () => ({opacity: '1', transform: 'none'}),
    details,
  });
  vm.runInContext(controller + '\ninitializeFold(details);', ctx);
  let prevented = false;
  listeners.click({preventDefault() { prevented = true; }});
  await vm.runInContext('stateFor(details).pending || Promise.resolve()', ctx);
  assert.ok(prevented);
  assert.equal(details.open, true, 'Click must reveal old source');
  listeners.click({preventDefault() {}});
  await vm.runInContext('stateFor(details).pending || Promise.resolve()', ctx);
  assert.equal(details.open, false, 'Second click must hide old source');
}

(async () => {
  for (const reduceMotion of [false, true]) {
    for (const hasContainer of [true, false]) await check(reduceMotion, hasContainer);
  }
  console.log('PASS: animated, reduced-motion, and legacy source folds open and close');
})().catch(error => { console.error(error); process.exitCode = 1; });
