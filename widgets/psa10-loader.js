// Variables used by Scriptable.
// These must be at the very top of the file. Do not edit.
// icon-color: yellow; icon-glyph: chart-line;

// PSA10 Tracker widget: loader. Paste THIS file into Scriptable once (instead of psa10-widget.js).
// Each run it fetches the current widget code from the site (widgets/psa10-widget.js) and runs it, so
// changes to the widget reach your iPhone / iPad without pasting again. The last good copy is kept on
// the device, so the widget still works offline. The code it runs is your own repo's (sprdl/psa10-tracker).

const CODE_URL = 'https://sprdl.github.io/psa10-tracker/widgets/psa10-widget.js';
const lfm = FileManager.local();
const codeFile = lfm.joinPath(lfm.documentsDirectory(), 'psa10-widget-code.js');
let code = null;
try {
  const req = new Request(CODE_URL + '?t=' + Math.floor(Date.now() / 3600000));   // re-fetched at most hourly
  req.timeoutInterval = 15;
  const body = await req.loadString();
  // only accept the real widget (a GitHub Pages 404 page or a captive portal must not replace the good copy)
  if (req.response && req.response.statusCode === 200 && body.includes('PSA10 Tracker widget for Scriptable')) {
    code = body;
    lfm.writeString(codeFile, code);
  }
} catch (e) { /* offline: use the saved copy */ }
if (!code && lfm.fileExists(codeFile)) code = lfm.readString(codeFile);
if (!code) {
  const w = new ListWidget();
  w.addText("Ghost Bid: couldn't load the widget code yet. Open Scriptable once while online.");
  Script.setWidget(w);
  Script.complete();
} else {
  // the widget code uses top-level await, so run it as the body of an async function
  const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
  await new AsyncFunction(code)();
}
