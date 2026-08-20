/** Durable sectional L2 snapshots. CacheService is an optional per-part L1 only. */
function _materializedScopeKey_(country, sourceIds) {
  const sources = Array.from(new Set((sourceIds || []).map(_text_).filter(Boolean))).sort();
  return _fold_(country) + '::' + (sources.length === 1 ? sources[0] : '*');
}

function _isCurrentSnapshotRecord_(record) {
  return Boolean(
    record &&
    _text_(record.projection_contract) === RADAR.projectionContract &&
    Number(record.projection_version) === Number(RADAR.projectionVersion)
  );
}

function _snapshotRecordById_(snapshotId, required) {
  const id = _text_(snapshotId);
  const record = _readRecords_(RADAR.sheets.snapshots).find(function (row) {
    return _text_(row.snapshot_id) === id;
  }) || null;
  const current = _isCurrentSnapshotRecord_(record) ? record : null;
  if (required !== false) {
    _assert_(current,
      'El snapshot solicitado no pertenece al contrato vigente. Importa un traslado v3.',
      'SNAPSHOT_NOT_FOUND');
  }
  return current;
}

function _activeSnapshotPointers_() {
  return _readRecords_(RADAR.sheets.snapshotPointers);
}

function _activeSnapshotRecordForScope_(scopeKey, required) {
  const key = _text_(scopeKey);
  const pointer = _activeSnapshotPointers_().find(function (row) {
    return _text_(row.scope_key) === key;
  }) || null;
  if (!pointer) {
    if (required !== false) {
      _assert_(false,
        'No hay una proyección publicada para este ámbito. Importa un traslado v3 desde escritorio.',
        'SNAPSHOT_NOT_FOUND');
    }
    return null;
  }
  return _snapshotRecordById_(pointer.snapshot_id, required);
}

function _projectionPartValues_(projection) {
  const parts = {};
  parts.meta = {
    schema: projection.schema,
    schemaVersion: projection.schemaVersion,
    semanticContract: projection.semanticContract,
    generatedAt: projection.generatedAt,
    scope: projection.scope,
    semantics: projection.semantics,
    report: projection.report,
    factsSha256: projection.factsSha256
  };
  parts.administration = projection.administration;
  parts.newsletter = projection.newsletterFacts;
  parts.overview = projection.views.overview;
  parts['insights/catalog'] = projection.views.insights.catalog;
  Object.keys(projection.views.insights.byId).sort().forEach(function (id) {
    parts['insights/' + id] = projection.views.insights.byId[id];
  });
  parts['trends/catalog'] = projection.views.trends.catalog;
  Object.keys(projection.views.trends.byId).sort().forEach(function (id) {
    parts['trends/' + id] = projection.views.trends.byId[id];
  });
  const issueRows = projection.views.issues.rows;
  const pageSize = RADAR.defaultPageSize;
  const pageCount = Math.max(1, Math.ceil(issueRows.length / pageSize));
  const byUid = {};
  const keyOccurrences = {};
  for (let page = 1; page <= pageCount; page += 1) {
    const start = (page - 1) * pageSize;
    const rows = issueRows.slice(start, start + pageSize);
    rows.forEach(function (row) {
      const issueKey = _text_(row && row.key);
      const issueUid = _text_(row && (row.issue_uid || row.issueUid));
      _assert_(issueKey, 'projection.views.issues contiene una clave vacía.', 'TRANSFER_INVALID');
      if (issueUid) {
        _assert_(!Object.prototype.hasOwnProperty.call(byUid, issueUid),
          'projection.views.issues contiene issue_uid duplicados.', 'TRANSFER_INVALID');
        byUid[issueUid] = page;
      }
      if (!keyOccurrences[issueKey]) keyOccurrences[issueKey] = [];
      keyOccurrences[issueKey].push(page);
    });
    parts['issues/page/' + page] = {
      totalRows: issueRows.length,
      page: page,
      pageSize: pageSize,
      rows: rows
    };
  }
  parts['issues/meta'] = {
    totalRows: issueRows.length,
    pageSize: pageSize,
    pageCount: pageCount
  };
  const byKey = {};
  Object.keys(keyOccurrences).forEach(function (issueKey) {
    if (keyOccurrences[issueKey].length === 1) byKey[issueKey] = keyOccurrences[issueKey][0];
  });
  parts['issues/index'] = { byUid: byUid, byKey: byKey };
  return parts;
}

