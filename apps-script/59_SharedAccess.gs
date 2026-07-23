/** Domain-authenticated bearer links pinned to one immutable snapshot. */
function _requireDomainViewer_() {
  const email = _activeEmail_();
  _assert_(email, 'Debes abrir el enlace con tu cuenta corporativa.', 'AUTH_REQUIRED');
  _assert_(email.endsWith('@' + RADAR.allowedDomain),
    'La cuenta no pertenece al dominio autorizado.', 'FORBIDDEN');
  return {
    email: email,
    role: 'shared',
    displayName: email.split('@')[0],
    shared: true
  };
}

function _applicationBaseUrl_() {
  const configured = _text_(
    PropertiesService.getScriptProperties().getProperty('RADAR_APP_URL')
  );
  const resolved = configured || _text_(ScriptApp.getService().getUrl());
  _assert_(resolved && /^https:\/\//i.test(resolved),
    'No se ha podido resolver la URL HTTPS de la aplicación desplegada.',
    'APP_URL_INVALID');
  return _sanitizeUrl_(resolved).replace(/[?#].*$/, '').replace(/\/+$/, '');
}

function _reportShareToken_() {
  const seed = _uuid_() + ':' + _uuid_() + ':' + Date.now();
  return Utilities.base64EncodeWebSafe(
    Utilities.computeDigest(
      Utilities.DigestAlgorithm.SHA_256,
      seed,
      Utilities.Charset.UTF_8
    )
  ).replace(/=+$/, '');
}

function _createReportShare_(context, user) {
  const record = context && (context.record || context.snapshot);
  _assert_(record && record.snapshot_id,
    'No se puede compartir una newsletter sin snapshot.', 'SNAPSHOT_NOT_FOUND');
  const token = _reportShareToken_();
  const shareId = _uuid_();
  const createdAt = new Date();
  const expiresAt = new Date(createdAt.getTime() + RADAR.shareTtlSeconds * 1000);
  _appendRecords_(RADAR.sheets.reportShares, [{
    share_id: shareId,
    token_sha256: _hash_(token),
    report_id: _text_(record.report_id),
    snapshot_id: _text_(record.snapshot_id),
    scope_key: _text_(record.scope_key),
    scope_label: _text_(record.scope_label),
    projection_sha256: _text_(record.projection_sha256),
    data_version: _text_(record.data_version),
    active: true,
    created_at: createdAt,
    expires_at: expiresAt,
    created_by: user.email
  }]);
  return {
    shareId: shareId,
    expiresAt: expiresAt.toISOString(),
    url: _applicationBaseUrl_() + '?share=' + encodeURIComponent(token)
  };
}

function _deactivateReportShare_(shareId) {
  const row = _readRecords_(RADAR.sheets.reportShares).find(function (item) {
    return _text_(item.share_id) === _text_(shareId);
  });
  if (row) {
    _upsertRecord_(
      RADAR.sheets.reportShares,
      Object.assign({}, row, { active: false })
    );
  }
}

function _sharedReportContext_(rawToken) {
  const token = _text_(rawToken);
  _assert_(/^[A-Za-z0-9_-]{40,120}$/.test(token),
    'El enlace compartido no es válido.', 'SHARE_INVALID');
  const share = _readRecords_(RADAR.sheets.reportShares).find(function (row) {
    return row.active === true && _text_(row.token_sha256) === _hash_(token);
  });
  _assert_(share, 'Este enlace compartido no existe o ya no está activo.', 'SHARE_INVALID');
  const expiresAt = _date_(share.expires_at);
  _assert_(expiresAt && expiresAt.getTime() > Date.now(),
    'Este enlace compartido ha caducado.', 'SHARE_INVALID');
  const user = _requireDomainViewer_();
  const record = _snapshotRecordById_(share.snapshot_id, true);
  _assert_(
    _text_(record.scope_key) === _text_(share.scope_key) &&
    _text_(record.report_id) === _text_(share.report_id) &&
    _text_(record.projection_sha256) === _text_(share.projection_sha256) &&
    _text_(record.data_version) === _text_(share.data_version),
    'El enlace no coincide con el snapshot publicado.', 'SHARE_INVALID'
  );
  const report = _readRecords_(RADAR.sheets.reportAudit).find(function (row) {
    return _text_(row.report_id) === _text_(share.report_id);
  });
  _assert_(
    report &&
    _text_(report.snapshot_id) === _text_(record.snapshot_id) &&
    _text_(report.projection_sha256) === _text_(record.projection_sha256),
    'La presentación asociada al enlace ya no es verificable.', 'SHARE_INVALID'
  );
  _snapshotHeader_(record);
  return {
    share: share,
    record: record,
    report: report,
    user: Object.assign({}, user, {
      scopeLabel: _text_(share.scope_label)
    })
  };
}

function _sharedDashboardRequest_(context, request) {
  return _normalizeMaterializedRequest_(
    request || { view: 'overview' },
    context.record.scope_key
  );
}

function getSharedBootstrap(token) {
  return _rpc_(function () {
    const context = _sharedReportContext_(token);
    const header = _snapshotHeader_(context.record);
    const scope = header.scope;
    const initialState = {
      panel: 'overview',
      scopeKey: scope.scopeKey,
      trendChart: 'open_status_bar',
      insightsId: 'summary',
      issuesView: 'Cards',
      page: 1,
      pageSize: RADAR.defaultPageSize
    };
    return {
      app: {
        name: RADAR.appName,
        contractVersion: RADAR.contractVersion,
        semanticContract: RADAR.semanticContract,
        dataVersion: scope.dataVersion,
        cacheEpoch: _cacheEpoch_(),
        maxTransferBytes: 0,
        scopeVersions: (function () {
          const versions = {};
          versions[scope.scopeKey] = scope.dataVersion;
          return versions;
        })(),
        shared: true,
        scopeLabel: scope.scopeLabel,
        materializedOnly: true,
        issueFiltersEnabled: false
      },
      user: context.user,
      scopes: [{
        scopeKey: scope.scopeKey,
        scopeLabel: scope.scopeLabel,
        country: scope.country,
        sourceIds: scope.sourceIds,
        dataVersion: scope.dataVersion,
        snapshotId: context.record.snapshot_id,
        activatedAt: context.share.created_at
      }],
      countries: [scope.country],
      sources: scope.sourceIds.map(function (sourceId) {
        return {
          source_id: sourceId,
          source_type: 'materialized',
          alias: sourceId,
          country: scope.country
        };
      }),
      preferences: { theme: 'light' },
      initialState: initialState,
      dashboard: _dashboardPayloadFromSnapshot_(
        context.record.snapshot_id,
        {
          view: 'overview',
          page: 1,
          pageSize: RADAR.defaultPageSize,
          sortId: 'default'
        },
        scope.scopeKey
      )
    };
  });
}

function querySharedDashboard(token, request) {
  return _rpc_(function () {
    const context = _sharedReportContext_(token);
    const input = _sharedDashboardRequest_(context, request);
    return _materializedViewPayload_(context.record, input);
  });
}

function getSharedIssueDetail(token, issueUid) {
  return _rpc_(function () {
    const context = _sharedReportContext_(token);
    const row = _snapshotIssueDetail_(context.record, _text_(issueUid));
    _assert_(row, 'No existe la incidencia en este snapshot.', 'NOT_FOUND');
    return row;
  });
}
