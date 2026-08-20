/** Application orchestration, authorization and atomic transfer publication. */
function _activeEmail_() {
  return _canonicalEmail_(Session.getActiveUser().getEmail());
}

function _requireUser_() {
  const email = _activeEmail_();
  _assert_(email, 'Debes abrir la aplicación con tu cuenta corporativa.', 'AUTH_REQUIRED');
  _assert_(email.endsWith('@' + RADAR.allowedDomain),
    'La cuenta no pertenece al dominio autorizado.', 'FORBIDDEN');
  let user = _readRecords_(RADAR.sheets.users).find(function (row) {
    return _canonicalEmail_(row.email) === email;
  });
  if (!user) {
    user = _upsertRecord_(RADAR.sheets.users, {
      email: email,
      role: 'viewer',
      active: true,
      display_name: email.split('@')[0],
      updated_at: _nowIso_(),
      updated_by: email
    });
  }
  return {
    email: email,
    role: user.active === true && _text_(user.role) === 'admin' ? 'admin' : 'viewer',
    displayName: _text_(user.display_name)
  };
}

function _requireAdmin_() {
  const user = _requireUser_();
  _assert_(user.role === 'admin', 'Esta operación requiere rol administrador.', 'FORBIDDEN');
  return user;
}

function _initialDashboardState_(manifest) {
  const scopes = (manifest && manifest.scopes) || [];
  return {
    panel: 'overview',
    scopeKey: scopes.length ? _text_(scopes[0].scopeKey) : '',
    trendChart: 'open_status_bar',
    insightsId: 'evolution',
    issuesView: 'Cards',
    page: 1,
    pageSize: RADAR.defaultPageSize
  };
}

function getBootstrap() {
  return _rpc_(function () {
    const user = _requireUser_();
    const manifest = _workspaceManifest_();
    const reportDriveFolder = user.role === 'admin' ? _reportDriveFolderSetting_() : null;
    const initialState = _initialDashboardState_(manifest);
    let dashboard = null;
    if (initialState.scopeKey) {
      dashboard = _dashboardPayload_({
        scopeKey: initialState.scopeKey,
        view: initialState.panel,
        chartId: initialState.trendChart,
        insightsId: initialState.insightsId,
        page: 1,
        pageSize: RADAR.defaultPageSize,
        sortId: 'default'
      });
    }
    return {
      app: {
        name: RADAR.appName,
        version: RADAR.appVersion,
        contractVersion: RADAR.contractVersion,
        semanticContract: RADAR.semanticContract,
        dataVersion: _dataVersion_(),
        cacheEpoch: _cacheEpoch_(),
        maxTransferBytes: RADAR.maxTransferBytes,
        scopeVersions: manifest.scopeVersions,
        materializedOnly: true,
        issueFiltersEnabled: false
      },
      user: user,
      scopes: manifest.scopes,
      countries: manifest.countries,
      sources: manifest.sources,
      administration: user.role === 'admin' ? {
        reportDriveFolder: reportDriveFolder,
        importReady: Boolean(reportDriveFolder)
      } : null,
      initialState: initialState,
      dashboard: dashboard
    };
  });
}

function queryDashboard(request) {
  return _rpc_(function () {
    _requireUser_();
    return _dashboardPayload_(request);
  });
}

function getIssueDetail(request) {
  return _rpc_(function () {
    _requireUser_();
    const input = request || {};
    _assertExactFields_(input, ['scopeKey', 'issueUid'], 'issueDetail');
    const record = _activeSnapshotRecordForScope_(_text_(input.scopeKey), true);
    const row = _snapshotIssueDetail_(record, _text_(input.issueUid));
    _assert_(row, 'No existe la incidencia en el snapshot publicado.', 'NOT_FOUND');
    return row;
  });
}

function _readOnlySnapshotError_() {
  const error = new Error(
    'La WebApp GPC es una proyección de solo lectura. Las anotaciones se gestionan en la aplicación de escritorio.'
  );
  error.code = 'READ_ONLY_SNAPSHOT';
  throw error;
}