function _appendSnapshotParts_(snapshotId, projection, createdAt) {
  const values = _projectionPartValues_(projection);
  const keys = Object.keys(values).sort();
  const rows = [];
  const descriptors = [];
  const partRows = [];
  keys.forEach(function (key) {
    _assert_(/^[a-z0-9][a-z0-9_./:-]{0,199}$/i.test(key),
      'La proyección contiene una clave de parte no válida.', 'TRANSFER_INVALID');
    const text = _safeJsonStringify_(_webSafe_(values[key]));
    const utf8Bytes = Utilities.newBlob(text, 'application/json').getBytes();
    const encoded = Utilities.base64Encode(utf8Bytes);
    const partUid = snapshotId + '::' + _hash_(key).slice(0, 24);
    const chunks = Math.max(1, Math.ceil(encoded.length / RADAR.snapshotChunkSize));
    const partSha256 = _hash_(text);
    const partBytes = utf8Bytes.length;
    descriptors.push({
      key: key,
      uid: partUid,
      sha256: partSha256,
      bytes: partBytes,
      chunks: chunks
    });
    partRows.push({
      part_uid: partUid,
      snapshot_id: snapshotId,
      part_key: key,
      part_sha256: partSha256,
      part_bytes: partBytes,
      chunk_count: chunks,
      created_at: createdAt
    });
    for (let index = 0; index < chunks; index += 1) {
      // Base64 is ASCII, never splits UTF-16 surrogate pairs, and the b64:
      // prefix prevents Sheets from interpreting any chunk as a formula.
      const content = 'b64:' + encoded.slice(
        index * RADAR.snapshotChunkSize,
        (index + 1) * RADAR.snapshotChunkSize
      );
      rows.push({
        chunk_uid: partUid + '::' + ('00000' + index).slice(-5),
        snapshot_id: snapshotId,
        part_uid: partUid,
        part_key: key,
        chunk_index: index,
        content_json: content,
        chunk_sha256: _hash_(content),
        created_at: createdAt
      });
    }
  });
  _assert_(rows.length > 0, 'La proyección no contiene partes materializables.', 'TRANSFER_INVALID');
  _appendRecords_(RADAR.sheets.snapshotParts, partRows);
  // Keep every Sheets write comfortably below the service payload ceiling.
  // Chunk identifiers are deterministic and unique across these bounded batches.
  const writeBatchSize = 20;
  for (let offset = 0; offset < rows.length; offset += writeBatchSize) {
    _appendRecords_(
      RADAR.sheets.snapshotChunks,
      rows.slice(offset, offset + writeBatchSize)
    );
  }
  return { chunkCount: rows.length, partCount: descriptors.length };
}

function _snapshotPartDescriptor_(record, partKey, required) {
  const key = _text_(partKey);
  const partUid = _text_(record && record.snapshot_id) + '::' + _hash_(key).slice(0, 24);
  const memoKey = 'snapshotPartDescriptor:' + partUid;
  const memo = _runtimeMemo_();
  if (Object.prototype.hasOwnProperty.call(memo.values, memoKey)) {
    const memoized = memo.values[memoKey];
    if (required !== false) {
      _assert_(memoized, 'La variante «' + key + '» no fue materializada por escritorio.',
        'VIEW_NOT_MATERIALIZED');
    }
    return memoized;
  }
  const matches = _readRecords_(RADAR.sheets.snapshotParts).filter(function (row) {
    return _text_(row.part_uid) === partUid;
  });
  _assert_(matches.length <= 1, 'El índice durable contiene partes duplicadas.', 'SNAPSHOT_CORRUPT');
  let descriptor = null;
  if (matches.length === 1) {
    const stored = matches[0];
    _assert_(
      _text_(stored.snapshot_id) === _text_(record.snapshot_id) &&
      _text_(stored.part_key) === key,
      'El descriptor de la parte no coincide con el snapshot.', 'SNAPSHOT_CORRUPT'
    );
    descriptor = {
      key: _text_(stored.part_key),
      uid: _text_(stored.part_uid),
      sha256: _text_(stored.part_sha256),
      bytes: Number(stored.part_bytes),
      chunks: Number(stored.chunk_count)
    };
  }
  memo.values[memoKey] = descriptor;
  if (required !== false) {
    _assert_(descriptor, 'La variante «' + key + '» no fue materializada por escritorio.',
      'VIEW_NOT_MATERIALIZED');
  }
  return descriptor;
}

