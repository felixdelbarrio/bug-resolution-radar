/** Strict portable transfer v3 adapter. Desktop owns every business rationale. */
const TRANSFER_FILES = Object.freeze({
  projection: 'data/projection.json',
  report: 'artifacts/period_followup.pptx'
});
const TRANSFER_LABELS = Object.freeze({
  projection: 'Proyección canónica',
  report: 'Presentación de seguimiento'
});
const REPORT_PPTX_MIME = 'application/vnd.openxmlformats-officedocument.presentationml.presentation';

function _byte_(value) { return (Number(value) + 256) % 256; }
function _u16le_(bytes, offset) { return _byte_(bytes[offset]) + _byte_(bytes[offset + 1]) * 256; }
function _u32le_(bytes, offset) {
  return (_byte_(bytes[offset]) + _byte_(bytes[offset + 1]) * 256 +
    _byte_(bytes[offset + 2]) * 65536 + _byte_(bytes[offset + 3]) * 16777216) >>> 0;
}
function _sha256Bytes_(bytes) {
  return Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, bytes).map(function (value) {
    return ('0' + _byte_(value).toString(16)).slice(-2);
  }).join('');
}
function _sha256Blob_(blob) { return _sha256Bytes_(blob.getBytes()); }

function _zipEntryNames_(blob, archiveBytes, maximumExpandedBytes) {
  const bytes = archiveBytes || blob.getBytes();
  const minimum = Math.max(0, bytes.length - 65557);
  let eocd = -1;
  for (let offset = bytes.length - 22; offset >= minimum; offset -= 1) {
    if (_u32le_(bytes, offset) === 0x06054b50) { eocd = offset; break; }
  }
  _assert_(eocd >= 0, 'El fichero no contiene una estructura ZIP válida.', 'TRANSFER_INVALID');
  const disk = _u16le_(bytes, eocd + 4);
  const directoryDisk = _u16le_(bytes, eocd + 6);
  const diskEntries = _u16le_(bytes, eocd + 8);
  const entries = _u16le_(bytes, eocd + 10);
  const directorySize = _u32le_(bytes, eocd + 12);
  const directoryOffset = _u32le_(bytes, eocd + 16);
  const eocdCommentLength = _u16le_(bytes, eocd + 20);
  _assert_(disk === 0 && directoryDisk === 0 && diskEntries === entries && entries > 0 && entries < 65535,
    'El ZIP usa una estructura no admitida.', 'TRANSFER_INVALID');
  _assert_(eocd + 22 + eocdCommentLength === bytes.length && directoryOffset + directorySize <= eocd,
    'El inventario ZIP está truncado.', 'TRANSFER_INVALID');
  let cursor = directoryOffset;
  let expanded = 0;
  const names = [];
  for (let index = 0; index < entries; index += 1) {
    _assert_(_u32le_(bytes, cursor) === 0x02014b50, 'El inventario ZIP está dañado.', 'TRANSFER_INVALID');
    const flags = _u16le_(bytes, cursor + 8);
    const method = _u16le_(bytes, cursor + 10);
    const compressed = _u32le_(bytes, cursor + 20);
    const uncompressed = _u32le_(bytes, cursor + 24);
    const nameLength = _u16le_(bytes, cursor + 28);
    const extraLength = _u16le_(bytes, cursor + 30);
    const commentLength = _u16le_(bytes, cursor + 32);
    _assert_((flags & 1) === 0 && [0, 8].indexOf(method) >= 0,
      'El ZIP contiene una entrada cifrada o incompatible.', 'TRANSFER_INVALID');
    _assert_(compressed <= RADAR.maxTransferExpandedBytes && uncompressed <= RADAR.maxTransferExpandedBytes,
      'Una entrada del ZIP supera el tamaño permitido.', 'TRANSFER_TOO_LARGE');
    const nameBytes = bytes.slice(cursor + 46, cursor + 46 + nameLength);
    const name = Utilities.newBlob(nameBytes).getDataAsString('UTF-8');
    _assert_(name && name[0] !== '/' && name.indexOf('\\') < 0 && name.split('/').indexOf('..') < 0,
      'El ZIP contiene rutas no permitidas.', 'TRANSFER_INVALID');
    names.push(name);
    expanded += uncompressed;
    cursor += 46 + nameLength + extraLength + commentLength;
  }
  _assert_(cursor === directoryOffset + directorySize, 'El inventario ZIP no coincide con el fichero.', 'TRANSFER_INVALID');
  _assert_(expanded <= Number(maximumExpandedBytes || RADAR.maxTransferExpandedBytes),
    'El contenido expandido supera el tamaño permitido.', 'TRANSFER_TOO_LARGE');
  return names;
}