function saveNote() { return _rpc_(_readOnlySnapshotError_); }
function deleteNote() { return _rpc_(_readOnlySnapshotError_); }
function listNotes() { return _rpc_(_readOnlySnapshotError_); }
function deleteIssueNotes() { return _rpc_(_readOnlySnapshotError_); }

function _temporaryTransferFile_(blob, token, kind, ownerEmail, expiresAt) {
  const safeKind = _text_(kind);
  const resource = Drive.Files.create({
    name: '.radar-transfer-' + token + '-' + safeKind,
    appProperties: {
      radarArtifact: 'transfer-staging',
      radarTransferToken: token,
      radarTransferKind: safeKind,
      radarOwnerHash: _hash_(ownerEmail).slice(0, 32),
      radarExpiresAt: String(expiresAt)
    }
  }, blob, {
    fields: 'id,name,mimeType,size,trashed'
  });
  _assert_(resource && resource.id, 'No se pudo crear el staging temporal en Drive.',
    'TRANSFER_STAGING_FAILED');
  return _text_(resource.id);
}

function _stageDecodedTransfer_(decoded, token, user) {
  const expiresAt = Date.now() + RADAR.transferTtlSeconds * 1000;
  let projectionFileId = '';
  let reportFileId = '';
  try {
    projectionFileId = _temporaryTransferFile_(
      Utilities.newBlob(decoded.projectionText, 'application/json', 'projection.json'),
      token,
      'projection',
      user.email,
      expiresAt
    );
    reportFileId = _temporaryTransferFile_(
      decoded.reportBlob.setName(decoded.projection.report.fileName).setContentType(REPORT_PPTX_MIME),
      token,
      'report',
      user.email,
      expiresAt
    );
    return {
      owner: user.email,
      runId: _uuid_(),
      createdAt: Date.now(),
      expiresAt: expiresAt,
      fileName: decoded.fileName,
      fileSha256: decoded.fileSha256,
      fileSize: decoded.fileSize,
      manifestCreatedAt: decoded.createdAt,
      semanticContract: decoded.semanticContract,
      scope: decoded.scope,
      projectionFileId: projectionFileId,
      projectionSha256: decoded.projectionSha256,
      projectionBytes: decoded.projectionBytes,
      reportFileId: reportFileId,
      reportSha256: decoded.reportSha256,
      reportBytes: decoded.reportBytes,
      reportName: decoded.projection.report.fileName,
      reportSlideCount: decoded.projection.report.slideCount
    };
  } catch (err) {
    _trashDriveFileQuietly_(projectionFileId);
    _trashDriveFileQuietly_(reportFileId);
    if (err && err.code) throw err;
    const error = new Error('No se pudo conservar temporalmente el traslado verificado.');
    error.code = 'TRANSFER_STAGING_FAILED';
    throw error;
  }
}

function _transferMeta_(token, user) {
  const cleanToken = _text_(token);
  const meta = _safeJsonParse_(
    PropertiesService.getScriptProperties().getProperty('transfer:' + cleanToken),
    null
  );
  _assert_(meta && meta.owner === user.email,
    'La importación no existe o no te pertenece.', 'FORBIDDEN');
  if (!Number(meta.expiresAt) || Date.now() >= Number(meta.expiresAt)) {
    _discardTransfer_(cleanToken, meta);
    return Object.assign({}, meta, { expired: true });
  }
  return meta;
}

function _discardTransfer_(token, meta) {
  const record = meta || {};
  _trashDriveFileQuietly_(record.projectionFileId);
  _trashDriveFileQuietly_(record.reportFileId);
  PropertiesService.getScriptProperties().deleteProperty('transfer:' + _text_(token));
}

