/** Configuration and immutable contracts. No secrets belong in this file. */
const RADAR = Object.freeze({
  appName: 'Bug Resolution Radar',
  corporateBrand: 'BBVA Banca de Empresas e Instituciones',
  appVersion: '2026.08.19.11',
  contractVersion: '5.1.0',
  projectionContract: 'bug-resolution-radar-cloud-projection',
  projectionVersion: 2,
  semanticContract: 'desktop-authoritative-v2',
  spreadsheetId: '10_kDe-giOQtJxBX_M67z8In17MIh-6IQpmQl_9eo7c8',
  initialAdmin: 'felix.delbarrio@bbva.com',
  allowedDomain: 'bbva.com',
  newsletterFrom: 'bug-resolution-radar.group@bbva.com',
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
  transferVersion: 3,
  sheets: Object.freeze({
    config: '_CONFIG',
    users: 'AUTH_USERS',
    importRuns: 'IMPORT_RUNS',
    snapshots: 'MATERIALIZED_SNAPSHOTS',
    snapshotParts: 'MATERIALIZED_PARTS',
    snapshotChunks: 'MATERIALIZED_CHUNKS',
    snapshotPointers: 'MATERIALIZED_POINTERS',
    reportAudit: 'REPORT_AUDIT',
    reportShares: 'REPORT_SHARES',
    newsletterRecipients: 'NEWSLETTER_RECIPIENTS',
    newsletterAudit: 'NEWSLETTER_AUDIT',
    analyticsEvents: 'ANALYTICS_EVENTS'
  })
});