function _transferEntryMap_(archiveBlob, archiveBytes) {
  const expected = ['manifest.json', TRANSFER_FILES.projection, TRANSFER_FILES.report].sort();
  const directoryNames = _zipEntryNames_(archiveBlob, archiveBytes, RADAR.maxTransferExpandedBytes)
    .filter(function (name) { return !/\/$/.test(name); })
    .sort();
  _assert_(directoryNames.length === expected.length && directoryNames.every(function (name, index) {
    return name === expected[index];
  }), 'El traslado v3 debe contener exclusivamente manifest.json, data/projection.json y artifacts/period_followup.pptx.', 'TRANSFER_INVALID');
  let blobs;
  try {
    blobs = Utilities.unzip(archiveBlob);
  } catch (err) {
    throw Object.assign(new Error('No se puede descomprimir el respaldo seleccionado.'), { code: 'TRANSFER_INVALID' });
  }
  const entries = {};
  blobs.forEach(function (entry) {
    const name = entry.getName();
    if (/\/$/.test(name)) return;
    _assert_(!entries[name], 'El respaldo contiene elementos duplicados.', 'TRANSFER_INVALID');
    entries[name] = entry;
  });
  _assert_(Object.keys(entries).length === expected.length && expected.every(function (name) { return entries[name]; }),
    'El respaldo no coincide con su inventario ZIP.', 'TRANSFER_INVALID');
  return entries;
}

function _entryJson_(entries, name, label) {
  try {
    return JSON.parse(entries[name].getDataAsString('UTF-8'));
  } catch (err) {
    throw Object.assign(new Error('No se puede leer «' + label + '».'), { code: 'TRANSFER_INVALID' });
  }
}
function _assertObject_(value, message) {
  _assert_(value && typeof value === 'object' && !Array.isArray(value), message, 'TRANSFER_INVALID');
}
function _assertExactFields_(record, allowed, label) {
  _assertObject_(record, '«' + label + '» contiene un registro no válido.');
  const actual = Object.keys(record).sort();
  const expected = allowed.slice().sort();
  _assert_(actual.length === expected.length && actual.every(function (key, index) { return key === expected[index]; }),
    '«' + label + '» no cumple el contrato de campos: ' + expected.join(', ') + '.', 'TRANSFER_INVALID');
}
function _validateNoSecretsDeep_(value, depth, budget) {
  if (value == null || typeof value !== 'object') return;
  _assert_(depth <= 16 && budget.count < 300000,
    'La proyección contiene una estructura excesivamente compleja.', 'TRANSFER_INVALID');
  budget.count += 1;
  if (Array.isArray(value)) {
    value.forEach(function (item) { _validateNoSecretsDeep_(item, depth + 1, budget); });
    return;
  }
  const forbidden = /(^|_)(cookie|secret|password|passwd|authorization|access_token|refresh_token|api_key)($|_)/i;
  Object.keys(value).forEach(function (key) {
    _assert_(!forbidden.test(key), 'La proyección contiene un campo secreto no permitido.', 'SECRET_FIELD_REJECTED');
    _validateNoSecretsDeep_(value[key], depth + 1, budget);
  });
}
function _validateNoCloudActionsDeep_(value, path) {
  if (value == null || typeof value !== 'object') return;
  if (Array.isArray(value)) {
    value.forEach(function (item, index) {
      _validateNoCloudActionsDeep_(item, path + '[' + index + ']');
    });
    return;
  }
  const forbidden = new Set([
    'filters', 'statusFilters', 'priorityFilters', 'assigneeFilters',
    'functionalityFilters', 'issueKeys', 'quincenalScopeLabel', 'selected',
    'combo', 'statusOptions', 'priorityOptions', 'functionalityOptions',
    'selectedStatuses', 'selectedPriorities', 'selectedFunctionalities'
  ]);
  Object.keys(value).forEach(function (key) {
    _assert_(!forbidden.has(key),
      path + ' contiene una acción o filtro no admitido por GPC: ' + key + '.',
      'TRANSFER_INVALID');
    _validateNoCloudActionsDeep_(value[key], path + '.' + key);
  });
}
function _stableJsonValue_(value) {
  if (Array.isArray(value)) return value.map(_stableJsonValue_);
  if (value && typeof value === 'object') {
    const out = {};
    Object.keys(value).sort().forEach(function (key) { out[key] = _stableJsonValue_(value[key]); });
    return out;
  }
  return value;
}
function _stableJsonStringify_(value) { return JSON.stringify(_stableJsonValue_(value)); }

