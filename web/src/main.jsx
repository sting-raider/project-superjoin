import React, { useEffect, useMemo, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './styles.css'

const API = '/api/v1'

async function get(path) {
  const response = await fetch(API + path)
  if (!response.ok) throw new Error(await response.text())
  return response.json()
}

async function post(path, payload) {
  const response = await fetch(API + path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
  if (!response.ok) throw new Error(await response.text())
  return response.json()
}

function Badge({ children, tone = 'neutral' }) {
  return <span className={`badge badge-${tone}`}>{children}</span>
}

function Stat({ label, value, accent = false }) {
  return <div className="stat"><span>{label}</span><strong className={accent ? 'accent' : ''}>{value}</strong></div>
}

function App() {
  const [workspace, setWorkspace] = useState('')
  const [workspaces, setWorkspaces] = useState([])
  const [overview, setOverview] = useState(null)
  const [facts, setFacts] = useState([])
  const [cases, setCases] = useState([])
  const [relationships, setRelationships] = useState([])
  const [documents, setDocuments] = useState([])
  const [changes, setChanges] = useState([])
  const [reviews, setReviews] = useState([])
  const [runs, setRuns] = useState([])
  const [replay, setReplay] = useState(null)
  const [selectedFact, setSelectedFact] = useState(null)
  const [selectedCase, setSelectedCase] = useState(null)
  const [selectedDocument, setSelectedDocument] = useState(null)
  const [documentDetail, setDocumentDetail] = useState(null)
  const [documentLoading, setDocumentLoading] = useState(false)
  const [section, setSection] = useState('overview')
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(true)
  const [notice, setNotice] = useState('')

  const refresh = async (id = workspace) => {
    setLoading(true)
    try {
      const [nextOverview, nextFacts, nextCases, nextRelationships, nextDocuments, nextChanges, nextReviews, nextRuns, nextReplay] = await Promise.all([
        get(`/overview?workspace_id=${id}`), get(`/facts?workspace_id=${id}&limit=200`), get('/cases'),
        get(`/relationships?workspace_id=${id}`), get(`/documents?workspace_id=${id}`),
        get(`/changes?workspace_id=${id}`), get(`/reviews?workspace_id=${id}`), get(`/runs?workspace_id=${id}`),
        get('/demo/replay').catch(() => null),
      ])
      setOverview(nextOverview); setFacts(nextFacts.items); setCases(nextCases.items)
      setRelationships(nextRelationships.items); setDocuments(nextDocuments.items); setChanges(nextChanges.items); setReviews(nextReviews.items); setRuns(nextRuns.items); setReplay(nextReplay)
    } catch (error) { setNotice(error.message) } finally { setLoading(false) }
  }

  useEffect(() => {
    get('/workspaces').then((data) => {
      setWorkspaces(data.items)
      setWorkspace((current) => current && data.items.some((item) => item.id === current) ? current : (data.items[0]?.id || ''))
    }).catch((error) => setNotice(error.message))
  }, [])
  useEffect(() => { if (workspace) refresh(workspace) }, [workspace])

  const filteredFacts = useMemo(() => {
    if (!query.trim()) return facts
    const needle = query.toLowerCase()
    return facts.filter((fact) => [fact.subject, fact.predicate, fact.display_value, fact.period, fact.status].join(' ').toLowerCase().includes(needle))
  }, [facts, query])

  const tone = (status) => ({ CORROBORATED: 'good', SUPPORTED: 'good', CONTESTED: 'bad', UNRESOLVED: 'warn' }[status] || 'neutral')

  const openFact = async (fact) => {
    setSelectedCase(null); setSelectedDocument(null); setDocumentDetail(null)
    try { const data = await get(`/facts/${fact.id}`); setSelectedFact(data) } catch (error) { setNotice(error.message) }
  }

  const openDocument = async (document) => {
    setSelectedFact(null); setSelectedCase(null); setSelectedDocument(document); setDocumentDetail(null); setDocumentLoading(true)
    try { setDocumentDetail(await get(`/documents/${document.id}`)) } catch (error) { setNotice(error.message) } finally { setDocumentLoading(false) }
  }

  const resetDemo = async () => {
    await post('/demo/reset'); setNotice('Demo workspace reset'); await refresh()
  }

  const startReplay = async () => {
    try {
      const next = await post('/demo/replay/start')
      setReplay(next)
      if (next.workspace_id) setWorkspace(next.workspace_id)
      setNotice('Recorded replay checkpoint ready: two documents loaded, no API calls.')
      await refresh(next.workspace_id || workspace)
    } catch (error) { setNotice(error.message) }
  }

  const advanceReplay = async () => {
    try {
      const next = await post('/demo/replay/advance')
      setReplay(next)
      if (next.workspace_id) setWorkspace(next.workspace_id)
      setNotice('Recorded replay complete: the third document was ingested with no API calls.')
      await refresh(next.workspace_id || workspace)
    } catch (error) { setNotice(error.message) }
  }

  const onUpload = async (event) => {
    const file = event.target.files?.[0]; if (!file) return
    const body = new FormData(); body.append('file', file); body.append('workspace_id', workspace)
    setNotice(`Processing ${file.name}…`)
    const response = await fetch(`${API}/documents`, { method: 'POST', body })
    const data = await response.json()
    if (!response.ok) { setNotice(data.detail || 'Upload failed'); return }
    setNotice(data.deduplicated ? 'This PDF is already in the workspace.' : 'PDF queued. The workspace will update when processing completes.')
    setTimeout(() => refresh(), 1200)
  }

  const selectCase = async (item) => {
    setSelectedCase(item)
    if (item.workspace_id !== workspace) setWorkspace(item.workspace_id)
    if (item.relationship_id) {
      const relation = relationships.find((entry) => entry.id === item.relationship_id)
      if (relation) setSection('cases')
    }
  }

  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><div className="brand-mark">⌘</div><div><strong>Project SuperJoin</strong><small>Evidence workspace</small></div></div>
      <div className="workspace-picker"><label>WORKSPACE</label><select value={workspace} onChange={(event) => setWorkspace(event.target.value)}>{workspaces.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></div>
      <nav>
        {[['overview', 'Overview', '⌂'], ['facts', 'Facts', '▦'], ['documents', 'Documents', '▤'], ['cases', 'Required cases', '◈'], ['changes', 'Knowledge Diff', '↻'], ['runs', 'Runs', '▷'], ['review', 'Review', '✓'], ['trust', 'Trust Gate', '⊙'], ['settings', 'Settings', '⚙']].map(([key, label, icon]) => <button data-case-nav={key === 'cases' ? 'true' : undefined} aria-current={section === key ? 'page' : undefined} className={section === key ? 'nav-item active' : 'nav-item'} onClick={() => setSection(key)} key={key}><span aria-hidden="true">{icon}</span>{label}{key === 'cases' && cases.length > 0 && <em>{cases.length}</em>}</button>)}
      </nav>
      <div className="sidebar-foot">{overview?.demo ? <><Badge tone="good">● Demo mode</Badge><p>Recorded model outputs are available without an API key.</p>{replay?.stage === 'baseline_ready' ? <button className="text-button" onClick={advanceReplay}>Continue recorded replay</button> : replay?.stage === 'replayed' ? <p className="mono">Replay complete · no API calls</p> : <button className="text-button" onClick={startReplay}>Start recorded replay</button>}<button className="text-button" onClick={resetDemo}>Reset demo workspace</button></> : <><Badge tone="neutral">● Live workspace</Badge><p>Provider-backed PDF processing is enabled for this workspace.</p></>}</div>
    </aside>
    <main className="main">
      <header className="topbar"><div><span className="eyebrow">FACT KNOWLEDGE LAYER</span><h1>{overview?.workspace?.name || 'Workspace'}</h1></div><div className="top-actions"><label className="upload-button">＋ Upload PDF<input aria-label="Upload PDF" type="file" accept="application/pdf" onChange={onUpload} /></label><button className="icon-button" title="Search facts" aria-label="Search facts" onClick={() => setSection('facts')}>⌕</button></div></header>
      {notice && <div className="notice" role="status" aria-live="polite">{notice}<button aria-label="Dismiss notice" onClick={() => setNotice('')}>×</button></div>}
      {loading ? <div className="loading"><div className="spinner" />Loading the evidence layer…</div> : <>
        {section === 'overview' && <Overview overview={overview} facts={facts} cases={cases} onCase={selectCase} onOpenCases={() => setSection('cases')} />}
        {section === 'facts' && <Facts facts={filteredFacts} query={query} setQuery={setQuery} onSelect={openFact} />}
        {section === 'documents' && <Documents documents={documents} onUpload={onUpload} selectedDocument={selectedDocument} onSelect={openDocument} />}
        {section === 'cases' && <Cases cases={cases} relationships={relationships} selectedCase={selectedCase} onSelect={selectCase} />}
        {section === 'changes' && <Changes overview={overview} changes={changes} />}
        {section === 'runs' && <Runs runs={runs} onRefresh={() => refresh()} />}
        {section === 'review' && <Review workspace={workspace} reviews={reviews} facts={facts} onRefresh={() => refresh()} />}
        {section === 'trust' && <TrustGate workspace={workspace} facts={facts} />}
        {section === 'settings' && <Settings />}
      </>}
    </main>
    {(selectedFact || selectedCase || selectedDocument) && <Inspector fact={selectedFact} selectedCase={selectedCase} document={documentDetail || (selectedDocument ? { document: selectedDocument, pages: [] } : null)} documentLoading={documentLoading} relationships={relationships} onClose={() => { setSelectedFact(null); setSelectedCase(null); setSelectedDocument(null); setDocumentDetail(null) }} />}
  </div>
}

function Overview({ overview, facts, cases, onCase, onOpenCases }) {
  const statuses = overview?.statuses || {}
  return <div className="content"><section className="hero-panel"><div><span className="eyebrow green">EVIDENCE FIRST · REVISION {overview?.workspace?.active_revision || 1}</span><h2>See what changed,<br /><span>and why it matters.</span></h2><p>Project SuperJoin turns scattered PDFs into a living, inspectable layer of facts, evidence, conflicts, and temporal context.</p></div><div className="hero-diagram"><div className="flow-label">CURRENT KNOWLEDGE STATE</div><div className="flow-row"><div>PDFs</div><i>→</i><div>Claims</div><i>→</i><div className="flow-active">Facts</div></div><div className="flow-caption">Every accepted value keeps its source, context, and history.</div></div></section><section className="stats-grid"><Stat label="Documents" value={overview?.counts?.documents || 0} /><Stat label="Source claims" value={overview?.counts?.claims || 0} /><Stat label="Canonical facts" value={overview?.counts?.facts || 0} accent /><Stat label="Relationships" value={overview?.counts?.relationships || 0} /></section><section className="overview-grid"><div className="panel"><div className="panel-heading"><div><span className="eyebrow">KNOWLEDGE HEALTH</span><h3>What the layer knows</h3></div><span className="revision-dot">● LIVE</span></div><div className="health-list"><div><span className="health-dot good" />Supported <strong>{statuses.SUPPORTED || 0}</strong></div><div><span className="health-dot good" />Corroborated <strong>{statuses.CORROBORATED || 0}</strong></div><div><span className="health-dot bad" />Contested <strong>{statuses.CONTESTED || 0}</strong></div><div><span className="health-dot warn" />Needs review <strong>{statuses.UNRESOLVED || 0}</strong></div></div><div className="coverage"><span>Evidence coverage</span><strong>100%</strong><div><i style={{ width: '100%' }} /></div></div></div><div className="panel cases-panel"><div className="panel-heading"><div><span className="eyebrow">ASSIGNMENT CASES</span><h3>Walk the evaluator through it</h3></div><button className="link-button" onClick={onOpenCases}>Open all →</button></div>{cases.map((item) => <button className="case-row" onClick={() => onCase(item)} key={item.id}><span className="case-number">0{item.number}</span><span><strong>{item.title}</strong><small>{item.label}</small></span><Badge tone={item.label.includes('Failure') ? 'warn' : item.label.includes('conflict') ? 'bad' : 'good'}>view</Badge></button>)}</div></section><section className="panel diff-panel"><div className="panel-heading"><div><span className="eyebrow">LATEST KNOWLEDGE DIFF</span><h3>Changes stay explainable</h3></div><span className="mono">recorded-demo</span></div><div className="diff-cards"><div><strong>+ {overview?.counts?.claims || 0}</strong><span>source claims</span></div><div><strong>✓ {overview?.statuses?.CORROBORATED || 0}</strong><span>corroboration</span></div><div><strong>↻ 1</strong><span>reconciliation</span></div><div><strong>! {overview?.statuses?.CONTESTED || 0}</strong><span>contested</span></div></div></section></div>
}

function Facts({ facts, query, setQuery, onSelect }) {
  const exportFacts = () => { const blob = new Blob([JSON.stringify(facts, null, 2)], { type: 'application/json' }); const url = URL.createObjectURL(blob); const link = document.createElement('a'); link.href = url; link.download = 'project-superjoin-facts.json'; link.click(); URL.revokeObjectURL(url) }
  const openRow = (fact) => onSelect(fact)
  return <div className="content"><div className="section-heading"><div><span className="eyebrow">CANONICAL KNOWLEDGE</span><h2>Facts</h2><p>Derived views stay linked to immutable source claims.</p></div><button className="secondary-button" onClick={exportFacts}>Export JSON ↓</button></div><div className="toolbar"><div className="search"><span aria-hidden="true">⌕</span><input aria-label="Search facts" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search subject, predicate, value…" /></div><div className="filter-chip" aria-label="Fact status filter">All statuses⌄</div><div className="toolbar-count" aria-live="polite">{facts.length} visible</div></div><div className="table-card"><table><thead><tr><th scope="col">SUBJECT</th><th scope="col">FACT</th><th scope="col">VALUE</th><th scope="col">PERIOD</th><th scope="col">MODE</th><th scope="col">STATE</th><th scope="col">SOURCES</th></tr></thead><tbody>{facts.map((fact) => <tr tabIndex="0" role="button" aria-label={`Inspect ${fact.subject} ${fact.predicate}`} onClick={() => openRow(fact)} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); openRow(fact) } }} key={fact.id}><td><strong>{fact.subject}</strong></td><td><span className="predicate">{fact.predicate.replaceAll('_', ' ')}</span></td><td className="value-cell">{fact.display_value}</td><td className="mono">{fact.period || '—'}</td><td><span className="muted">{fact.modality || 'unknown'}</span></td><td><Badge tone={fact.status === 'CONTESTED' ? 'bad' : fact.status === 'CORROBORATED' ? 'good' : 'neutral'}>{fact.status}</Badge></td><td><span className="source-count" aria-label="Evidence available">◉</span></td></tr>)}</tbody></table>{facts.length === 0 && <div className="empty">No facts match that search.</div>}</div></div>
}

function Documents({ documents, onUpload, selectedDocument, onSelect }) {
  return <div className="content"><div className="section-heading"><div><span className="eyebrow">SOURCE LIBRARY</span><h2>Documents</h2><p>Every source remains visible beside the interpretations it supports.</p></div><label className="secondary-button">＋ Add PDF<input aria-label="Add PDF" type="file" accept="application/pdf" onChange={onUpload} /></label></div><div className="document-grid">{documents.map((document) => <button className={selectedDocument?.id === document.id ? 'document-card selected' : 'document-card'} key={document.id} onClick={() => onSelect(document)} aria-label={`Inspect ${document.name}`}><div className="doc-icon" aria-hidden="true">PDF</div><div className="document-info"><strong>{document.name}</strong><span>{document.publisher}</span><small>{document.page_count} PDF pages · {document.status === 'complete' ? 'parsed' : document.status}</small></div><Badge tone={document.status === 'complete' ? 'good' : 'warn'}>{document.status}</Badge><span className="document-open" aria-hidden="true">Inspect →</span></button>)}</div></div>
}

function Cases({ cases, relationships, selectedCase, onSelect }) {
  return <div className="content"><div className="section-heading"><div><span className="eyebrow">REQUIRED CASES</span><h2>Show the reasoning</h2><p>Four evaluator-ready paths through the evidence layer.</p></div></div><div className="case-grid">{cases.map((item) => { const relation = relationships.find((entry) => entry.id === item.relationship_id); return <button className={selectedCase?.id === item.id ? 'case-card selected' : 'case-card'} onClick={() => onSelect(item)} key={item.id}><span className="case-number">0{item.number}</span><Badge tone={item.label.includes('Failure') ? 'warn' : item.label.includes('conflict') ? 'bad' : 'good'}>{item.label}</Badge><h3>{item.title}</h3><p>{item.description}</p><div className="case-footer">{relation ? <><span>{relation.relationship_type}</span><span>Inspect evidence →</span></> : <><span>Native parser</span><span>Inspect failure →</span></>}</div></button> })}</div></div>
}

function Changes({ overview, changes }) {
  return <div className="content"><div className="section-heading"><div><span className="eyebrow">REVISION HISTORY</span><h2>Knowledge Diff</h2><p>Changes are attached to a source, a run, or a review decision.</p></div></div><div className="panel diff-detail"><div className="diff-banner"><span className="revision-dot">●</span><div><strong>Committed knowledge revision</strong><span>Project SuperJoin revision {overview?.workspace?.active_revision || 1} · {changes.length} recorded changes</span></div></div>{changes.length ? changes.map((change) => <div className="change-line" key={change.id}><span className={`change-symbol ${change.kind.includes('conflict') ? 'conflict' : change.kind.includes('reconcile') ? 'reconcile' : 'plus'}`}>{change.kind.includes('conflict') ? '!' : change.kind.includes('reconcile') ? '↻' : '＋'}</span><div><strong>{change.summary}</strong><small>{change.kind} · {change.run_id || 'recorded'}</small></div><b>view</b></div>) : <div className="empty">No changes recorded for this workspace.</div>}</div></div>
}

function Runs({ runs, onRefresh }) {
  const [expandedRunId, setExpandedRunId] = useState(null)
  const [callsByRun, setCallsByRun] = useState({})
  const [loadingRunId, setLoadingRunId] = useState(null)
  const [telemetryError, setTelemetryError] = useState('')
  const act = async (run, path) => { try { await post(`/runs/${run.id}/${path}`); onRefresh() } catch (error) { /* the app-level notice remains available for the next refresh */ onRefresh() } }
  const inspectTelemetry = async (run) => {
    if (expandedRunId === run.id) { setExpandedRunId(null); return }
    setExpandedRunId(run.id); setTelemetryError('')
    if (callsByRun[run.id]) return
    setLoadingRunId(run.id)
    try {
      const data = await get(`/runs/${run.id}/model-calls`)
      setCallsByRun((current) => ({ ...current, [run.id]: data.items || [] }))
    } catch (error) { setTelemetryError(error.message || 'Unable to load model telemetry') } finally { setLoadingRunId(null) }
  }
  const calls = expandedRunId ? (callsByRun[expandedRunId] || []) : []
  const spend = calls.reduce((total, call) => total + Number(call.estimated_cost || 0), 0)
  const cacheHits = calls.reduce((total, call) => total + Number(call.cache_hit || 0), 0)
  return <div className="content"><div className="section-heading"><div><span className="eyebrow">OBSERVABILITY</span><h2>Runs</h2><p>Durable parser, extraction, and publication progress for this workspace.</p></div></div><div className="panel run-list">{runs.length ? runs.map((run) => <React.Fragment key={run.id}><div className="run-row"><div><strong>{run.mode} · {run.id}</strong><small>{run.message || 'Queued'} · updated {run.updated_at}</small></div><div className="run-progress"><Badge tone={run.status === 'complete' ? 'good' : run.status === 'failed' ? 'bad' : run.status === 'cancelled' ? 'neutral' : 'warn'}>{run.status}</Badge><span>{run.progress}%</span><i aria-hidden="true"><b style={{ width: `${run.progress || 0}%` }} /></i><div className="run-actions">{['queued', 'processing'].includes(run.status) && <button className="text-button" onClick={() => act(run, 'cancel')}>Cancel</button>}{['failed', 'cancelled'].includes(run.status) && <button className="text-button" onClick={() => act(run, 'resume')}>Resume</button>}<button className="text-button" aria-expanded={expandedRunId === run.id} onClick={() => inspectTelemetry(run)}>{expandedRunId === run.id ? 'Hide telemetry' : 'Inspect telemetry'}</button></div></div></div>{expandedRunId === run.id && <div className="run-telemetry" role="region" aria-label={`Model telemetry for ${run.id}`}>{loadingRunId === run.id ? <div className="empty">Loading model telemetry…</div> : telemetryError ? <div className="empty">{telemetryError}</div> : <><div className="telemetry-summary"><span><strong>{calls.length}</strong> calls</span><span><strong>${spend.toFixed(4)}</strong> spend</span><span><strong>{cacheHits}</strong> cache hits</span></div>{calls.length ? <table><thead><tr><th scope="col">ROLE</th><th scope="col">MODEL</th><th scope="col">STATUS</th><th scope="col">TOKENS</th><th scope="col">LATENCY</th><th scope="col">ATTEMPTS</th><th scope="col">COST</th></tr></thead><tbody>{calls.map((call) => <tr key={call.id}><td>{call.role}</td><td className="mono">{call.model || '—'}</td><td><Badge tone={call.status === 'complete' ? 'good' : call.status === 'failed' ? 'bad' : 'warn'}>{call.status}</Badge></td><td className="mono">{call.input_tokens || 0} / {call.output_tokens || 0}</td><td className="mono">{call.latency_ms == null ? '—' : `${call.latency_ms} ms`}</td><td className="mono">{call.attempts || 1}</td><td className="mono">${Number(call.estimated_cost || 0).toFixed(4)}</td></tr>)}</tbody></table> : <div className="empty">No model calls recorded for this run. Recorded demo replay intentionally stays offline.</div>}</>}</div>}</React.Fragment>) : <div className="empty">No runs recorded for this workspace yet.</div>}</div></div>
}

function Settings() {
  const [settings, setSettings] = useState(null)
  const [activeRole, setActiveRole] = useState('extraction')
  const [drafts, setDrafts] = useState({})
  const [status, setStatus] = useState('')
  const [saving, setSaving] = useState(false)
  const roleCards = [['extraction', 'Extraction'], ['reasoning', 'Reasoning'], ['vision', 'Vision'], ['embeddings', 'Embeddings']]
  const hydrate = (data) => {
    setSettings(data)
    setDrafts((current) => {
      const next = { ...current }
      roleCards.forEach(([key]) => {
        const role = data.roles?.[key] || {}
        next[key] = {
          base_url: role.base_url || '', model: role.model || '', path: role.chat_path || role.embedding_path || '',
          api_key: '', clear_api_key: false, timeout_seconds: role.timeout_seconds || 90,
          max_output_tokens: role.max_output_tokens || 1200, concurrency: role.concurrency || 1,
          structured_output_mode: role.structured_output_mode || 'json_object', auth_header: role.auth_header || 'Authorization',
          auth_scheme: role.auth_scheme ?? 'Bearer', send_model: role.send_model ?? true,
          dimensions: role.dimensions || 768, include_dimensions: role.include_dimensions ?? true,
          task_type: role.task_type || 'retrieval_document', extra_body_json: '',
        }
      })
      return next
    })
  }
  useEffect(() => { get('/settings').then(hydrate).catch((error) => setStatus(error.message)) }, [])
  const draft = drafts[activeRole] || {}
  const change = (field, value) => setDrafts((current) => ({ ...current, [activeRole]: { ...current[activeRole], [field]: value } }))
  const applyPreset = (id) => {
    const preset = settings?.presets?.find((item) => item.id === id)
    if (!preset) return
    setDrafts((current) => ({ ...current, [activeRole]: { ...current[activeRole], ...Object.fromEntries(Object.entries(preset).filter(([key]) => !['id', 'label'].includes(key))) } }))
  }
  const save = async (event) => {
    event.preventDefault(); setSaving(true); setStatus('')
    const payload = { ...draft }
    if (!payload.api_key) delete payload.api_key
    if (activeRole === 'embeddings') { delete payload.max_output_tokens; delete payload.structured_output_mode } else { delete payload.dimensions; delete payload.include_dimensions; delete payload.task_type }
    try { hydrate(await post(`/settings/${activeRole}`, payload)); setStatus(`${activeRole} configuration is active in this process.`) } catch (error) { setStatus(error.message) } finally { setSaving(false) }
  }
  const testConnection = async () => {
    setSaving(true); setStatus(`Testing ${activeRole}…`)
    try { const result = await post(`/settings/${activeRole}/test`); setStatus(`Connected to ${result.model} in ${result.latency_ms} ms.`) } catch (error) { setStatus(error.message) } finally { setSaving(false) }
  }
  return <div className="content"><div className="section-heading"><div><span className="eyebrow">RUNTIME CONFIGURATION</span><h2>Provider desk</h2><p>Configure each OpenAI-compatible role independently. Changes last until this container restarts.</p></div></div><div className="provider-tabs" role="tablist">{roleCards.map(([key, label]) => { const role = settings?.roles?.[key]; return <button key={key} role="tab" aria-selected={activeRole === key} className={activeRole === key ? 'provider-tab active' : 'provider-tab'} onClick={() => { setActiveRole(key); setStatus('') }}><span>{label}</span><Badge tone={role?.configured ? 'good' : 'warn'}>{role?.configured ? 'ready' : 'offline'}</Badge><small>{role?.model || 'No model'}</small></button> })}</div><form className="provider-editor" onSubmit={save}><div className="provider-editor-head"><div><span className="eyebrow">{activeRole.toUpperCase()} ROLE</span><h3>Connection contract</h3></div><select aria-label="Provider preset" defaultValue="" onChange={(event) => applyPreset(event.target.value)}><option value="" disabled>Choose a preset…</option>{settings?.presets?.map((preset) => <option value={preset.id} key={preset.id}>{preset.label}</option>)}</select></div><div className="provider-fields"><label className="wide">BASE URL<input value={draft.base_url || ''} onChange={(event) => change('base_url', event.target.value)} placeholder="https://provider.example/v1" /></label><label>MODEL<input value={draft.model || ''} onChange={(event) => change('model', event.target.value)} placeholder="Any provider model name" /></label><label>API KEY<input type="password" autoComplete="new-password" value={draft.api_key || ''} onChange={(event) => change('api_key', event.target.value)} placeholder={settings?.roles?.[activeRole]?.key_configured ? 'Configured · enter to replace' : 'Optional for local endpoints'} /></label><label className="wide">REQUEST PATH<input value={draft.path || ''} onChange={(event) => change('path', event.target.value)} placeholder={activeRole === 'embeddings' ? '/embeddings' : '/chat/completions'} /></label><label>TIMEOUT · SECONDS<input type="number" min="1" max="600" value={draft.timeout_seconds || 90} onChange={(event) => change('timeout_seconds', Number(event.target.value))} /></label><label>CONCURRENCY<input type="number" min="1" max="64" value={draft.concurrency || 1} onChange={(event) => change('concurrency', Number(event.target.value))} /></label>{activeRole === 'embeddings' ? <><label>DIMENSIONS<input type="number" min="1" value={draft.dimensions || 768} onChange={(event) => change('dimensions', Number(event.target.value))} /></label><label>TASK TYPE<input value={draft.task_type || ''} onChange={(event) => change('task_type', event.target.value)} /></label></> : <><label>OUTPUT TOKEN LIMIT<input type="number" min="1" value={draft.max_output_tokens || 1200} onChange={(event) => change('max_output_tokens', Number(event.target.value))} /></label><label>STRUCTURED OUTPUT<select value={draft.structured_output_mode || 'none'} onChange={(event) => change('structured_output_mode', event.target.value)}><option value="json_object">JSON object</option><option value="json_schema">JSON schema</option><option value="none">None</option></select></label></>}<label>AUTH HEADER<input value={draft.auth_header || ''} onChange={(event) => change('auth_header', event.target.value)} /></label><label>AUTH SCHEME<input value={draft.auth_scheme ?? ''} onChange={(event) => change('auth_scheme', event.target.value)} placeholder="Bearer or blank" /></label><label className="wide">EXTRA REQUEST BODY · JSON<input value={draft.extra_body_json || ''} onChange={(event) => change('extra_body_json', event.target.value)} placeholder='{"thinking":{"type":"disabled"}}' /></label></div><div className="provider-controls"><label className="checkbox"><input type="checkbox" checked={draft.send_model ?? true} onChange={(event) => change('send_model', event.target.checked)} /> Send model field</label>{activeRole === 'embeddings' && <label className="checkbox"><input type="checkbox" checked={draft.include_dimensions ?? true} onChange={(event) => change('include_dimensions', event.target.checked)} /> Send dimensions</label>}<label className="checkbox danger"><input type="checkbox" checked={draft.clear_api_key || false} onChange={(event) => change('clear_api_key', event.target.checked)} /> Clear saved runtime key</label><div className="provider-actions"><button type="button" className="secondary-button" disabled={saving} onClick={testConnection}>Test connection</button><button className="upload-button" disabled={saving} type="submit">{saving ? 'Working…' : 'Apply settings'}</button></div></div>{status && <p className="provider-status" role="status">{status}</p>}</form><div className="settings-ledger"><div><span>Parser</span><strong>{settings?.parser?.backend || 'liteparse'} · {settings?.parser?.local_ocr_enabled ? 'selective local OCR' : 'native only'}</strong></div><div><span>Budget remaining</span><strong>${settings?.budget?.remaining_usd?.toFixed?.(4) || '20.0000'}</strong></div><div><span>Retry policy</span><strong>{settings?.provider_retry?.attempts || 1} attempts · {settings?.provider_retry?.backoff_seconds || 0}s backoff</strong></div><p>API keys stay in process memory, are never returned by the API, and disappear when the container restarts. Remote endpoints require HTTPS; local HTTP is restricted to localhost.</p></div></div>
}

function Review({ workspace, reviews, facts, onRefresh }) {
  const [factId, setFactId] = useState(facts.find((fact) => fact.status === 'CONTESTED')?.id || facts[0]?.id || '')
  const [action, setAction] = useState('keep_unresolved')
  const [rationale, setRationale] = useState('')
  const [notice, setNotice] = useState('')
  useEffect(() => { if (!facts.some((fact) => fact.id === factId)) setFactId(facts.find((fact) => fact.status === 'CONTESTED')?.id || facts[0]?.id || '') }, [facts, factId])
  const submit = async (event) => { event.preventDefault(); if (!factId || !rationale.trim()) return setNotice('Choose a fact and provide a rationale.'); try { await post('/reviews', { workspace_id: workspace, fact_id: factId, action, rationale }); setNotice('Immutable review recorded.'); setRationale(''); onRefresh() } catch (error) { setNotice(error.message) } }
  return <div className="content"><div className="section-heading"><div><span className="eyebrow">HUMAN REVIEW</span><h2>Review queue</h2><p>Decisions attach to a fact revision and never overwrite source claims.</p></div></div><div className="review-layout"><form className="panel review-form" onSubmit={submit}><label>FACT<select value={factId} onChange={(event) => setFactId(event.target.value)}>{facts.map((fact) => <option value={fact.id} key={fact.id}>{fact.subject} · {fact.predicate} · {fact.period || 'no period'}</option>)}</select></label><label>DECISION<select value={action} onChange={(event) => setAction(event.target.value)}><option value="keep_unresolved">Keep unresolved</option><option value="prefer">Prefer for a named use</option><option value="confirm_context">Confirm context distinction</option></select></label><label>RATIONALE<textarea value={rationale} onChange={(event) => setRationale(event.target.value)} placeholder="Why should this decision apply to this revision?" rows="5" /></label><button className="upload-button" type="submit">Record decision</button>{notice && <p className="form-notice">{notice}</p>}</form><div className="panel"><span className="eyebrow">DECISION LEDGER</span>{reviews.length ? reviews.map((review) => <div className="review-row" key={review.id}><Badge tone={review.stale ? 'warn' : 'good'}>{review.status}</Badge><div><strong>{review.action}</strong><small>{review.rationale}</small></div><span className="mono">rev {review.based_on_revision}</span></div>) : <div className="empty">No decisions recorded.</div>}</div></div></div>
}

function TrustGate({ workspace, facts }) {
  const [subject, setSubject] = useState('')
  const [predicate, setPredicate] = useState('')
  const [period, setPeriod] = useState('')
  const [policy, setPolicy] = useState('strict')
  const [result, setResult] = useState(null)
  useEffect(() => {
    const firstFact = facts.find((fact) => fact.subject && fact.predicate)
    setSubject(firstFact?.subject || '')
    setPredicate(firstFact?.predicate || '')
    setPeriod(firstFact?.period || '')
    setResult(null)
  }, [workspace, facts])
  const run = async (event) => { event.preventDefault(); try { setResult(await post('/resolve', { workspace_id: workspace, subject, predicate, period, policy })) } catch (error) { setResult({ error: error.message }) } }
  return <div className="content"><div className="section-heading"><div><span className="eyebrow">MACHINE CONSUMPTION</span><h2>Trust Gate</h2><p>Ask for a fact; blocked decisions return alternatives instead of an executable value.</p></div></div><div className="trust-layout"><form className="panel trust-form" onSubmit={run}><label>SUBJECT<input value={subject} onChange={(event) => setSubject(event.target.value)} /></label><label>PREDICATE<input value={predicate} onChange={(event) => setPredicate(event.target.value)} /></label><label>PERIOD<input value={period} onChange={(event) => setPeriod(event.target.value)} placeholder="Optional" /></label><label>POLICY<select value={policy} onChange={(event) => setPolicy(event.target.value)}><option value="strict">Strict</option><option value="human_preference">Explicit human preference</option></select></label><button className="upload-button" type="submit">Resolve fact</button></form><div className="panel gate-result">{result ? <><Badge tone={result.safe_to_use ? 'good' : 'bad'}>{result.decision}</Badge><h3>{result.safe_to_use ? result.display_value : 'No executable value'}</h3><p>{(result.reason_codes || []).join(' · ')}</p><pre>{JSON.stringify(result, null, 2)}</pre></> : <div className="empty">Submit a query to inspect the signed-off JSON response.</div>}</div></div></div>
}

function Inspector({ fact, selectedCase, document, documentLoading, relationships, onClose }) {
  const relation = selectedCase?.relationship_id ? relationships.find((entry) => entry.id === selectedCase.relationship_id) : null
  return <aside className="inspector" aria-label="Evidence inspector"><div className="inspector-top"><span className="eyebrow">EVIDENCE INSPECTOR</span><button className="close-button" aria-label="Close evidence inspector" onClick={onClose}>×</button></div>{fact ? <><Badge tone={fact.fact.status === 'CONTESTED' ? 'bad' : 'good'}>{fact.fact.status}</Badge><h2>{fact.fact.predicate.replaceAll('_', ' ')}</h2><div className="inspector-value">{fact.fact.display_value}</div><div className="inspector-meta">{fact.fact.period || 'No period'} · {fact.fact.scope || 'Scope unspecified'}</div><div className="inspector-rule" /><h4>SOURCE EVIDENCE</h4>{(fact.anchors || []).map((anchor) => <div className="evidence-block" key={anchor.id}><div><strong>{anchor.document_id}</strong><span>PDF p.{anchor.pdf_page} · printed p.{anchor.printed_page || '—'} · {anchor.precision}</span></div><p>“{anchor.text}”</p></div>)}<div className="inspector-rule" /><h4>NORMALIZED INTERPRETATION</h4><p className="reasoning">{fact.fact.reason}</p>{fact.interpretations?.slice(0, 3).map((interpretation) => <div className="relation-chip" key={interpretation.id}><Badge tone="neutral">{interpretation.value_type}</Badge><span>{interpretation.predicate} · {interpretation.normalized_value || 'text'} · {interpretation.eligibility}</span></div>)}{fact.relationships.map((entry) => <div className="relation-chip" key={entry.id}><Badge tone={entry.relationship_type === 'CONTRADICTS' ? 'bad' : 'good'}>{entry.relationship_type}</Badge><span>{entry.reason}</span></div>)}</> : selectedCase ? <><Badge tone={selectedCase.label.includes('Failure') ? 'warn' : selectedCase.label.includes('conflict') ? 'bad' : 'good'}>{selectedCase.label}</Badge><h2>{selectedCase.title}</h2><p className="case-description">{selectedCase.description}</p>{relation ? <><div className="inspector-rule" /><h4>SYSTEM INTERPRETATION</h4><div className="relationship-hero"><strong>{relation.relationship_type}</strong><p>{relation.reason}</p></div><h4>COMPARISON DIMENSIONS</h4><div className="dimension-list">{Object.entries(relation.dimensions || {}).map(([key, value]) => <div key={key}><span>{key.replaceAll('_', ' ')}</span><strong>{value}</strong></div>)}</div></> : <><div className="inspector-rule" /><h4>OBSERVED FAILURE</h4><div className="failure-box"><strong>Native text extraction returned zero characters.</strong><p>The page is visually readable, so the adaptive parser routes it to a configured visual model. Without one, the claim remains quarantined rather than invented.</p></div></>} </> : document ? <DocumentInspector document={document} loading={documentLoading} /> : null}</aside>
}

function DocumentInspector({ document, loading }) {
  const pages = document.pages || []
  const sourceHref = document.document.stored_path ? `${API}/documents/${encodeURIComponent(document.document.id)}/file` : document.document.source_url
  const parseFlags = (page) => Array.isArray(page.quality_flags) ? page.quality_flags : []
  const pageHref = (page) => sourceHref ? `${sourceHref}${sourceHref.includes('#') ? '&' : '#'}page=${encodeURIComponent(page.page_number)}` : ''
  return <>{loading ? <div className="empty">Loading document evidence…</div> : <><Badge tone={document.document.status === 'complete' ? 'good' : 'warn'}>{document.document.status}</Badge><h2 className="document-inspector-title">{document.document.name}</h2><div className="inspector-meta">{document.document.publisher} · {document.document.page_count || pages.length} PDF pages</div>{sourceHref && <a className="document-source-link" href={sourceHref} target="_blank" rel="noreferrer">Open original PDF ↗</a>}<div className="inspector-rule" /><h4>PARSE ARTIFACT</h4><div className="document-metadata"><div><span>Parser</span><strong>{document.document.parser || 'pending'}</strong></div><div><span>Quality score</span><strong>{document.document.quality_score == null ? '—' : Number(document.document.quality_score).toFixed(2)}</strong></div><div><span>Publication</span><strong>{document.document.published_at || '—'}</strong></div></div><h4 className="document-pages-heading">PAGE MAP</h4>{pages.length ? <div className="page-list">{pages.map((page) => { const flags = parseFlags(page); return <div className="page-row" key={page.id}><div><strong>PDF p.{page.page_number}</strong><span>Printed p.{page.printed_label || '—'} · {page.parser}</span></div><div className="page-status"><Badge tone={page.disposition === 'native' ? 'good' : page.disposition === 'visual' ? 'warn' : 'neutral'}>{page.disposition}</Badge><small>{page.native_text?.length || 0} native chars{flags.length ? ` · ${flags.join(', ')}` : ''}</small>{pageHref(page) && <a className="page-link" href={pageHref(page)} target="_blank" rel="noreferrer">Open page ↗</a>}</div></div> })}</div> : <div className="empty">No page artifacts recorded yet.</div>}</>}</>
}

createRoot(document.getElementById('root')).render(<App />)