function _snapshotPartRows_(descriptor) {
  _validateSheetContract_(RADAR.sheets.snapshotChunks);
  const sheet = _sheet_(RADAR.sheets.snapshotChunks);
  const headers = _headersFor_(RADAR.sheets.snapshotChunks);
  const partColumn = headers.indexOf('part_uid') + 1;
  _assert_(sheet.getLastRow() >= 2, 'Los chunks del snapshot no están disponibles.', 'SNAPSHOT_CORRUPT');
  const matches = sheet.getRange(2, partColumn, sheet.getLastRow() - 1, 1)
    .createTextFinder(_text_(descriptor.uid))
    .matchEntireCell(true)
    .findAll();
  _assert_(matches.length === Number(descriptor.chunks),
    'Los chunks de una parte del snapshot están incompletos.', 'SNAPSHOT_CORRUPT');
  const rowNumbers = matches.map(function (range) { return range.getRow(); }).sort(function (a, b) { return a - b; });
  _assert_(rowNumbers.every(function (row, index) {
    return index === 0 || row === rowNumbers[index - 1] + 1;
  }), 'Los chunks de una parte no son contiguos.', 'SNAPSHOT_CORRUPT');
  return sheet.getRange(rowNumbers[0], 1, rowNumbers.length, headers.length).getValues().map(function (row) {
    return _rowToRecord_(headers, row);
  });
}

function _loadSnapshotPart_(record, partKey) {
  _assert_(record && record.snapshot_id, 'El snapshot no está disponible.', 'SNAPSHOT_NOT_FOUND');
  const descriptor = _snapshotPartDescriptor_(record, partKey, true);
  const cache = CacheService.getScriptCache();
  const cacheKey = _cacheKey_('snapshot-part:' + _text_(record.snapshot_id), {
    part: descriptor.key,
    sha256: descriptor.sha256
  });
  const cached = _cacheGetJson_(cache, cacheKey);
  if (cached != null) return cached;
  const rows = _snapshotPartRows_(descriptor)
    .sort(function (left, right) { return Number(left.chunk_index) - Number(right.chunk_index); });
  let encoded = '';
  rows.forEach(function (row, index) {
    const content = String(row.content_json);
    _assert_(
      _text_(row.part_uid) === _text_(descriptor.uid) &&
      _text_(row.part_key) === _text_(descriptor.key) &&
      Number(row.chunk_index) === index &&
      _hash_(content) === _text_(row.chunk_sha256),
      'Una parte del snapshot no supera la validación de integridad.',
      'SNAPSHOT_CORRUPT'
    );
    _assert_(content.indexOf('b64:') === 0,
      'Una parte durable usa una codificación no admitida.', 'SNAPSHOT_CORRUPT');
    encoded += content.slice(4);
  });
  let decodedBytes;
  try {
    decodedBytes = Utilities.base64Decode(encoded);
  } catch (err) {
    throw Object.assign(new Error('Una parte durable no contiene Base64 válido.'),
      { code: 'SNAPSHOT_CORRUPT' });
  }
  const text = Utilities.newBlob(decodedBytes, 'application/json').getDataAsString('UTF-8');
  _assert_(
    decodedBytes.length === Number(descriptor.bytes) &&
    _hash_(text) === _text_(descriptor.sha256),
    'La parte durable no coincide con su huella.',
    'SNAPSHOT_CORRUPT'
  );
  const value = _safeJsonParse_(text, undefined);
  _assert_(value !== undefined, 'La parte durable no contiene JSON válido.', 'SNAPSHOT_CORRUPT');
  _cachePutJson_(cache, cacheKey, value, RADAR.cacheSeconds);
  return value;
}