function _normalizeManifestScope_(raw, label) {
  _assertExactFields_(raw, [
    'scopeKey', 'scopeLabel', 'country', 'scopeMode', 'sourceIds',
    'dataVersion', 'referenceDate', 'immutable'
  ], label);
  const country = _sanitizeText_(raw.country, 120);
  const scopeMode = _text_(raw.scopeMode);
  const sourceIds = (raw.sourceIds || []).map(function (value) {
    return _sanitizeSourceId_(_text_(value).replace(/\s+/g, '-'));
  });
  _assert_(country, label + ' no contiene país.', 'TRANSFER_INVALID');
  _assert_(['country', 'source'].indexOf(scopeMode) >= 0, label + ' contiene un scopeMode no válido.', 'TRANSFER_INVALID');
  _assert_(Array.isArray(raw.sourceIds) && sourceIds.length > 0,
    label + ' debe declarar al menos un origen.', 'TRANSFER_INVALID');
  _assert_(sourceIds.length === new Set(sourceIds).size &&
    sourceIds.every(function (value, index) { return index === 0 || sourceIds[index - 1] < value; }),
  label + '.sourceIds debe estar ordenado y sin duplicados.', 'TRANSFER_INVALID');
  const scopeKey = _text_(raw.scopeKey);
  _assert_(scopeKey === _materializedScopeKey_(country, sourceIds),
    label + '.scopeKey no coincide con el país y los orígenes.', 'TRANSFER_INVALID');
  const scopeLabel = _sanitizeText_(raw.scopeLabel, 300);
  const dataVersion = _sanitizeText_(raw.dataVersion, 200);
  const referenceDate = _dayKey_(raw.referenceDate);
  _assert_(scopeLabel && dataVersion && referenceDate,
    label + ' no contiene etiqueta, versión o fecha de referencia válida.', 'TRANSFER_INVALID');
  _assert_(raw.immutable === true, label + ' debe declarar immutable=true.', 'TRANSFER_INVALID');
  return {
    scopeKey: scopeKey,
    scopeLabel: scopeLabel,
    country: country,
    scopeMode: scopeMode,
    sourceIds: sourceIds,
    dataVersion: dataVersion,
    referenceDate: referenceDate,
    immutable: true
  };
}

function _normalizeProjectionScope_(raw, label) {
  return _normalizeManifestScope_(raw, label);
}

function _assertCanonicalFactScalars_(value, path) {
  if (value == null || typeof value === 'string' || typeof value === 'boolean') return;
  if (typeof value === 'number') {
    _assert_(Number.isInteger(value) && isFinite(value), path + ' solo admite enteros.', 'TRANSFER_INVALID');
    return;
  }
  if (Array.isArray(value)) {
    value.forEach(function (item, index) { _assertCanonicalFactScalars_(item, path + '[' + index + ']'); });
    return;
  }
  _assertObject_(value, path + ' no es un valor canónico.');
  Object.keys(value).forEach(function (key) { _assertCanonicalFactScalars_(value[key], path + '.' + key); });
}

