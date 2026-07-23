/** HTML entrypoint and public RPC surface. */
function _include_(filename) { return HtmlService.createHtmlOutputFromFile(filename).getContent(); }
function doGet(event) {
  const template = HtmlService.createTemplateFromFile('Index');
  const requestedShare = _sanitizeText_(event && event.parameter ? event.parameter.share : '', 160);
  template.sharedToken = !requestedShare || /^[A-Za-z0-9_-]{40,120}$/.test(requestedShare) ? requestedShare : 'invalid';
  return template.evaluate().setTitle(RADAR.appName).setXFrameOptionsMode(HtmlService.XFrameOptionsMode.DEFAULT);
}