function _snapshotHeader_(record) {
  const meta = _loadSnapshotPart_(record, 'meta');
  _assert_(
    meta.schema === RADAR.projectionContract &&
    meta.schemaVersion === RADAR.projectionVersion &&
    meta.semanticContract === RADAR.semanticContract &&
    meta.scope && meta.scope.scopeKey === _text_(record.scope_key) &&
    meta.scope.dataVersion === _text_(record.data_version) &&
    meta.factsSha256 === _text_(record.facts_sha256),
    'La cabecera del snapshot no coincide con su índice.',
    'SNAPSHOT_CORRUPT'
  );
  return meta;
}

function _snapshotNewsletter_(record) {
  const newsletter = _loadSnapshotPart_(record, 'newsletter');
  _assert_(_hash_(_stableJsonStringify_(newsletter)) === _text_(record.facts_sha256),
    'Los hechos de newsletter no coinciden con el snapshot.', 'SNAPSHOT_CORRUPT');
  return newsletter;
}

function _snapshotAdministration_(record) {
  return _loadSnapshotPart_(record, 'administration');
}

function _snapshotIssueDetail_(record, issueKey) {
  const key = _text_(issueKey);
  const index = _loadSnapshotPart_(record, 'issues/index');
  const page = Number(
    index && (
      (index.byUid && index.byUid[key]) ||
      (index.byKey && index.byKey[key])
    )
  );
  if (!page) return null;
  const payload = _loadSnapshotPart_(record, 'issues/page/' + page);
  return (payload.rows || []).find(function (row) {
    return _text_(row.issue_uid || row.issueUid) === key || _text_(row.key) === key;
  }) || null;
}

function _publishSnapshotPointer_(record, user) {
  return _upsertRecord_(RADAR.sheets.snapshotPointers, {
    scope_key: record.scope_key,
    snapshot_id: record.snapshot_id,
    data_version: record.data_version,
    activated_at: _nowIso_(),
    activated_by: user.email
  });
}

function _normalizeMaterializedRequest_(request, fixedScopeKey) {
  const input = request || {};
  const allowed = new Set(['scopeKey', 'view', 'chartId', 'insightsId', 'page', 'pageSize', 'sortId']);
  Object.keys(input).forEach(function (key) {
    _assert_(allowed.has(key),
      'La vista materializada no admite el parámetro «' + key + '».',
      'VIEW_NOT_MATERIALIZED');
  });
  const scopeKey = _text_(fixedScopeKey || input.scopeKey);
  _assert_(scopeKey, 'Selecciona un ámbito materializado.', 'SNAPSHOT_NOT_FOUND');
  if (fixedScopeKey) {
    _assert_(!input.scopeKey || _text_(input.scopeKey) === scopeKey,
      'El enlace compartido no permite cambiar de ámbito.', 'FORBIDDEN');
  }
  const view = _text_(input.view) || 'overview';
  _assert_(['overview', 'insights', 'trends', 'issues'].indexOf(view) >= 0,
    'La vista solicitada no está materializada.', 'VIEW_NOT_MATERIALIZED');
  const page = Math.max(1, Math.floor(Number(input.page || 1)));
  const pageSize = Number(input.pageSize == null ? RADAR.defaultPageSize : input.pageSize);
  _assert_(pageSize === RADAR.defaultPageSize,
    'La paginación está fijada en ' + RADAR.defaultPageSize + ' filas por el snapshot.',
    'VIEW_NOT_MATERIALIZED');
  const sortId = _text_(input.sortId) || 'default';
  _assert_(sortId === 'default',
    'Ese orden no fue materializado por la aplicación de escritorio.',
    'VIEW_NOT_MATERIALIZED');
  return {
    scopeKey: scopeKey,
    view: view,
    chartId: _text_(input.chartId),
    insightsId: _text_(input.insightsId),
    page: page,
    pageSize: pageSize,
    sortId: sortId
  };
}

