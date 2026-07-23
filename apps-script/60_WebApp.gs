/** HTML entrypoint and public RPC surface. */
function _include_(filename) { return HtmlService.createHtmlOutputFromFile(filename).getContent(); }

function _designTokenDeclarations_(tokens) {
  return Object.keys(tokens || {}).map(function (name) {
    const value = _text_(tokens[name]);
    _assert_(/^--[a-z0-9-]+$/.test(name) && value && !/[;{}<>]/.test(value),
      'El manifiesto contiene un token visual inválido.', 'CONTRACT_ERROR');
    return name + ':' + value;
  }).join(';');
}

function _clientBootstrapMarkup_(sharedToken) {
  const shareJson = _safeJsonStringify_(_text_(sharedToken)).replace(/</g, '\\u003c');
  const light = _designTokenDeclarations_(DESIGN_TOKENS.web.light);
  const dark = _designTokenDeclarations_(DESIGN_TOKENS.web.dark);
  return '<script>window.__RADAR_SHARE_TOKEN__=' + shareJson + ';</script>' +
    '<style id="radar-design-tokens">:root{' + light + '}' +
    ':root[data-theme="dark"]{' + dark + '}</style>';
}

function doGet(event) {
  const template = HtmlService.createTemplateFromFile('Index');
  const requestedShare = _sanitizeText_(event && event.parameter ? event.parameter.share : '', 160);
  template.sharedToken = !requestedShare || /^[A-Za-z0-9_-]{40,120}$/.test(requestedShare) ? requestedShare : 'invalid';
  return template.evaluate().setTitle(RADAR.appName).setXFrameOptionsMode(HtmlService.XFrameOptionsMode.DEFAULT);
}
