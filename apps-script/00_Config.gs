/** Configuration and immutable contracts. No secrets belong in this file. */
const RADAR = Object.freeze({
  appName: 'Bug Resolution Radar',
  contractVersion: '4.0.0',
  projectionContract: 'bug-resolution-radar-cloud-projection',
  projectionVersion: 1,
  semanticContract: 'desktop-authoritative-v1',
  spreadsheetId: '10_kDe-giOQtJxBX_M67z8In17MIh-6IQpmQl_9eo7c8',
  initialAdmin: 'felix.delbarrio@bbva.com',
  allowedDomain: 'bbva.com',
  newsletterFrom: 'bug-resolution-radar.group@bbva.com',
  geminiModel: 'gemini-3.6-flash',
  maxPageSize: 250,
  defaultPageSize: 50,
  cacheSeconds: 21600,
  transferTtlSeconds: 1800,
  shareTtlSeconds: 90 * 24 * 60 * 60,
  maxTransferBytes: 32 * 1024 * 1024,
  maxTransferExpandedBytes: 80 * 1024 * 1024,
  maxProjectionBytes: 24 * 1024 * 1024,
  maxReportBytes: 20 * 1024 * 1024,
  snapshotChunkSize: 40000,
  transferFormat: 'bug-resolution-radar-transfer',
  transferVersion: 2,
  sheets: Object.freeze({
    config: '_CONFIG',
    users: 'AUTH_USERS',
    importRuns: 'IMPORT_RUNS',
    preferences: 'USER_PREFS',
    snapshots: 'MATERIALIZED_SNAPSHOTS',
    snapshotParts: 'MATERIALIZED_PARTS',
    snapshotChunks: 'MATERIALIZED_CHUNKS',
    snapshotPointers: 'MATERIALIZED_POINTERS',
    reportAudit: 'REPORT_AUDIT',
    reportShares: 'REPORT_SHARES',
    newsletterRecipients: 'NEWSLETTER_RECIPIENTS',
    newsletterAudit: 'NEWSLETTER_AUDIT'
  })
});

const DESIGN_TOKENS = Object.freeze({
  color: Object.freeze({
    midnight: '#070E46',
    electric: '#001391',
    royalDark: '#2165CA',
    royal: '#0C6DFF',
    sereneDark: '#53A9EF',
    serene: '#85C8FF',
    blueLight: '#D6E9F8',
    black: '#000519',
    grey900: '#11192D',
    grey800: '#222C42',
    grey700: '#334056',
    grey600: '#46536D',
    grey500: '#ADB8C2',
    grey400: '#CAD1D8',
    grey300: '#E2E6EA',
    grey200: '#F7F8F8',
    reportComment: '#F6F9FF',
    white: '#FFFFFF',
    success: '#15803D',
    successSoft: '#EBFFF0',
    warning: '#D97706',
    warningStrong: '#906401',
    warningSoft: '#FFF5E5',
    danger: '#B4232A',
    dangerSoft: '#FFE9E5',
    statusIntake: '#E85D63',
    statusProgress: '#F59E0B',
    statusAccepted: '#4CAF50',
    statusDeployed: '#5B3FD0',
    statusOpen: '#FBBF24',
    priorityHigh: '#D64550',
    priorityLow: '#22A447',
    neutral: '#E2E6EE'
  }),
  dark: Object.freeze({
    midnight: '#F7F8F8',
    electric: '#85C8FF',
    black: '#FFFFFF',
    grey900: '#F7F8F8',
    grey800: '#E2E6EA',
    grey700: '#CAD1D8',
    grey600: '#ADB8C2',
    grey500: '#46536D',
    grey400: '#334056',
    grey300: '#222C42',
    grey200: '#11192D',
    white: '#000519',
    primaryStrong: '#D6E9F8',
    success: '#9CE67E',
    successSoft: '#14331D',
    warning: '#FFC553',
    warningSoft: '#382B12',
    danger: '#FF8585',
    dangerSoft: '#3D191B'
  }),
  font: Object.freeze({
    webBody: '"BentonSans", Arial, sans-serif',
    webHeadline: '"Tiempos", Georgia, serif'
  }),
  effect: Object.freeze({
    emailShadow: 'rgba(7,14,70,.10)'
  })
});