function _materializedCatalogId_(catalog, requested, fallback) {
  const ids = (catalog || []).map(function (item) { return _text_(item && item.id); }).filter(Boolean);
  const selected = _text_(requested) || _text_(fallback) || ids[0];
  _assert_(selected && ids.indexOf(selected) >= 0,
    'La variante solicitada no fue materializada.', 'VIEW_NOT_MATERIALIZED');
  return selected;
}

function _materializedCommonPayload_(record, input) {
  return {
    snapshotId: _text_(record.snapshot_id),
    projectionSha256: _text_(record.projection_sha256),
    dataVersion: _text_(record.data_version),
    scopeVersion: _text_(record.data_version),
    scopeKey: _text_(record.scope_key),
    page: input.page,
    pageSize: input.pageSize
  };
}

function _materializedViewPayload_(record, input) {
  const common = _materializedCommonPayload_(record, input);
  if (input.view === 'overview') {
    const storedOverview = _loadSnapshotPart_(record, 'overview');
    const overview = Object.assign({}, storedOverview);
    const availableCharts = Array.isArray(storedOverview.charts)
      ? storedOverview.charts
      : [];
    const configured = _configuredSummaryChartIds_();
    overview.charts = configured.map(function (chartId) {
      return availableCharts.find(function (chart) {
        return _text_(chart && chart.id) === chartId;
      });
    }).filter(Boolean);
    return Object.assign({}, common, overview);
  }
  if (input.view === 'insights') {
    const catalog = _loadSnapshotPart_(record, 'insights/catalog');
    const activeId = _materializedCatalogId_(catalog, input.insightsId, 'evolution');
    const selected = _loadSnapshotPart_(record, 'insights/' + activeId);
    const insights = {
      tabs: catalog,
      activeTab: activeId
    };
    if (activeId === 'evolution') insights.executionEvolution = selected.executionEvolution || selected;
    else if (activeId === 'summary') insights.periodSummary = selected.periodSummary || selected;
    else insights[activeId] = selected || {};
    return Object.assign({}, common, { insights: insights });
  }
  if (input.view === 'trends') {
    const catalog = _loadSnapshotPart_(record, 'trends/catalog');
    const chartId = _materializedCatalogId_(catalog, input.chartId, 'open_status_bar');
    const selected = _loadSnapshotPart_(record, 'trends/' + chartId);
    return Object.assign({}, common, {
      trends: Object.assign({
        chartCatalog: catalog,
        selectedChartId: chartId
      }, selected || {})
    });
  }
  if (input.view === 'issues') {
    const meta = _loadSnapshotPart_(record, 'issues/meta');
    _assert_(input.page <= Number(meta.pageCount),
      'Esa página no fue materializada.', 'VIEW_NOT_MATERIALIZED');
    return Object.assign({}, common, _loadSnapshotPart_(record, 'issues/page/' + input.page));
  }
  _assert_(false, 'La vista solicitada no está materializada.', 'VIEW_NOT_MATERIALIZED');
}

function _dashboardPayloadFromSnapshot_(snapshotId, request, fixedScopeKey) {
  const record = _snapshotRecordById_(snapshotId, true);
  const input = _normalizeMaterializedRequest_(request, fixedScopeKey || record.scope_key);
  _assert_(input.scopeKey === _text_(record.scope_key),
    'El snapshot no pertenece al ámbito solicitado.', 'FORBIDDEN');
  return _materializedViewPayload_(record, input);
}

function _dashboardPayload_(request) {
  const input = _normalizeMaterializedRequest_(request);
  const record = _activeSnapshotRecordForScope_(input.scopeKey, true);
  const cache = CacheService.getScriptCache();
  const cacheKey = _cacheKey_('dashboard-view:' + _text_(record.snapshot_id), input);
  const cached = _cacheGetJson_(cache, cacheKey);
  if (cached != null) return cached;
  const payload = _materializedViewPayload_(record, input);
  _cachePutJson_(cache, cacheKey, payload, RADAR.cacheSeconds);
  return payload;
}