function _validateProjectionNewsletter_(newsletter) {
  _assertExactFields_(
    newsletter,
    [
      'periodLabel', 'focusLabel', 'metrics', 'previousOpen', 'backlogDelta',
      'criticalOpen', 'evolution', 'responsibleRollups', 'draft'
    ],
    'projection.newsletterFacts'
  );
  _assert_(_sanitizeText_(newsletter.periodLabel, 300), 'projection.newsletterFacts.periodLabel está vacío.', 'TRANSFER_INVALID');
  const baseMetricFields = [
    'createdCurrent', 'createdPrevious', 'closedCurrent', 'closedPrevious',
    'currentOpen', 'agedOpen', 'resolutionCurrent'
  ];
  const actualMetricFields = Object.keys(newsletter.metrics || {}).sort();
  const baseSorted = baseMetricFields.slice().sort();
  const splitSorted = baseMetricFields.concat(['focusOpen', 'otherOpen']).sort();
  const hasBase = actualMetricFields.length === baseSorted.length &&
    actualMetricFields.every(function (key, index) { return key === baseSorted[index]; });
  const hasSplit = actualMetricFields.length === splitSorted.length &&
    actualMetricFields.every(function (key, index) { return key === splitSorted[index]; });
  _assert_(hasBase || hasSplit,
    'projection.newsletterFacts.metrics no cumple el contrato de métricas.',
    'TRANSFER_INVALID');
  baseMetricFields.filter(function (key) {
    return key !== 'resolutionCurrent';
  }).forEach(function (key) {
    _assert_(Number.isInteger(newsletter.metrics[key]),
      'projection.newsletterFacts.metrics.' + key + ' debe ser entero.',
      'TRANSFER_INVALID');
  });
  _assert_(typeof newsletter.metrics.resolutionCurrent === 'string',
    'projection.newsletterFacts.metrics.resolutionCurrent debe ser texto.',
    'TRANSFER_INVALID');
  const focusLabel = _sanitizeText_(newsletter.focusLabel, 300);
  if (hasSplit) {
    _assert_(
      focusLabel &&
      Number.isInteger(newsletter.metrics.focusOpen) &&
      Number.isInteger(newsletter.metrics.otherOpen) &&
      newsletter.metrics.focusOpen + newsletter.metrics.otherOpen === newsletter.metrics.currentOpen,
      'El desglose focusOpen/otherOpen no es coherente con currentOpen.',
      'TRANSFER_INVALID'
    );
  } else {
    _assert_(!focusLabel,
      'focusLabel debe estar vacío cuando no existe desglose de foco.',
      'TRANSFER_INVALID');
  }
  ['previousOpen', 'backlogDelta', 'criticalOpen'].forEach(function (key) {
    _assert_(Number.isInteger(newsletter[key]),
      'projection.newsletterFacts.' + key + ' debe ser entero.', 'TRANSFER_INVALID');
  });
  _assert_(newsletter.backlogDelta === newsletter.metrics.currentOpen - newsletter.previousOpen,
    'El delta de backlog de la newsletter no es coherente.', 'TRANSFER_INVALID');
  _assertExactFields_(
    newsletter.evolution,
    ['tone', 'title', 'summary', 'focus', 'yearLabel', 'fortnightLabel'],
    'projection.newsletterFacts.evolution'
  );
  _assert_(['positive', 'negative', 'neutral', 'mixed'].indexOf(_text_(newsletter.evolution.tone)) >= 0,
    'El tono de evolución no es válido.', 'TRANSFER_INVALID');
  ['title', 'summary', 'yearLabel', 'fortnightLabel'].forEach(function (key) {
    _assert_(_sanitizeText_(newsletter.evolution[key], 4000),
      'projection.newsletterFacts.evolution.' + key + ' está vacío.', 'TRANSFER_INVALID');
  });
  _assert_(Array.isArray(newsletter.evolution.focus),
    'projection.newsletterFacts.evolution.focus debe ser una lista.', 'TRANSFER_INVALID');
  newsletter.evolution.focus.forEach(function (line) { _sanitizeText_(line, 1000); });
  _assert_(Array.isArray(newsletter.responsibleRollups),
    'projection.newsletterFacts.responsibleRollups debe ser una lista.', 'TRANSFER_INVALID');
  newsletter.responsibleRollups.forEach(function (row) {
    _assertExactFields_(
      row,
      ['name', 'dashboardUrl', 'openIssues', 'rootCauseEvolutives', 'finalistDiscrepancies'],
      'projection.newsletterFacts.responsibleRollups'
    );
    _assert_(_sanitizeText_(row.name, 300), 'El responsable de newsletter está vacío.', 'TRANSFER_INVALID');
    ['openIssues', 'rootCauseEvolutives', 'finalistDiscrepancies'].forEach(function (key) {
      _assert_(Number.isInteger(row[key]) && row[key] >= 0,
        'Un conteo por responsable no es válido.', 'TRANSFER_INVALID');
    });
    if (_text_(row.dashboardUrl)) _sanitizeUrl_(row.dashboardUrl);
  });
  _assertExactFields_(
    newsletter.draft,
    [
      'subject', 'greeting', 'intro', 'reportLinkLabel', 'summary',
      'responsibleIntro', 'responsibleParagraphs', 'closing'
    ],
    'projection.newsletterFacts.draft'
  );
  ['subject', 'greeting', 'intro', 'reportLinkLabel', 'summary', 'responsibleIntro', 'closing']
    .forEach(function (key) {
      _assert_(_sanitizeText_(newsletter.draft[key], 4000),
        'El borrador local de newsletter está incompleto.', 'TRANSFER_INVALID');
    });
  _assert_(Array.isArray(newsletter.draft.responsibleParagraphs),
    'Los párrafos por responsable no son válidos.', 'TRANSFER_INVALID');
  _assertCanonicalFactScalars_(newsletter, 'projection.newsletterFacts');
}