const CONTRACTS = Object.freeze({
  _CONFIG: Object.freeze({
    key: 'key', version: '4.0.0', unique: ['key'],
    columns: Object.freeze([
      ['key', 'string', true], ['value', 'string', false], ['kind', 'enum', true, ['string', 'number', 'boolean', 'json']],
      ['description', 'string', false], ['updated_at', 'datetime', true], ['updated_by', 'email', true]
    ])
  }),
  AUTH_USERS: Object.freeze({
    key: 'email', version: '4.0.0', unique: ['email'],
    columns: Object.freeze([
      ['email', 'email', true], ['role', 'enum', true, ['admin', 'viewer']], ['active', 'boolean', true],
      ['display_name', 'string', false], ['updated_at', 'datetime', true], ['updated_by', 'email', true]
    ])
  }),
  IMPORT_RUNS: Object.freeze({
    key: 'run_id', version: '4.0.0', unique: ['run_id'],
    columns: Object.freeze([
      ['run_id', 'string', true], ['file_name', 'string', true], ['file_sha256', 'string', true],
      ['status', 'enum', true, ['validated', 'completed', 'failed', 'cancelled']],
      ['started_at', 'datetime', true], ['finished_at', 'datetime', false], ['new_records', 'number', true],
      ['updated_records', 'number', true], ['unchanged_records', 'number', true], ['data_version', 'string', false],
      ['requested_by', 'email', true], ['details', 'string', false], ['snapshot_id', 'string', false]
    ])
  }),
  USER_PREFS: Object.freeze({
    key: 'pref_uid', version: '4.0.0', unique: ['pref_uid'],
    columns: Object.freeze([
      ['pref_uid', 'string', true], ['email', 'email', true], ['preference_key', 'string', true],
      ['value_json', 'json', true], ['updated_at', 'datetime', true]
    ])
  }),
  MATERIALIZED_SNAPSHOTS: Object.freeze({
    key: 'snapshot_id', version: '4.0.0', unique: ['snapshot_id'],
    columns: Object.freeze([
      ['snapshot_id', 'string', true], ['scope_key', 'string', true], ['scope_label', 'string', true],
      ['country', 'string', true], ['source_ids_json', 'json', true], ['data_version', 'string', true],
      ['projection_contract', 'string', true], ['projection_version', 'number', true],
      ['projection_sha256', 'string', true], ['projection_bytes', 'number', true],
      ['part_count', 'number', true], ['chunk_count', 'number', true],
      ['facts_sha256', 'string', true], ['reference_date', 'datetime', false],
      ['report_name', 'string', true], ['pptx_file_id', 'string', true], ['pptx_sha256', 'string', true],
      ['pptx_bytes', 'number', true], ['slides_file_id', 'string', true], ['slides_url', 'url', true],
      ['report_id', 'string', true], ['row_count', 'number', true], ['slide_count', 'number', true],
      ['created_at', 'datetime', true], ['created_by', 'email', true]
    ])
  }),
  MATERIALIZED_PARTS: Object.freeze({
    key: 'part_uid', version: '4.0.0', unique: ['part_uid'],
    columns: Object.freeze([
      ['part_uid', 'string', true], ['snapshot_id', 'string', true],
      ['part_key', 'string', true], ['part_sha256', 'string', true],
      ['part_bytes', 'number', true], ['chunk_count', 'number', true],
      ['created_at', 'datetime', true]
    ])
  }),
  MATERIALIZED_CHUNKS: Object.freeze({
    key: 'chunk_uid', version: '4.0.0', unique: ['chunk_uid'],
    columns: Object.freeze([
      ['chunk_uid', 'string', true], ['snapshot_id', 'string', true], ['part_uid', 'string', true],
      ['part_key', 'string', true], ['chunk_index', 'number', true],
      ['content_json', 'string', true], ['chunk_sha256', 'string', true], ['created_at', 'datetime', true]
    ])
  }),
  MATERIALIZED_POINTERS: Object.freeze({
    key: 'scope_key', version: '4.0.0', unique: ['scope_key'],
    columns: Object.freeze([
      ['scope_key', 'string', true], ['snapshot_id', 'string', true], ['data_version', 'string', true],
      ['activated_at', 'datetime', true], ['activated_by', 'email', true]
    ])
  }),
  REPORT_AUDIT: Object.freeze({
    key: 'report_id', version: '4.0.0', unique: ['report_id'],
    columns: Object.freeze([
      ['report_id', 'string', true], ['report_type', 'enum', true, ['period']],
      ['snapshot_id', 'string', true], ['scope_key', 'string', true], ['data_version', 'string', true],
      ['projection_sha256', 'string', true], ['facts_sha256', 'string', true],
      ['row_count', 'number', true], ['slide_count', 'number', true],
      ['created_at', 'datetime', true], ['created_by', 'email', true],
      ['slides_file_id', 'string', true], ['slides_url', 'url', true],
      ['pptx_file_id', 'string', true], ['pptx_sha256', 'string', true]
    ])
  }),
  REPORT_SHARES: Object.freeze({
    key: 'share_id', version: '4.0.0', unique: ['share_id'],
    columns: Object.freeze([
      ['share_id', 'string', true], ['token_sha256', 'string', true], ['report_id', 'string', true],
      ['snapshot_id', 'string', true], ['scope_key', 'string', true], ['scope_label', 'string', true],
      ['projection_sha256', 'string', true], ['data_version', 'string', true], ['active', 'boolean', true],
      ['created_at', 'datetime', true], ['expires_at', 'datetime', true], ['created_by', 'email', true]
    ])
  }),
  NEWSLETTER_RECIPIENTS: Object.freeze({
    key: 'recipient_uid', version: '4.0.0', unique: ['recipient_uid'],
    columns: Object.freeze([
      ['recipient_uid', 'string', true], ['scope_key', 'string', true], ['scope_label', 'string', true],
      ['email', 'email', true], ['display_name', 'string', false], ['active', 'boolean', true],
      ['created_at', 'datetime', true], ['created_by', 'email', true],
      ['updated_at', 'datetime', true], ['updated_by', 'email', true]
    ])
  }),
  NEWSLETTER_AUDIT: Object.freeze({
    key: 'newsletter_id', version: '4.0.0', unique: ['newsletter_id'],
    columns: Object.freeze([
      ['newsletter_id', 'string', true], ['report_id', 'string', true],
      ['mode', 'enum', true, ['test', 'send']], ['scope_key', 'string', true],
      ['data_version', 'string', true], ['recipients_json', 'json', true],
      ['subject', 'string', true], ['facts_sha256', 'string', true], ['gemini_model', 'string', true],
      ['created_at', 'datetime', true], ['created_by', 'email', true],
      ['status', 'enum', true, ['processing', 'sent', 'failed']], ['details', 'string', false]
    ])
  })
});