function _workspaceManifest_() {
  const pointers = _activeSnapshotPointers_();
  const snapshots = _readRecords_(RADAR.sheets.snapshots);
  const byId = {};
  snapshots.forEach(function (row) { byId[_text_(row.snapshot_id)] = row; });
  const scopes = [];
  const sourceMap = {};
  const versions = {};
  pointers.forEach(function (pointer) {
    const record = byId[_text_(pointer.snapshot_id)];
    if (!_isCurrentSnapshotRecord_(record)) return;
    const sourceIds = _safeJsonParse_(record.source_ids_json, []) || [];
    scopes.push({
      scopeKey: _text_(record.scope_key),
      scopeLabel: _text_(record.scope_label),
      country: _text_(record.country),
      sourceIds: sourceIds,
      dataVersion: _text_(record.data_version),
      snapshotId: _text_(record.snapshot_id),
      activatedAt: pointer.activated_at
    });
    versions[_text_(record.scope_key)] = _text_(record.data_version);
    sourceIds.forEach(function (sourceId) {
      const mapKey = _text_(record.country) + '\u001f' + _text_(sourceId);
      if (!sourceMap[mapKey]) {
        sourceMap[mapKey] = {
          source_id: _text_(sourceId),
          source_type: 'materialized',
          alias: _text_(sourceId),
          country: _text_(record.country)
        };
      }
    });
  });
  scopes.sort(function (left, right) {
    return left.scopeLabel.localeCompare(right.scopeLabel, 'es', { sensitivity: 'base' });
  });
  const countries = Array.from(new Set(scopes.map(function (scope) { return scope.country; })))
    .sort(function (left, right) {
      return left.localeCompare(right, 'es', { sensitivity: 'base' });
    });
  return {
    scopes: scopes,
    countries: countries,
    sources: Object.keys(sourceMap).map(function (key) { return sourceMap[key]; }).sort(function (left, right) {
      return left.country.localeCompare(right.country, 'es') ||
        left.alias.localeCompare(right.alias, 'es');
    }),
    scopeVersions: versions
  };
}

function _trashDriveFileQuietly_(fileId) {
  const id = _text_(fileId);
  if (!id) return;
  try {
    Drive.Files.update({ trashed: true }, id, null, { supportsAllDrives: true });
  } catch (err) {
    console.warn('snapshot_file_trash_failed', { fileId: id });
  }
}

function _deleteSnapshotChunkRows_(snapshotIds) {
  const targets = new Set((snapshotIds || []).map(_text_).filter(Boolean));
  if (!targets.size) return 0;
  const sheet = _sheet_(RADAR.sheets.snapshotChunks);
  const headers = _headersFor_(RADAR.sheets.snapshotChunks);
  const snapshotColumn = headers.indexOf('snapshot_id');
  if (sheet.getLastRow() < 2) return 0;
  const values = sheet.getRange(2, snapshotColumn + 1, sheet.getLastRow() - 1, 1).getDisplayValues();
  const rows = [];
  values.forEach(function (value, index) {
    if (targets.has(_text_(value[0]))) rows.push(index + 2);
  });
  const groups = [];
  rows.forEach(function (row) {
    const last = groups[groups.length - 1];
    if (last && row === last.start + last.count) last.count += 1;
    else groups.push({ start: row, count: 1 });
  });
  groups.sort(function (left, right) { return right.start - left.start; }).forEach(function (group) {
    sheet.deleteRows(group.start, group.count);
  });
  if (rows.length) _forgetSheet_(RADAR.sheets.snapshotChunks);
  return rows.length;
}