function _validateProjectionReport_(report, descriptor) {
  _assertExactFields_(report, ['fileName', 'mimeType', 'sha256', 'bytes', 'slideCount'], 'projection.report');
  _assert_(report.mimeType === REPORT_PPTX_MIME, 'La presentación debe ser un PPTX.', 'TRANSFER_INVALID');
  _assert_(/\.pptx$/i.test(_text_(report.fileName)) && _text_(report.fileName).length <= 240,
    'projection.report.fileName no es válido.', 'TRANSFER_INVALID');
  _assert_(_text_(report.sha256).toLowerCase() === _text_(descriptor.sha256).toLowerCase() &&
    Number(report.bytes) === Number(descriptor.bytes),
  'projection.report no coincide con el descriptor binario.', 'TRANSFER_INVALID');
  _assert_(Number.isInteger(report.slideCount) && report.slideCount > 0,
    'projection.report.slideCount no es válido.', 'TRANSFER_INVALID');
}

function _validateProjection_(projection, manifest, reportDescriptor) {
  _assertExactFields_(projection, [
    'schema', 'schemaVersion', 'semanticContract', 'generatedAt', 'scope',
    'semantics', 'administration', 'views', 'newsletterFacts', 'report', 'factsSha256'
  ], TRANSFER_LABELS.projection);
  _assert_(projection.schema === RADAR.projectionContract && projection.schemaVersion === RADAR.projectionVersion,
    'La proyección no pertenece al contrato GPC vigente.', 'TRANSFER_INVALID');
  _assert_(projection.semanticContract === RADAR.semanticContract &&
    manifest.semanticContract === RADAR.semanticContract,
  'El contrato semántico debe ser desktop-authoritative-v3.', 'TRANSFER_INVALID');
  _assert_(_date_(projection.generatedAt), 'projection.generatedAt no es una fecha válida.', 'TRANSFER_INVALID');
  const scope = _normalizeProjectionScope_(projection.scope, 'projection.scope');
  const manifestScope = _normalizeManifestScope_(manifest.scope, 'manifest.scope');
  _assert_(_stableJsonStringify_(scope) === _stableJsonStringify_(manifestScope),
    'El ámbito del manifest no coincide con la proyección.', 'TRANSFER_INVALID');
  _assertObject_(projection.semantics, 'projection.semantics no es un objeto de trazabilidad.');
  _assertExactFields_(projection.administration, ['jiraSources'], 'projection.administration');
  _assert_(Array.isArray(projection.administration.jiraSources),
    'projection.administration.jiraSources no es una lista.', 'TRANSFER_INVALID');
  const administrationSourceIds = new Set();
  projection.administration.jiraSources.forEach(function (row) {
    _assertExactFields_(
      row,
      ['sourceId', 'alias', 'poTeamLeader', 'dashboardUrl'],
      'projection.administration.jiraSources'
    );
    const sourceId = _sanitizeSourceId_(row.sourceId);
    _assert_(scope.sourceIds.indexOf(sourceId) >= 0 && !administrationSourceIds.has(sourceId),
      'Una fuente JIRA administrativa está duplicada o fuera del ámbito.',
      'TRANSFER_INVALID');
    administrationSourceIds.add(sourceId);
    _assert_(_sanitizeText_(row.alias, 300),
      'Una fuente JIRA administrativa no contiene alias.', 'TRANSFER_INVALID');
    _sanitizeText_(row.poTeamLeader, 300);
    if (_text_(row.dashboardUrl)) _sanitizeUrl_(row.dashboardUrl);
  });
  _assertExactFields_(projection.views, ['overview', 'insights', 'trends', 'issues'], 'projection.views');
  ['overview', 'insights', 'trends', 'issues'].forEach(function (view) {
    _assert_(projection.views[view] && typeof projection.views[view] === 'object',
      'La vista materializada «' + view + '» no está disponible.', 'TRANSFER_INVALID');
  });
  const expectedChartIds = [
    'timeseries', 'age_buckets', 'open_status_bar', 'open_priority_pie', 'resolution_hist'
  ];
  const overviewCharts = projection.views.overview.charts;
  _assert_(Array.isArray(overviewCharts) &&
    overviewCharts.map(function (chart) { return _text_(chart && chart.id); })
      .every(function (id, index) { return id === expectedChartIds[index]; }) &&
    overviewCharts.length === expectedChartIds.length,
  'El catálogo de gráficos de Resumen está incompleto.', 'TRANSFER_INVALID');
  _assertExactFields_(projection.views.trends, ['catalog', 'byId'], 'projection.views.trends');
  _assert_(Array.isArray(projection.views.trends.catalog), 'projection.views.trends.catalog no es una lista.', 'TRANSFER_INVALID');
  _assertObject_(projection.views.trends.byId, 'projection.views.trends.byId no es un objeto.');
  _assert_(
    projection.views.trends.catalog.length === expectedChartIds.length &&
    projection.views.trends.catalog.every(function (item, index) {
      return _text_(item && item.id) === expectedChartIds[index];
    }) &&
    Object.keys(projection.views.trends.byId).sort().join('|') ===
      expectedChartIds.slice().sort().join('|'),
    'El catálogo de Tendencias está incompleto.',
    'TRANSFER_INVALID'
  );
  _assertExactFields_(projection.views.issues, ['total', 'rows'], 'projection.views.issues');
  _assert_(Number.isInteger(projection.views.issues.total) && projection.views.issues.total >= 0 &&
    Array.isArray(projection.views.issues.rows) &&
    projection.views.issues.total === projection.views.issues.rows.length,
  'projection.views.issues debe contener todas sus filas materializadas.', 'TRANSFER_INVALID');
  const issueUids = new Set();
  projection.views.issues.rows.forEach(function (row) {
    _assertObject_(row, 'projection.views.issues contiene una fila no válida.');
    const issueUid = _text_(row.issue_uid);
    _assert_(issueUid && issueUid.indexOf('::') > 0 && !issueUids.has(issueUid),
      'Cada incidencia debe incluir un issue_uid compuesto y único.',
      'TRANSFER_INVALID');
    issueUids.add(issueUid);
  });
  _validateNoCloudActionsDeep_(projection.views, 'projection.views');
  _validateProjectionNewsletter_(projection.newsletterFacts);
  _validateProjectionReport_(projection.report, reportDescriptor);
  _assert_(/^[a-f0-9]{64}$/i.test(_text_(projection.factsSha256)) &&
    _hash_(_stableJsonStringify_(projection.newsletterFacts)) === _text_(projection.factsSha256).toLowerCase(),
  'projection.factsSha256 no coincide con newsletterFacts.', 'TRANSFER_INVALID');
  _validateNoSecretsDeep_(projection, 0, { count: 0 });
  return scope;
}