function _loadStagedDecodedTransfer_(meta) {
  let projectionBlob;
  let reportBlob;
  try {
    projectionBlob = DriveApp.getFileById(_text_(meta.projectionFileId)).getBlob();
    reportBlob = DriveApp.getFileById(_text_(meta.reportFileId)).getBlob();
  } catch (err) {
    const missing = new Error('El staging temporal ya no está disponible en Google Drive.');
    missing.code = 'UPLOAD_EXPIRED';
    throw missing;
  }
  const projectionBytes = projectionBlob.getBytes();
  const reportBytes = reportBlob.getBytes();
  _assert_(
    projectionBytes.length === Number(meta.projectionBytes) &&
    _sha256Bytes_(projectionBytes) === _text_(meta.projectionSha256),
    'La proyección temporal ha cambiado desde su validación.', 'TRANSFER_INVALID'
  );
  _assert_(
    reportBytes.length === Number(meta.reportBytes) &&
    _sha256Bytes_(reportBytes) === _text_(meta.reportSha256),
    'El PPTX temporal ha cambiado desde su validación.', 'TRANSFER_INVALID'
  );
  const projectionText = Utilities.newBlob(projectionBytes, 'application/json').getDataAsString('UTF-8');
  let projection;
  try {
    projection = JSON.parse(projectionText);
  } catch (err) {
    throw Object.assign(new Error('La proyección temporal ya no contiene JSON válido.'),
      { code: 'TRANSFER_INVALID' });
  }
  const manifest = {
    format: RADAR.transferFormat,
    version: RADAR.transferVersion,
    createdAt: meta.manifestCreatedAt,
    scope: meta.scope,
    semanticContract: meta.semanticContract,
    datasets: {
      projection: {
        path: TRANSFER_FILES.projection,
        sha256: meta.projectionSha256,
        bytes: Number(meta.projectionBytes),
        records: 1
      },
      report: {
        path: TRANSFER_FILES.report,
        sha256: meta.reportSha256,
        bytes: Number(meta.reportBytes),
        records: 1
      }
    }
  };
  const scope = _validateProjection_(projection, manifest, manifest.datasets.report);
  _validatePptxBlob_(reportBlob, manifest.datasets.report, reportBytes);
  return {
    fileName: meta.fileName,
    fileSha256: meta.fileSha256,
    fileSize: Number(meta.fileSize),
    createdAt: meta.manifestCreatedAt,
    dataVersion: scope.dataVersion,
    semanticContract: meta.semanticContract,
    scope: scope,
    scopeKey: scope.scopeKey,
    projection: projection,
    projectionText: projectionText,
    projectionSha256: _text_(meta.projectionSha256),
    projectionBytes: Number(meta.projectionBytes),
    reportBlob: reportBlob.setName(projection.report.fileName).setContentType(REPORT_PPTX_MIME),
    reportSha256: _text_(meta.reportSha256),
    reportBytes: Number(meta.reportBytes)
  };
}

function _markImportRun_(runId, patch) {
  const run = _readRecords_(RADAR.sheets.importRuns).find(function (row) {
    return _text_(row.run_id) === _text_(runId);
  });
  if (!run) return null;
  return _upsertRecord_(RADAR.sheets.importRuns, Object.assign({}, run, patch || {}));
}

function validateTransferImport(form) {
  return _rpc_(function () {
    const user = _requireAdmin_();
    _configuredReportDriveFolder_();
    _cleanupExpiredTransfers_();
    const decoded = _decodeTransferPackage_(form && form.transferFile);
    const preview = _transferPreview_(decoded);
    return _withApplicationLock_(function () {
      const token = _uuid_();
      let meta = null;
      try {
        meta = _stageDecodedTransfer_(decoded, token, user);
        PropertiesService.getScriptProperties().setProperty(
          'transfer:' + token,
          _safeJsonStringify_(meta)
        );
        _appendRecords_(RADAR.sheets.importRuns, [{
          run_id: meta.runId,
          file_name: decoded.fileName,
          file_sha256: decoded.fileSha256,
          status: 'validated',
          started_at: _nowIso_(),
          finished_at: '',
          new_records: preview.totalNewRecords,
          updated_records: preview.totalUpdatedRecords,
          unchanged_records: preview.totalUnchangedRecords,
          data_version: decoded.dataVersion,
          requested_by: user.email,
          details: 'Proyección canónica y PPTX exacto verificados; staging temporal en Drive.',
          snapshot_id: ''
        }]);
        return Object.assign({}, preview, {
          token: token,
          runId: meta.runId,
          checkedAt: _nowIso_(),
          expiresAt: new Date(meta.expiresAt).toISOString()
        });
      } catch (err) {
        if (meta) _discardTransfer_(token, meta);
        if (err && err.code) throw err;
        throw Object.assign(new Error('No se pudo conservar temporalmente el traslado.'),
          { code: 'TRANSFER_STAGING_FAILED' });
      }
    });
  });
}

