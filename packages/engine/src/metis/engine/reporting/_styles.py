"""CSS for the self-contained HTML eval report."""

REPORT_CSS = """\
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; padding: 20px 32px; background: #f9fafb; color: #111827; max-width: 1400px; margin: 0 auto; }
h1 { font-size: 22px; margin-bottom: 2px; }
h2 { font-size: 16px; margin: 24px 0 10px; color: #374151; }
.subtitle { color: #6b7280; margin-bottom: 20px; font-size: 13px; }
.description { color: #374151; margin-bottom: 12px; font-size: 14px; }
.summary-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(100px, 1fr)); gap: 10px; margin-bottom: 24px; }
.card { background: white; border-radius: 8px; padding: 14px 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
.card-value { font-size: 26px; font-weight: 700; }
.card-label { color: #6b7280; font-size: 12px; margin-top: 2px; }
.section { margin-bottom: 24px; }
code { background: #f3f4f6; padding: 2px 5px; border-radius: 3px; font-size: 11px; }
details { margin-top: 6px; }
details summary { cursor: pointer; color: #6b7280; font-size: 13px; }

/* Task / Behaviour / AC hierarchy */
.task-section { background: white; border-radius: 8px; margin-bottom: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); overflow: hidden; }
.task-title { padding: 12px 16px; font-size: 15px; font-weight: 700; color: #111827; cursor: pointer; text-transform: capitalize; background: #f9fafb; border-bottom: 1px solid #e5e7eb; }
.task-title:hover { background: #f3f4f6; }
.task-body { padding: 10px 16px 16px; }
.task-context { margin-bottom: 12px; padding: 10px 12px; background: #f0f9ff; border: 1px solid #bae6fd; border-radius: 6px; }
.task-description { font-size: 12px; color: #1e40af; line-height: 1.5; margin-bottom: 6px; }
.task-meta { display: flex; flex-direction: column; gap: 3px; }
.task-meta-item { font-size: 11px; color: #374151; line-height: 1.4; }
.task-meta-item strong { color: #1e3a5f; }
.behaviour-rate { font-size: 16px; font-weight: 700; }
.ac-list { padding-left: 12px; margin-top: 6px; }
.ac-row { margin-bottom: 6px; padding: 8px 10px; background: #f9fafb; border-radius: 6px; border: 1px solid #e5e7eb; }
.ac-header { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.ac-desc { font-size: 12px; color: #374151; flex: 1; }
.ac-pass { font-size: 11px; font-weight: 600; color: #166534; background: #dcfce7; padding: 2px 6px; border-radius: 4px; white-space: nowrap; }
.ac-fail { font-size: 11px; font-weight: 600; color: #991b1b; background: #fecaca; padding: 2px 6px; border-radius: 4px; white-space: nowrap; }
.ac-nodata { font-size: 11px; color: #9ca3af; }
.ac-failures-toggle { margin-top: 6px; }
.ac-failures-summary { font-size: 11px; color: #991b1b; cursor: pointer; padding: 2px 0; }
.ac-failures { margin-top: 6px; padding-left: 8px; border-left: 3px solid #fecaca; }
.ac-failure { margin-bottom: 8px; padding: 6px 10px; background: #fef2f2; border-radius: 5px; }
.ac-failure-reason { font-size: 11px; color: #1f2937; line-height: 1.4; margin-bottom: 3px; }
.ac-failure-meta { font-size: 10px; color: #6b7280; margin-bottom: 3px; }
.ac-turns { margin-top: 6px; }
.ac-turn { padding: 6px 8px; margin-bottom: 4px; border-radius: 5px; background: white; }
.ac-turn-label { font-size: 10px; font-weight: 600; color: #6b7280; margin-bottom: 3px; }
.ac-turn-io { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
.ac-turn-io pre { background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 4px; padding: 6px; font-size: 10px; white-space: pre-wrap; word-break: break-word; max-height: 250px; overflow-y: auto; }
.context-label { font-size: 9px; font-weight: 600; color: #6b7280; text-transform: uppercase; margin-bottom: 2px; }


/* Secondary sections */
.secondary-section { margin-top: 36px; border-top: 2px solid #e5e7eb; padding-top: 16px; }
.secondary-section > details > summary { font-size: 15px; font-weight: 600; color: #6b7280; padding: 6px 0; }
table { width: 100%; border-collapse: collapse; background: white; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); overflow: hidden; margin-top: 12px; }
th { background: #f3f4f6; text-align: left; padding: 10px 12px; font-size: 13px; color: #374151; }
td { padding: 10px 12px; border-top: 1px solid #e5e7eb; font-size: 13px; }
tr:hover { background: #f9fafb; }

/* Trace detail (secondary) */
.trace-card { background: white; border-radius: 8px; margin-bottom: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
.trace-card summary { padding: 14px 16px; cursor: pointer; display: flex; align-items: center; gap: 10px; font-size: 13px; }
.trace-card summary:hover { background: #f9fafb; border-radius: 8px; }
.trace-meta { color: #6b7280; font-size: 12px; margin-left: auto; }
.trace-body { padding: 0 16px 16px; }
.session-turn { border: 1px solid #e5e7eb; border-radius: 8px; padding: 12px; margin-bottom: 10px; }
.session-turn-header { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; font-size: 13px; }
.session-turn-io { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 8px; }
.io-block pre { background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 6px; padding: 10px; font-size: 11px; white-space: pre-wrap; word-break: break-word; max-height: 500px; overflow-y: auto; }
.metrics-dropdown { margin-top: 6px; }
.metrics-dropdown summary { cursor: pointer; color: #6b7280; font-size: 12px; font-weight: 500; padding: 4px 0; }
.trace-metrics-list { display: flex; flex-direction: column; gap: 6px; margin-top: 6px; }
.trace-metric { padding: 8px 12px; background: #f9fafb; border-radius: 6px; border: 1px solid #e5e7eb; }
.trace-metric-header { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.trace-metric-name { font-size: 12px; font-weight: 500; color: #374151; }
.trace-metric-reason { font-size: 12px; color: #6b7280; line-height: 1.4; }
.badge { padding: 2px 6px; border-radius: 4px; font-size: 11px; font-weight: 600; }
.badge-pass { background: #dcfce7; color: #166534; }
.badge-fail { background: #fecaca; color: #991b1b; }
.badge-skip { background: #e5e7eb; color: #6b7280; }
"""