function _validatePptxBlob_(blob, descriptor, bytes) {
  _assert_(bytes.length > 0 && bytes.length <= RADAR.maxReportBytes &&
    bytes.length === Number(descriptor.bytes), 'El PPTX está vacío o supera el tamaño permitido.', 'TRANSFER_TOO_LARGE');
  _assert_(bytes.length >= 4 && _byte_(bytes[0]) === 0x50 && _byte_(bytes[1]) === 0x4b,
    'El artefacto de informe no es un PPTX válido.', 'TRANSFER_INVALID');
  _assert_(_sha256Bytes_(bytes) === _text_(descriptor.sha256).toLowerCase(),
    'La huella del PPTX no coincide con el manifest.', 'TRANSFER_INVALID');
  const names = _zipEntryNames_(blob, bytes, RADAR.maxReportBytes * 5);
  const files = new Set(names.filter(function (name) { return !/\/$/.test(name); }));
  _assert_(files.has('[Content_Types].xml') && files.has('ppt/presentation.xml'),
    'El artefacto no contiene una presentación Office válida.', 'TRANSFER_INVALID');
  _assert_(!names.some(function (name) {
    return /(^|\/)(vbaProject\.bin|activeX\/|embeddings\/)/i.test(name);
  }), 'El PPTX contiene elementos ejecutables o incrustados no permitidos.', 'TRANSFER_INVALID');
  return bytes.length;
}