function cancelTransferImport(token) {
  return _rpc_(function () {
    const user = _requireAdmin_();
    return _withApplicationLock_(function () {
      const meta = _transferMeta_(token, user);
      if (!meta.expired) _discardTransfer_(token, meta);
      _markImportRun_(meta.runId, {
        status: 'cancelled',
        finished_at: _nowIso_(),
        details: meta.expired
          ? 'Importación caducada; staging eliminado sin cambiar el snapshot activo.'
          : 'Importación cancelada; staging eliminado sin cambiar el snapshot activo.'
      });
      return { cancelled: true, expired: Boolean(meta.expired) };
    });
  });
}

function _snapshotRecordFromImport_(snapshotId, reportId, decoded, artifacts, parts, user, createdAt) {
  const scope = decoded.scope;
  return {
    snapshot_id: snapshotId,
    scope_key: scope.scopeKey,
    scope_label: scope.scopeLabel,
    country: scope.country,
    source_ids_json: _safeJsonStringify_(scope.sourceIds),
    data_version: scope.dataVersion,
    projection_contract: decoded.projection.schema,
    projection_version: decoded.projection.schemaVersion,
    projection_sha256: decoded.projectionSha256,
    projection_bytes: decoded.projectionBytes,
    part_count: parts.partCount,
    chunk_count: parts.chunkCount,
    facts_sha256: decoded.projection.factsSha256,
    reference_date: scope.referenceDate,
    report_name: artifacts.reportName,
    pptx_file_id: artifacts.pptxFileId,
    pptx_sha256: artifacts.pptxSha256,
    pptx_bytes: artifacts.pptxBytes,
    slides_file_id: artifacts.slidesFileId,
    slides_url: artifacts.slidesUrl,
    report_id: reportId,
    row_count: decoded.projection.views.issues.total,
    slide_count: artifacts.slideCount,
    created_at: createdAt,
    created_by: user.email
  };
}

function _reportAuditFromSnapshot_(record) {
  return {
    report_id: record.report_id,
    report_type: 'period',
    snapshot_id: record.snapshot_id,
    scope_key: record.scope_key,
    data_version: record.data_version,
    projection_sha256: record.projection_sha256,
    facts_sha256: record.facts_sha256,
    row_count: record.row_count,
    slide_count: record.slide_count,
    created_at: record.created_at,
    created_by: record.created_by,
    slides_file_id: record.slides_file_id,
    slides_url: record.slides_url,
    pptx_file_id: record.pptx_file_id,
    pptx_sha256: record.pptx_sha256
  };
}