const DESIGN_TOKENS = (function () {
  const color = Object.freeze({
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
  });
  const dark = Object.freeze({
    midnight: '#FFFFFF',
    electric: '#85C8FF',
    black: '#FFFFFF',
    grey900: '#F7F8F8',
    grey800: '#F7F8F8',
    grey700: '#F7F8F8',
    grey600: '#CAD1D8',
    grey500: '#46536D',
    grey400: '#334056',
    grey300: '#222C42',
    grey200: '#11192D',
    blueLight: '#222C42',
    white: '#070E46',
    primaryStrong: '#F7F8F8',
    success: '#9CE67E',
    successSoft: '#334056',
    warning: '#FFC553',
    warningStrong: '#FFC553',
    warningSoft: '#334056',
    danger: '#FF5252',
    dangerSoft: '#334056'
  });
  const font = Object.freeze({
    webBody: '"BentonSans", Arial, sans-serif',
    webHeadline: '"Tiempos", Georgia, serif'
  });
  const radius = Object.freeze({
    container: '16px',
    component: '8px'
  });
  const effect = Object.freeze({
    transparent: 'rgba(0,0,0,0)',
    shadow: '0 8px 24px rgba(7,14,70,.08)',
    shadowSoft: '0 3px 12px rgba(7,14,70,.06)',
    shadowPanel: '0 8px 24px rgba(7,14,70,.10)',
    shadowGate: '0 24px 72px rgba(0,5,25,.35)',
    shadowDrawer: '-16px 0 48px rgba(0,5,25,.24)',
    darkShadow: '0 8px 24px rgba(0,0,0,.28)',
    darkShadowSoft: '0 3px 12px rgba(0,0,0,.20)',
    glowGate: 'rgba(133,200,255,.24)',
    glowHero: 'rgba(133,200,255,.46)',
    borderInverseSoft: 'rgba(255,255,255,.32)',
    overlay: 'rgba(0,5,25,.58)',
    emailShadow: '0 8px 24px rgba(7,14,70,.10)'
  });

  function kebab_(value) {
    return String(value)
      .replace(/([a-z0-9])([A-Z])/g, '$1-$2')
      .replace(/([A-Za-z])([0-9])/g, '$1-$2')
      .toLowerCase();
  }

  function colorVariables_(palette) {
    const variables = {};
    Object.keys(palette).forEach(function (key) {
      variables['--bbva-' + kebab_(key)] = palette[key];
    });
    return variables;
  }

  const light = colorVariables_(color);
  Object.assign(light, {
    '--signal-status-intake': 'var(--bbva-status-intake)',
    '--signal-status-progress': 'var(--bbva-status-progress)',
    '--signal-status-accepted': 'var(--bbva-status-accepted)',
    '--signal-status-deployed': 'var(--bbva-status-deployed)',
    '--signal-status-closed': 'var(--bbva-success)',
    '--signal-status-open': 'var(--bbva-status-open)',
    '--signal-priority-highest': 'var(--bbva-danger)',
    '--signal-priority-high': 'var(--bbva-priority-high)',
    '--signal-priority-medium': 'var(--bbva-status-progress)',
    '--signal-priority-low': 'var(--bbva-priority-low)',
    '--signal-priority-lowest': 'var(--bbva-success)',
    '--signal-neutral': 'var(--bbva-neutral)',
    '--chart-series-1': 'var(--bbva-electric)',
    '--chart-series-2': 'var(--bbva-royal-dark)',
    '--chart-series-3': 'var(--bbva-royal)',
    '--chart-series-4': 'var(--bbva-serene-dark)',
    '--chart-series-5': 'var(--bbva-serene)',
    '--chart-series-6': 'var(--bbva-success)',
    '--chart-series-7': 'var(--bbva-warning)',
    '--chart-transparent': effect.transparent,
    '--bbva-primary': 'var(--bbva-electric)',
    '--bbva-primary-strong': 'var(--bbva-midnight)',
    '--bbva-surface': 'var(--bbva-white)',
    '--bbva-surface-2': 'var(--bbva-grey-200)',
    '--bbva-surface-elevated': 'var(--bbva-white)',
    '--bbva-border': 'var(--bbva-grey-300)',
    '--bbva-border-strong': 'var(--bbva-grey-400)',
    '--bbva-text': 'var(--bbva-midnight)',
    '--bbva-text-muted': 'var(--bbva-grey-600)',
    '--bbva-on-primary': 'var(--bbva-white)',
    '--bbva-accent-bg': 'var(--bbva-blue-light)',
    '--bbva-action-bg': 'var(--bbva-white)',
    '--bbva-action-border': 'var(--bbva-grey-400)',
    '--bbva-tab-soft-text': 'var(--bbva-grey-600)',
    '--bbva-tab-active-bg': 'var(--bbva-electric)',
    '--bbva-tab-active-text': 'var(--bbva-white)',
    '--bbva-tab-active-border': 'var(--bbva-electric)',
    '--bbva-inverse-surface': 'var(--bbva-midnight)',
    '--bbva-on-inverse': 'var(--bbva-white)',
    '--bbva-brand-midnight': color.midnight,
    '--bbva-brand-electric': color.electric,
    '--bbva-brand-royal-dark': color.royalDark,
    '--bbva-brand-on-hero': color.white,
    '--bbva-brand-on-hero-muted': color.blueLight,
    '--bbva-shadow': effect.shadow,
    '--bbva-shadow-soft': effect.shadowSoft,
    '--bbva-shadow-panel': effect.shadowPanel,
    '--bbva-shadow-gate': effect.shadowGate,
    '--bbva-shadow-drawer': effect.shadowDrawer,
    '--bbva-glow-gate': effect.glowGate,
    '--bbva-glow-hero': effect.glowHero,
    '--bbva-border-inverse-soft': effect.borderInverseSoft,
    '--bbva-overlay': effect.overlay,
    '--bbva-radius-container': radius.container,
    '--bbva-radius-component': radius.component,
    '--bbva-radius-xl': 'var(--bbva-radius-container)',
    '--bbva-radius-lg': 'var(--bbva-radius-container)',
    '--bbva-radius-md': 'var(--bbva-radius-component)',
    '--bbva-radius-sm': 'var(--bbva-radius-component)',
    '--bbva-font-sans': font.webBody,
    '--bbva-font-headline': font.webHeadline
  });

  const darkWeb = colorVariables_(dark);
  Object.assign(darkWeb, {
    '--bbva-primary': 'var(--bbva-electric)',
    '--bbva-primary-strong': dark.primaryStrong,
    '--bbva-surface': 'var(--bbva-grey-200)',
    '--bbva-surface-2': color.black,
    '--bbva-surface-elevated': 'var(--bbva-grey-300)',
    '--bbva-border': 'var(--bbva-grey-500)',
    '--bbva-border-strong': 'var(--bbva-grey-500)',
    '--bbva-text': 'var(--bbva-midnight)',
    '--bbva-text-muted': 'var(--bbva-grey-700)',
    '--bbva-on-primary': color.midnight,
    '--bbva-accent-bg': 'var(--bbva-grey-400)',
    '--bbva-action-bg': 'var(--bbva-grey-200)',
    '--bbva-action-border': 'var(--bbva-grey-500)',
    '--bbva-tab-soft-text': 'var(--bbva-grey-700)',
    '--bbva-tab-active-bg': 'var(--bbva-electric)',
    '--bbva-tab-active-text': color.midnight,
    '--bbva-tab-active-border': 'var(--bbva-electric)',
    '--bbva-inverse-surface': 'var(--bbva-grey-400)',
    '--bbva-on-inverse': color.white,
    '--bbva-shadow': effect.darkShadow,
    '--bbva-shadow-soft': effect.darkShadowSoft
  });

  return Object.freeze({
    color: color,
    dark: dark,
    font: font,
    radius: radius,
    effect: effect,
    web: Object.freeze({
      light: Object.freeze(light),
      dark: Object.freeze(darkWeb)
    })
  });
})();