function _validateDatasetDescriptor_(descriptor, key, entry) {
  _assertExactFields_(descriptor, ['path', 'sha256', 'bytes', 'records'], 'datasets.' + key);
  _assert_(descriptor.path === TRANSFER_FILES[key], 'datasets.' + key + '.path no coincide.', 'TRANSFER_INVALID');
  _assert_(/^[a-f0-9]{64}$/i.test(_text_(descriptor.sha256)), 'datasets.' + key + '.sha256 no es válido.', 'TRANSFER_INVALID');
  _assert_(Number.isInteger(descriptor.bytes) && descriptor.bytes > 0,
    'datasets.' + key + '.bytes no es válido.', 'TRANSFER_INVALID');
  _assert_(descriptor.records === 1, 'datasets.' + key + '.records debe ser 1.', 'TRANSFER_INVALID');
  const bytes = entry.getBytes();
  _assert_(bytes.length === descriptor.bytes && _sha256Bytes_(bytes) === _text_(descriptor.sha256).toLowerCase(),
    'El contenido de «' + TRANSFER_LABELS[key] + '» no coincide con el manifest.', 'TRANSFER_INVALID');
  return bytes;
}

function _decodeTransferPackage_(archiveBlob) {
  _assert_(archiveBlob && typeof archiveBlob.getBytes === 'function', 'Selecciona un fichero .brr.', 'TRANSFER_INVALID');
  const fileName = _text_(archiveBlob.getName());
  const archiveBytes = archiveBlob.getBytes();
  _assert_(/\.brr$/i.test(fileName), 'Selecciona un traslado .brr v3.', 'TRANSFER_INVALID');
  _assert_(archiveBytes.length > 0 && archiveBytes.length <= RADAR.maxTransferBytes,
    'El respaldo está vacío o supera el tamaño máximo de ' + Math.floor(RADAR.maxTransferBytes / 1048576) + ' MB.',
    'TRANSFER_TOO_LARGE');
  const entries = _transferEntryMap_(archiveBlob, archiveBytes);
  const manifest = _entryJson_(entries, 'manifest.json', 'manifest');
  _assertExactFields_(manifest, ['format', 'version', 'createdAt', 'scope', 'semanticContract', 'datasets'], 'manifest');
  _assert_(manifest.format === RADAR.transferFormat && manifest.version === RADAR.transferVersion,
    'Solo se admite el contrato de traslado v3.', 'TRANSFER_INVALID');
  _assert_(manifest.semanticContract === RADAR.semanticContract,
    'El respaldo no fue generado con el racional autoritativo del escritorio.', 'TRANSFER_INVALID');
  _assert_(_date_(manifest.createdAt), 'manifest.createdAt no es una fecha válida.', 'TRANSFER_INVALID');
  _assertExactFields_(manifest.datasets, ['projection', 'report'], 'manifest.datasets');
  const projectionBytes = _validateDatasetDescriptor_(
    manifest.datasets.projection, 'projection', entries[TRANSFER_FILES.projection]
  );
  const reportBytes = _validateDatasetDescriptor_(
    manifest.datasets.report, 'report', entries[TRANSFER_FILES.report]
  );
  _assert_(manifest.datasets.projection.bytes <= RADAR.maxProjectionBytes,
    'La proyección supera el tamaño permitido.', 'TRANSFER_TOO_LARGE');
  _assert_(manifest.datasets.report.bytes <= RADAR.maxReportBytes,
    'El PPTX supera el tamaño permitido.', 'TRANSFER_TOO_LARGE');
  const projectionText = Utilities.newBlob(projectionBytes, 'application/json').getDataAsString('UTF-8');
  let projection;
  try {
    projection = JSON.parse(projectionText);
  } catch (err) {
    throw Object.assign(new Error('No se puede leer «' + TRANSFER_LABELS.projection + '».'), { code: 'TRANSFER_INVALID' });
  }
  const scope = _validateProjection_(projection, manifest, manifest.datasets.report);
  _validatePptxBlob_(entries[TRANSFER_FILES.report], manifest.datasets.report, reportBytes);
  return {
    fileName: fileName,
    fileSha256: _sha256Bytes_(archiveBytes),
    fileSize: archiveBytes.length,
    createdAt: String(manifest.createdAt),
    dataVersion: scope.dataVersion,
    semanticContract: manifest.semanticContract,
    scope: scope,
    scopeKey: scope.scopeKey,
    projection: projection,
    projectionText: projectionText,
    projectionSha256: _text_(manifest.datasets.projection.sha256).toLowerCase(),
    projectionBytes: manifest.datasets.projection.bytes,
    reportBlob: entries[TRANSFER_FILES.report].setName(_text_(projection.report.fileName)),
    reportSha256: _text_(manifest.datasets.report.sha256).toLowerCase(),
    reportBytes: manifest.datasets.report.bytes
  };
}