function _publishDecodedTransfer_(decoded, meta, user) {
  const active = _activeSnapshotRecordForScope_(decoded.scopeKey, false);
  if (active && _text_(active.projection_sha256) === decoded.projectionSha256) {
    _markImportRun_(meta.runId, {
      status: 'completed',
      finished_at: _nowIso_(),
      new_records: 0,
      updated_records: 0,
      unchanged_records: 1,
      data_version: active.data_version,
      details: 'Importación idempotente: la misma proyección ya estaba activa.',
      snapshot_id: active.snapshot_id
    });
    return { record: active, idempotent: true };
  }

  const snapshotId = _uuid_();
  const reportId = _uuid_();
  const createdAt = _nowIso_();
  const folder = _configuredReportDriveFolder_();
  let artifacts = null;
  let snapshotAppended = false;
  let auditAppended = false;
  const priorDataVersion = _dataVersion_();
  let configChanged = false;
  try {
    artifacts = _importExactReportArtifacts_(decoded.reportBlob, decoded.projection, folder);
    const parts = _appendSnapshotParts_(snapshotId, decoded.projection, createdAt);
    const record = _snapshotRecordFromImport_(
      snapshotId, reportId, decoded, artifacts, parts, user, createdAt
    );
    _appendRecords_(RADAR.sheets.snapshots, [record]);
    snapshotAppended = true;
    _appendRecords_(RADAR.sheets.reportAudit, [_reportAuditFromSnapshot_(record)]);
    auditAppended = true;
    _setConfig_(
      'DATA_VERSION',
      decoded.dataVersion,
      'string',
      'Última versión de una proyección materializada publicada',
      user.email
    );
    configChanged = true;
    _markImportRun_(meta.runId, {
      status: 'completed',
      finished_at: _nowIso_(),
      new_records: active ? 0 : 1,
      updated_records: active ? 1 : 0,
      unchanged_records: 0,
      data_version: decoded.dataVersion,
      details: 'Snapshot materializado y PPTX exacto publicados de forma atómica.',
      snapshot_id: snapshotId
    });
    // The active pointer is intentionally the final durable write.
    _publishSnapshotPointer_(record, user);
    return { record: record, idempotent: false };
  } catch (err) {
    if (configChanged) {
      try {
        _setConfig_(
          'DATA_VERSION',
          priorDataVersion,
          'string',
          'Última versión de una proyección materializada publicada',
          user.email
        );
      } catch (configErr) {
        console.error('transfer_config_rollback_failed', { snapshotId: snapshotId });
      }
    }
    if (auditAppended) _deleteRecord_(RADAR.sheets.reportAudit, reportId);
    if (snapshotAppended) _deleteRecord_(RADAR.sheets.snapshots, snapshotId);
    _deleteSnapshotChunkRows_([snapshotId]);
    _deleteSnapshotPartRows_([snapshotId]);
    if (artifacts) {
      _trashDriveFileQuietly_(artifacts.pptxFileId);
      _trashDriveFileQuietly_(artifacts.slidesFileId);
    }
    throw err;
  }
}

function commitTransferImport(token) {
  return _rpc_(function () {
    const user = _requireAdmin_();
    let meta = null;
    let published = null;
    try {
      published = _withApplicationLock_(function () {
        meta = _transferMeta_(token, user);
        _assert_(!meta.expired,
          'La importación ha caducado; selecciona de nuevo el fichero.', 'UPLOAD_EXPIRED');
        const decoded = _loadStagedDecodedTransfer_(meta);
        return _publishDecodedTransfer_(decoded, meta, user);
      });
      if (!published.idempotent) _invalidateCaches_();
      const cache = { warmed: [], failed: [] };
      let garbageCollection = { removedSnapshots: 0, removedChunks: 0, removedParts: 0 };
      try {
        garbageCollection = _garbageCollectSnapshots_(published.record.scope_key);
      } catch (gcErr) {
        console.warn('snapshot_gc_failed', {
          scopeKey: published.record.scope_key,
          code: gcErr && gcErr.code
        });
      }
      return {
        operation: 'import',
        summary: published.idempotent
          ? 'La proyección ya estaba publicada; no se duplicaron datos ni artefactos.'
          : 'Snapshot publicado y presentación nativa de Google Slides creada desde el PPTX autoritativo.',
        completedAt: _nowIso_(),
        snapshotId: published.record.snapshot_id,
        scopeKey: published.record.scope_key,
        dataVersion: published.record.data_version,
        projectionSha256: published.record.projection_sha256,
        reportId: published.record.report_id,
        slidesUrl: published.record.slides_url,
        pptxSha256: published.record.pptx_sha256,
        idempotent: published.idempotent,
        cache: cache,
        garbageCollection: garbageCollection
      };
    } catch (err) {
      if (meta) {
        try {
          _markImportRun_(meta.runId, {
            status: 'failed',
            finished_at: _nowIso_(),
            details: 'La importación falló; el puntero anterior permanece activo.'
          });
        } catch (auditErr) {
          console.error('transfer_audit_failed', { runId: meta.runId });
        }
      }
      throw err;
    } finally {
      if (meta) _discardTransfer_(token, meta);
    }
  });
}

function listImportRuns() {
  return _rpc_(function () {
    _requireAdmin_();
    return _readRecords_(RADAR.sheets.importRuns).sort(function (left, right) {
      return (_date_(right.started_at) || 0) - (_date_(left.started_at) || 0);
    }).slice(0, 50);
  });
}