function _deleteSnapshotPartRows_(snapshotIds) {
  const targets = new Set((snapshotIds || []).map(_text_).filter(Boolean));
  if (!targets.size) return 0;
  const sheet = _sheet_(RADAR.sheets.snapshotParts);
  const headers = _headersFor_(RADAR.sheets.snapshotParts);
  const snapshotColumn = headers.indexOf('snapshot_id');
  if (sheet.getLastRow() < 2) return 0;
  const values = sheet.getRange(
    2,
    snapshotColumn + 1,
    sheet.getLastRow() - 1,
    1
  ).getDisplayValues();
  const rows = [];
  values.forEach(function (value, index) {
    if (targets.has(_text_(value[0]))) rows.push(index + 2);
  });
  const groups = [];
  rows.forEach(function (row) {
    const last = groups[groups.length - 1];
    if (last && row === last.start + last.count) last.count += 1;
    else groups.push({ start: row, count: 1 });
  });
  groups.sort(function (left, right) {
    return right.start - left.start;
  }).forEach(function (group) {
    sheet.deleteRows(group.start, group.count);
  });
  if (rows.length) _forgetSheet_(RADAR.sheets.snapshotParts);
  return rows.length;
}

function _garbageCollectOrphanSnapshotChunks_() {
  const known = new Set(_readRecords_(RADAR.sheets.snapshots).map(function (row) {
    return _text_(row.snapshot_id);
  }));
  const sheet = _sheet_(RADAR.sheets.snapshotChunks);
  const headers = _headersFor_(RADAR.sheets.snapshotChunks);
  const snapshotColumn = headers.indexOf('snapshot_id');
  if (sheet.getLastRow() < 2) return 0;
  const values = sheet.getRange(2, snapshotColumn + 1, sheet.getLastRow() - 1, 1).getDisplayValues();
  const orphanIds = new Set();
  values.forEach(function (value) {
    const id = _text_(value[0]);
    if (id && !known.has(id)) orphanIds.add(id);
  });
  return _deleteSnapshotChunkRows_(Array.from(orphanIds));
}

function _garbageCollectOrphanSnapshotParts_() {
  const known = new Set(_readRecords_(RADAR.sheets.snapshots).map(function (row) {
    return _text_(row.snapshot_id);
  }));
  const orphanIds = new Set();
  _readRecords_(RADAR.sheets.snapshotParts).forEach(function (row) {
    const id = _text_(row.snapshot_id);
    if (id && !known.has(id)) orphanIds.add(id);
  });
  return _deleteSnapshotPartRows_(Array.from(orphanIds));
}

function _garbageCollectSnapshots_(scopeKey) {
  const key = _text_(scopeKey);
  const active = _activeSnapshotRecordForScope_(key, true);
  const candidates = _readRecords_(RADAR.sheets.snapshots).filter(function (row) {
    return _text_(row.scope_key) === key;
  }).sort(function (left, right) {
    return (_date_(right.created_at) || 0) - (_date_(left.created_at) || 0);
  });
  const keep = new Set([_text_(active.snapshot_id)]);
  const previous = candidates.find(function (row) {
    return !keep.has(_text_(row.snapshot_id));
  });
  if (previous) keep.add(_text_(previous.snapshot_id));
  const remove = candidates.filter(function (row) {
    return !keep.has(_text_(row.snapshot_id));
  });
  if (!remove.length) {
    return {
      removedSnapshots: 0,
      removedChunks: _garbageCollectOrphanSnapshotChunks_(),
      removedParts: _garbageCollectOrphanSnapshotParts_()
    };
  }
  const removeIds = remove.map(function (row) { return _text_(row.snapshot_id); });
  _readRecords_(RADAR.sheets.reportShares).filter(function (share) {
    return removeIds.indexOf(_text_(share.snapshot_id)) >= 0 && share.active === true;
  }).forEach(function (share) {
    _upsertRecord_(RADAR.sheets.reportShares, Object.assign({}, share, { active: false }));
  });
  remove.forEach(function (record) {
    _trashDriveFileQuietly_(record.pptx_file_id);
    _trashDriveFileQuietly_(record.slides_file_id);
  });
  const removedChunks = _deleteSnapshotChunkRows_(removeIds);
  const removedParts = _deleteSnapshotPartRows_(removeIds);
  removeIds.forEach(function (snapshotId) {
    _deleteRecord_(RADAR.sheets.snapshots, snapshotId);
  });
  return {
    removedSnapshots: removeIds.length,
    removedChunks: removedChunks + _garbageCollectOrphanSnapshotChunks_(),
    removedParts: removedParts + _garbageCollectOrphanSnapshotParts_()
  };
}