function _transferPreview_(decoded) {
  const active = _activeSnapshotRecordForScope_(decoded.scopeKey, false);
  const same = active && _text_(active.projection_sha256) === decoded.projectionSha256;
  return {
    valid: true,
    summary: same
      ? 'La proyección ya está publicada para este ámbito; la confirmación será idempotente.'
      : 'Proyección y PPTX verificados. La confirmación publicará el snapshot de forma atómica.',
    fileName: decoded.fileName,
    fileSize: decoded.fileSize,
    createdAt: decoded.createdAt,
    mode: 'replace-scope-snapshot',
    scopeKey: decoded.scopeKey,
    country: decoded.scope.country,
    sourceIds: decoded.scope.sourceIds,
    semanticContract: decoded.semanticContract,
    totalSourceRecords: 2,
    totalNewRecords: same ? 0 : 1,
    totalUpdatedRecords: active && !same ? 1 : 0,
    totalUnchangedRecords: same ? 1 : 0,
    stats: [
      { key: 'projection', label: TRANSFER_LABELS.projection, sourceCount: 1, destinationCount: active ? 1 : 0,
        newCount: active ? 0 : 1, updatedCount: active && !same ? 1 : 0, unchangedCount: same ? 1 : 0, finalCount: 1 },
      { key: 'report', label: TRANSFER_LABELS.report, sourceCount: 1, destinationCount: active ? 1 : 0,
        newCount: active ? 0 : 1, updatedCount: active && !same ? 1 : 0, unchangedCount: same ? 1 : 0, finalCount: 1 }
    ],
    warnings: []
  };
}