const CONTRACTS = Object.freeze({
  _CONFIG: Object.freeze({
    key: 'key', version: '5.0.0', unique: ['key'],
    columns: Object.freeze([
      ['key', 'string', true], ['value', 'string', false], ['kind', 'enum', true, ['string', 'number', 'boolean', 'json']],
      ['description', 'string', false], ['updated_at', 'datetime', true], ['updated_by', 'email', true]
    ])
  }),
  AUTH_USERS: Object.freeze({
    key: 'email', version: '5.0.0', unique: ['email'],
    columns: Object.freeze([
      ['email', 'email', true], ['role', 'enum', true, ['admin', 'viewer']], ['active', 'boolean', true],
      ['display_name', 'string', false], ['updated_at', 'datetime', true], ['updated_by', 'email', true]
    ])
  }),
  IMPORT_RUNS: Object.freeze({
    key: 'run_id', version: '5.0.0', unique: ['run_id'],
    columns: Object.freeze([
      ['run_id', 'string', true], ['file_name', 'string', true], ['file_sha256', 'string', true],
      ['status', 'enum', true, ['validated', 'completed', 'failed', 'cancelled']],
      ['started_at', 'datetime', true], ['finished_at', 'datetime', false], ['new_records', 'number', true],
      ['updated_records', 'number', true], ['unchanged_records', 'number', true], ['data_version', 'string', false],
      ['requested_by', 'email', true], ['details', 'string', false], ['snapshot_id', 'string', false]
    ])
  }),
  MATERIALIZED_SNAPSHOTS: Object.freeze({
    key: 'snapshot_id', version: '5.0.0', unique: ['snapshot_id'],
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
    key: 'part_uid', version: '5.0.0', unique: ['part_uid'],
    columns: Object.freeze([
      ['part_uid', 'string', true], ['snapshot_id', 'string', true],
      ['part_key', 'string', true], ['part_sha256', 'string', true],
      ['part_bytes', 'number', true], ['chunk_count', 'number', true],
      ['created_at', 'datetime', true]
    ])
  }),
  MATERIALIZED_CHUNKS: Object.freeze({
    key: 'chunk_uid', version: '5.0.0', unique: ['chunk_uid'],
    columns: Object.freeze([
      ['chunk_uid', 'string', true], ['snapshot_id', 'string', true], ['part_uid', 'string', true],
      ['part_key', 'string', true], ['chunk_index', 'number', true],
      ['content_json', 'string', true], ['chunk_sha256', 'string', true], ['created_at', 'datetime', true]
    ])
  }),
  MATERIALIZED_POINTERS: Object.freeze({
    key: 'scope_key', version: '5.0.0', unique: ['scope_key'],
    columns: Object.freeze([
      ['scope_key', 'string', true], ['snapshot_id', 'string', true], ['data_version', 'string', true],
      ['activated_at', 'datetime', true], ['activated_by', 'email', true]
    ])
  }),
  REPORT_AUDIT: Object.freeze({
    key: 'report_id', version: '5.0.0', unique: ['report_id'],
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
    key: 'share_id', version: '5.0.0', unique: ['share_id'],
    columns: Object.freeze([
      ['share_id', 'string', true], ['token_sha256', 'string', true], ['report_id', 'string', true],
      ['snapshot_id', 'string', true], ['scope_key', 'string', true], ['scope_label', 'string', true],
      ['projection_sha256', 'string', true], ['data_version', 'string', true], ['active', 'boolean', true],
      ['created_at', 'datetime', true], ['expires_at', 'datetime', true], ['created_by', 'email', true]
    ])
  }),
  NEWSLETTER_RECIPIENTS: Object.freeze({
    key: 'recipient_uid', version: '5.0.0', unique: ['recipient_uid'],
    columns: Object.freeze([
      ['recipient_uid', 'string', true], ['report_id', 'string', true], ['snapshot_id', 'string', true],
      ['scope_key', 'string', true], ['scope_label', 'string', true],
      ['email', 'email', true], ['display_name', 'string', false], ['active', 'boolean', true],
      ['created_at', 'datetime', true], ['created_by', 'email', true],
      ['updated_at', 'datetime', true], ['updated_by', 'email', true]
    ])
  }),
  NEWSLETTER_AUDIT: Object.freeze({
    key: 'newsletter_id', version: '5.0.0', unique: ['newsletter_id'],
    columns: Object.freeze([
      ['newsletter_id', 'string', true], ['report_id', 'string', true],
      ['mode', 'enum', true, ['test', 'send']], ['scope_key', 'string', true],
      ['data_version', 'string', true], ['recipients_json', 'json', true],
      ['subject', 'string', true], ['facts_sha256', 'string', true],
      ['body_text', 'string', true], ['slides_url', 'url', true],
      ['recipient_count', 'number', true], ['effective_sender', 'email', true],
      ['created_at', 'datetime', true], ['created_by', 'email', true],
      ['status', 'enum', true, ['processing', 'sent', 'partial', 'failed']], ['details', 'string', false]
    ])
  }),
  ANALYTICS_EVENTS: Object.freeze({
    key: 'event_id', version: '5.0.0', unique: ['event_id'],
    columns: Object.freeze([
      ['event_id', 'string', true], ['event_at', 'datetime', true],
      ['user_email', 'email', true], ['session_id', 'string', true],
      ['event_name', 'string', true], ['route', 'string', false],
      ['panel', 'string', false], ['scope_key', 'string', false],
      ['duration_ms', 'number', false], ['status', 'string', false],
      ['details_json', 'json', true], ['user_agent', 'string', false]
    ])
  })
});
