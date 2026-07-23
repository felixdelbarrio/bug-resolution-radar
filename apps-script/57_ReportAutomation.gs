/** Read-only status of the exact report imported with the active snapshot. */

function _periodNewsletterState_(reportId, adminEmail) {
  const id = _text_(reportId);
  const admin = _canonicalEmail_(adminEmail);
  const audits = id ? _readRecords_(RADAR.sheets.newsletterAudit).filter(function (row) {
    return _text_(row.report_id) === id && _text_(row.status) === 'sent';
  }) : [];
  return {
    testSent: audits.some(function (row) {
      return _text_(row.mode) === 'test' && _canonicalEmail_(row.created_by) === admin;
    }),
    newsletterSent: audits.some(function (row) {
      return _text_(row.mode) === 'send';
    })
  };
}

function getPeriodReportStatus(scopeKey) {
  return _rpc_(function () {
    const user = _requireAdmin_();
    const key = _text_(scopeKey);
    _assert_(key, 'Selecciona un ámbito materializado.', 'SNAPSHOT_NOT_FOUND');
    const record = _activeSnapshotRecordForScope_(key, true);
    _snapshotHeader_(record);
    const newsletter = _periodNewsletterState_(record.report_id, user.email);
    return {
      scopeKey: key,
      job: {
        jobId: '',
        scopeKey: key,
        country: _text_(record.country),
        sourceIds: _safeJsonParse_(record.source_ids_json, []) || [],
        dataVersion: _text_(record.data_version),
        status: 'completed',
        createdAt: record.created_at,
        startedAt: record.created_at,
        finishedAt: record.created_at,
        reportId: _text_(record.report_id),
        fileUrl: _text_(record.slides_url),
        rowCount: Number(record.row_count),
        slideCount: Number(record.slide_count),
        details: 'PPTX exacto importado desde escritorio y convertido a Google Slides.',
        newsletterTested: newsletter.testSent,
        newsletterSent: newsletter.newsletterSent,
        recipientCount: _newsletterRecipientsForReport_(record.report_id).length,
        projectionSha256: _text_(record.projection_sha256),
        pptxSha256: _text_(record.pptx_sha256)
      },
      folder: _reportDriveFolderSetting_()
    };
  });
}
