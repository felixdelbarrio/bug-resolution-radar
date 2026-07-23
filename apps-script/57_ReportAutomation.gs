/** Read-only status of the exact report imported with the active snapshot. */

function _periodNewsletterWasSent_(reportId) {
  const id = _text_(reportId);
  return Boolean(id) && _readRecords_(RADAR.sheets.newsletterAudit).some(function (row) {
    return _text_(row.report_id) === id &&
      _text_(row.mode) === 'send' &&
      _text_(row.status) === 'sent';
  });
}

function getPeriodReportStatus(scopeKey) {
  return _rpc_(function () {
    const user = _requireAdmin_();
    const key = _text_(scopeKey);
    _assert_(key, 'Selecciona un ámbito materializado.', 'SNAPSHOT_NOT_FOUND');
    const record = _activeSnapshotRecordForScope_(key, true);
    _snapshotHeader_(record);
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
        newsletterSent: _periodNewsletterWasSent_(record.report_id),
        projectionSha256: _text_(record.projection_sha256),
        pptxSha256: _text_(record.pptx_sha256)
      },
      folder: (_preferenceMap_(user.email) || {}).report_drive_folder || null
    };
  });
}
