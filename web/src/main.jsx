import React, { useEffect, useState } from 'react'
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

async function remove(path) {
  const response = await fetch(API + path, { method: 'DELETE' })
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
  const [factResults, setFactResults] = useState([])
  const [factTotal, setFactTotal] = useState(0)
  const [factStatuses, setFactStatuses] = useState([])
  const [factStatus, setFactStatus] = useState('')
  const [factsLoading, setFactsLoading] = useState(false)
  const [relationships, setRelationships] = useState([])
  const [documents, setDocuments] = useState([])
  const [changes, setChanges] = useState([])
  const [reviews, setReviews] = useState([])
  const [runs, setRuns] = useState([])
  const [selectedFact, setSelectedFact] = useState(null)
  const [selectedRelationship, setSelectedRelationship] = useState(null)
  const [selectedDocument, setSelectedDocument] = useState(null)
  const [documentDetail, setDocumentDetail] = useState(null)
  const [documentLoading, setDocumentLoading] = useState(false)
  const [section, setSection] = useState('overview')
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(true)
  const [notice, setNotice] = useState('')
  const [showWorkspaceForm, setShowWorkspaceForm] = useState(false)
  const [newWorkspaceName, setNewWorkspaceName] = useState('')

  const refresh = async (id = workspace, quiet = false) => {
    if (!id) { setLoading(false); return }
    if (!quiet) setLoading(true)
    try {
      const [nextOverview, nextFacts, nextRelationships, nextDocuments, nextChanges, nextReviews, nextRuns] = await Promise.all([
        get(`/overview?workspace_id=${id}`), get(`/facts?workspace_id=${id}&limit=200`),
        get(`/relationships?workspace_id=${id}`), get(`/documents?workspace_id=${id}`),
        get(`/changes?workspace_id=${id}`), get(`/reviews?workspace_id=${id}`), get(`/runs?workspace_id=${id}`),
      ])
      setOverview(nextOverview); setFacts(nextFacts.items); setFactResults(nextFacts.items); setFactTotal(nextFacts.total ?? nextFacts.count ?? nextFacts.items.length); setFactStatuses(nextFacts.statuses || [])
      setRelationships(nextRelationships.items); setDocuments(nextDocuments.items); setChanges(nextChanges.items); setReviews(nextReviews.items); setRuns(nextRuns.items)
    } catch (error) { setNotice(error.message) } finally { if (!quiet) setLoading(false) }
  }

  useEffect(() => {
    get('/workspaces').then((data) => {
      setWorkspaces(data.items)
      setWorkspace((current) => current && data.items.some((item) => item.id === current) ? current : (data.items[0]?.id || ''))
      if (!data.items.length) setLoading(false)
    }).catch((error) => { setNotice(error.message); setLoading(false) })
  }, [])
  useEffect(() => { if (workspace) refresh(workspace) }, [workspace])
  useEffect(() => {
    if (!workspace || !runs.some((run) => ['queued', 'processing'].includes(run.status))) return undefined
    const timer = window.setTimeout(() => refresh(workspace, true), 1500)
    return () => window.clearTimeout(timer)
  }, [workspace, runs])

  useEffect(() => {
    if (!workspace) return undefined
    const controller = new AbortController()
    const timer = window.setTimeout(async () => {
      setFactsLoading(true)
      try {
        const params = new URLSearchParams({ workspace_id: workspace, limit: '200' })
        if (query.trim()) params.set('q', query.trim())
        if (factStatus) params.set('status', factStatus)
        const response = await fetch(`${API}/facts?${params}`, { signal: controller.signal })
        if (!response.ok) throw new Error(await response.text())
        const data = await response.json()
        setFactResults(data.items || []); setFactTotal(data.total ?? data.count ?? 0); setFactStatuses(data.statuses || [])
      } catch (error) { if (error.name !== 'AbortError') setNotice(error.message) } finally { setFactsLoading(false) }
    }, 300)
    return () => { window.clearTimeout(timer); controller.abort() }
  }, [workspace, query, factStatus])

  const tone = (status) => ({ CORROBORATED: 'good', SUPPORTED: 'good', CONTESTED: 'bad', UNRESOLVED: 'warn' }[status] || 'neutral')

  const openFact = async (fact) => {
    setSelectedRelationship(null); setSelectedDocument(null); setDocumentDetail(null)
    try { const data = await get(`/facts/${fact.id}`); setSelectedFact(data) } catch (error) { setNotice(error.message) }
  }

  const openDocument = async (document) => {
    setSelectedFact(null); setSelectedRelationship(null); setSelectedDocument(document); setDocumentDetail(null); setDocumentLoading(true)
    try { setDocumentDetail(await get(`/documents/${document.id}`)) } catch (error) { setNotice(error.message) } finally { setDocumentLoading(false) }
  }

  const onUpload = async (event) => {
    const files = Array.from(event.target.files || []); if (!files.length) return
    event.target.value = ''
    let queued = 0; let duplicates = 0
    try {
      for (const file of files) {
        setNotice(`Adding ${queued + duplicates + 1} of ${files.length}: ${file.name}…`)
        const body = new FormData(); body.append('file', file); body.append('workspace_id', workspace)
        const response = await fetch(`${API}/documents`, { method: 'POST', body })
        const data = await response.json()
        if (!response.ok) throw new Error(data.detail || `Upload failed for ${file.name}`)
        if (data.deduplicated) duplicates += 1; else queued += 1
      }
      await refresh(workspace)
      setNotice(`${queued} PDF${queued === 1 ? '' : 's'} queued for this workspace${duplicates ? ` · ${duplicates} already present` : ''}. Follow live progress under Runs.`)
      setTimeout(() => refresh(workspace, true), 1400)
    } catch (error) { setNotice(error.message) }
  }

  const createWorkspace = async (event) => {
    event.preventDefault()
    if (!newWorkspaceName.trim()) return
    try {
      const created = await post('/workspaces', { name: newWorkspaceName.trim() })
      const data = await get('/workspaces')
      setWorkspaces(data.items); setWorkspace(created.id); setNewWorkspaceName(''); setShowWorkspaceForm(false); setSection('overview'); setNotice(`Created ${created.name}. Upload a PDF to build its first knowledge revision.`)
    } catch (error) { setNotice(error.message) }
  }

  const deleteWorkspace = async () => {
    const current = workspaces.find((item) => item.id === workspace)
    if (!current || !window.confirm(`Delete “${current.name}” and all of its local documents, claims, facts, and history? This cannot be undone.`)) return
    try {
      await remove(`/workspaces/${encodeURIComponent(workspace)}`)
      const data = await get('/workspaces')
      setWorkspaces(data.items); setWorkspace(data.items[0]?.id || ''); setOverview(null); setFacts([]); setRelationships([]); setDocuments([]); setChanges([]); setReviews([]); setRuns([]); setNotice(`Deleted ${current.name}.`)
    } catch (error) { setNotice(error.message) }
  }

  const setSourceActive = async (document, active) => {
    const action = active ? 'restore' : 'remove'
    if (!active && !window.confirm(`Remove “${document.name}” from this workspace’s active knowledge? Its source record and audit history will be retained so it can be restored.`)) return
    try {
      await post(`/documents/${encodeURIComponent(document.id)}/${active ? 'reactivate' : 'archive'}`)
      if (selectedDocument?.id === document.id) { setSelectedDocument(null); setDocumentDetail(null) }
      await refresh(workspace)
      setNotice(active ? `Restored ${document.name} to the active knowledge layer.` : `Removed ${document.name} from active knowledge. Its audit record is retained.`)
    } catch (error) { setNotice(`Could not ${action} source: ${error.message}`) }
  }

  const navItems = [['overview', 'Briefing'], ['facts', 'Facts'], ['documents', 'Sources'], ['relationships', 'Relationships'], ['changes', 'Diff'], ['review', 'Review'], ['trust', 'Trust gate'], ['runs', 'Runs'], ['settings', 'Configure']]
  return <div className="app-shell">
    <header className="masthead">
      <button className="brand" onClick={() => setSection('overview')} aria-label="Open Project SuperJoin briefing"><span className="brand-mark" aria-hidden="true">SJ</span><span><strong>Project SuperJoin</strong><small>Evidence desk</small></span></button>
      <div className="issue-meta"><span>ACTIVE WORKSPACE</span>{workspace ? <div className="workspace-controls"><select value={workspace} onChange={(event) => setWorkspace(event.target.value)}>{workspaces.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select><button onClick={() => setShowWorkspaceForm((value) => !value)}>New</button><button className="delete-workspace" onClick={deleteWorkspace}>Delete</button></div> : <button className="new-workspace-link" onClick={() => setShowWorkspaceForm(true)}>Create workspace</button>}</div>
      <div className="edition-actions">{workspace && <label className="upload-button">＋ Upload PDFs<input aria-label="Upload PDFs" type="file" accept="application/pdf" multiple onChange={onUpload} /></label>}</div>
    </header>
    {showWorkspaceForm && <form className="workspace-create-bar" onSubmit={createWorkspace}><label>NEW WORKSPACE<input autoFocus value={newWorkspaceName} onChange={(event) => setNewWorkspaceName(event.target.value)} placeholder="e.g. Acme diligence" /></label><button className="upload-button" type="submit">Create workspace</button><button className="secondary-button" type="button" onClick={() => setShowWorkspaceForm(false)}>Cancel</button></form>}
    <nav className="edition-nav" aria-label="Workspace sections">{navItems.map(([key, label]) => <button aria-current={section === key ? 'page' : undefined} className={section === key ? 'nav-item active' : 'nav-item'} onClick={() => setSection(key)} key={key}>{label}{key === 'relationships' && relationships.length > 0 && <em>{relationships.length}</em>}</button>)}</nav>
    <div className="edition-status"><span>● Live production pipeline</span>{workspace && <span>Revision {overview?.workspace?.active_revision || 1}</span>}<span>{relationships.length} evidence relationships</span></div>
    <main className="main">
      <header className="page-folio"><span>FACT KNOWLEDGE LAYER</span><strong>{overview?.workspace?.name || 'No workspace'}</strong><button aria-label="Search facts" onClick={() => setSection('facts')}>Search the record ↗</button></header>
      {notice && <div className="notice" role="status" aria-live="polite">{notice}<button aria-label="Dismiss notice" onClick={() => setNotice('')}>×</button></div>}
      {!workspace && section !== 'settings' ? <EmptyWorkspace onCreate={() => setShowWorkspaceForm(true)} /> : loading ? <div className="loading"><div className="spinner" />Loading the evidence layer…</div> : <>
        {section === 'overview' && <Overview overview={overview} facts={facts} relationships={relationships} onRelationship={setSelectedRelationship} onOpenRelationships={() => setSection('relationships')} />}
        {section === 'facts' && <Facts facts={factResults} total={factTotal} statuses={factStatuses} status={factStatus} setStatus={setFactStatus} loading={factsLoading} query={query} setQuery={setQuery} onSelect={openFact} />}
        {section === 'documents' && <Documents documents={documents} onUpload={onUpload} selectedDocument={selectedDocument} onSelect={openDocument} onSetActive={setSourceActive} />}
        {section === 'relationships' && <Relationships relationships={relationships} selected={selectedRelationship} onSelect={setSelectedRelationship} />}
        {section === 'changes' && <Changes overview={overview} changes={changes} />}
        {section === 'runs' && <Runs runs={runs} onRefresh={() => refresh()} />}
        {section === 'review' && <Review workspace={workspace} reviews={reviews} facts={facts} onRefresh={() => refresh()} />}
        {section === 'trust' && <TrustGate workspace={workspace} facts={facts} />}
        {section === 'settings' && <Settings />}
      </>}
    </main>
    {(selectedFact || selectedRelationship || selectedDocument) && <Inspector fact={selectedFact} relationship={selectedRelationship} document={documentDetail || (selectedDocument ? { document: selectedDocument, pages: [] } : null)} documentLoading={documentLoading} onClose={() => { setSelectedFact(null); setSelectedRelationship(null); setSelectedDocument(null); setDocumentDetail(null) }} />}
  </div>
}

function EmptyWorkspace({ onCreate }) {
  return <div className="content empty-workspace"><span className="eyebrow green">REAL PIPELINE · EMPTY DATABASE</span><h2>No workspaces yet.</h2><p>Create a workspace, upload an actual PDF, and watch native parsing, extraction, grounding, schema resolution, relationship reasoning, and canonical publication run in sequence.</p><button className="upload-button" onClick={onCreate}>Create workspace</button><ol><li><strong>01</strong><span>Name the corpus you are investigating.</span></li><li><strong>02</strong><span>Upload any PDF from your own source library.</span></li><li><strong>03</strong><span>Inspect every published fact against its page evidence.</span></li></ol></div>
}

function Overview({ overview, relationships, onRelationship, onOpenRelationships }) {
  const statuses = overview?.statuses || {}
  const grounded = overview?.counts?.grounded_claims || 0
  const claims = overview?.counts?.claims || 0
  const coverage = claims ? Math.round((grounded / claims) * 100) : 0
  const relationTypes = overview?.relationship_types || {}
  return <div className="content"><section className="issue-cover"><div className="cover-copy"><span className="eyebrow green">EVIDENCE FIRST · REVISION {overview?.workspace?.active_revision || 1}</span><h2>Facts that can<br /><em>show their work.</em></h2><p>Project SuperJoin turns changing financial documents into an inspectable record of claims, context, conflicts, and time.</p></div><div className="revision-proof"><span>CURRENT EDITION</span><strong>{String(overview?.workspace?.active_revision || 1).padStart(2, '0')}</strong><p>Every published value keeps the sentence, page, parser, and reasoning that produced it.</p><div><b>PDFs</b><i>→</i><b>Claims</b><i>→</i><b>Facts</b></div></div></section><section className="stats-grid"><Stat label="Documents read" value={overview?.counts?.documents || 0} /><Stat label="Immutable claims" value={claims} /><Stat label="Fact families" value={overview?.counts?.facts || 0} accent /><Stat label="Relationships" value={overview?.counts?.relationships || 0} /></section><section className="overview-grid"><article className="panel knowledge-column"><div className="panel-heading"><div><span className="eyebrow">STATE OF THE RECORD</span><h3>What can be trusted today</h3></div><span className="revision-dot">● PUBLISHED</span></div><div className="health-list"><div><span className="health-dot good" />Supported <strong>{statuses.SUPPORTED || 0}</strong></div><div><span className="health-dot good" />Corroborated <strong>{statuses.CORROBORATED || 0}</strong></div><div><span className="health-dot bad" />Contested <strong>{statuses.CONTESTED || 0}</strong></div><div><span className="health-dot warn" />Needs review <strong>{statuses.UNRESOLVED || 0}</strong></div></div><div className="coverage"><span>Grounded evidence coverage</span><strong>{coverage}%</strong><div><i style={{ width: `${coverage}%` }} /></div></div></article><article className="panel cases-panel"><div className="panel-heading"><div><span className="eyebrow">RELATIONSHIP DESK</span><h3>What the evidence says together</h3></div><button className="link-button" onClick={onOpenRelationships}>Read all</button></div>{relationships.slice(0, 5).map((item, index) => <button className="case-row" onClick={() => onRelationship(item)} key={item.id}><span className="case-number">{String(index + 1).padStart(2, '0')}</span><span><strong>{item.relationship_type.toLowerCase()}</strong><small>{item.reason}</small></span><span className="read-arrow">↗</span></button>)}{!relationships.length && <div className="empty compact">Upload more documents to discover corroboration, contradiction, reconciliation, and supersedence.</div>}</article></section><section className="panel diff-panel"><div className="panel-heading"><div><span className="eyebrow">REVISION LEDGER</span><h3>The latest knowledge diff</h3></div><span className="mono">COMMITTED · AUDITABLE</span></div><div className="diff-cards"><div><strong>+ {claims}</strong><span>source claims</span></div><div><strong>{relationTypes.CORROBORATES || 0}</strong><span>corroborations</span></div><div><strong>{relationTypes.RECONCILES || 0}</strong><span>reconciliations</span></div><div><strong>{relationTypes.CONTRADICTS || 0}</strong><span>contradictions</span></div></div></section></div>
}

function Facts({ facts, total, statuses, status, setStatus, loading, query, setQuery, onSelect }) {
  const exportFacts = () => { const blob = new Blob([JSON.stringify(facts, null, 2)], { type: 'application/json' }); const url = URL.createObjectURL(blob); const link = document.createElement('a'); link.href = url; link.download = 'project-superjoin-facts.json'; link.click(); URL.revokeObjectURL(url) }
  const openRow = (fact) => onSelect(fact)
  const modality = (value) => ({ asserted: 'Reported', mandatory: 'Required', positive: 'Positive finding', negative: 'Negative finding', estimate: 'Estimated' }[String(value || '').toLowerCase()] || String(value || 'Unspecified').replaceAll('_', ' ').replace(/^./, (letter) => letter.toUpperCase()))
  return <div className="content"><div className="section-heading"><div><span className="eyebrow">CANONICAL KNOWLEDGE</span><h2>Facts</h2><p>Derived views stay linked to immutable source claims.</p></div><button className="secondary-button" onClick={exportFacts}>Export results ↓</button></div><div className="taxonomy-note"><strong>Statement type</strong> captures how the source frames a claim. <strong>Period</strong> is its reported fiscal or calendar context.</div><div className="toolbar"><div className="search"><span aria-hidden="true">⌕</span><input aria-label="Search all facts" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search subject, fact, value or evidence…" /></div><select className="status-filter" aria-label="Filter facts by status" value={status} onChange={(event) => setStatus(event.target.value)}><option value="">All statuses</option>{statuses.map((item) => <option key={item} value={item}>{item.replaceAll('_', ' ')}</option>)}</select><div className="toolbar-count" aria-live="polite">{loading ? 'Searching…' : `${total} result${total === 1 ? '' : 's'}`}</div></div><div className="table-card"><table><thead><tr><th scope="col">SUBJECT</th><th scope="col">FACT</th><th scope="col">VALUE</th><th scope="col" title="Fiscal or calendar context stated by the source">PERIOD ⓘ</th><th scope="col" title="How the source frames this statement">STATEMENT TYPE ⓘ</th><th scope="col">STATE</th><th scope="col">EVIDENCE</th></tr></thead><tbody>{facts.map((fact) => <tr tabIndex="0" role="button" aria-label={`Inspect ${fact.subject} ${fact.predicate}`} onClick={() => openRow(fact)} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); openRow(fact) } }} key={fact.id}><td><strong>{fact.subject}</strong></td><td><span className="predicate">{fact.predicate.replaceAll('_', ' ')}</span></td><td className="value-cell">{fact.display_value}</td><td className="mono">{fact.period || '—'}</td><td><span className="muted">{modality(fact.modality)}</span></td><td><Badge tone={fact.status === 'CONTESTED' ? 'bad' : fact.status === 'CORROBORATED' || fact.status === 'SUPPORTED' ? 'good' : fact.status === 'UNRESOLVED' ? 'warn' : 'neutral'}>{fact.status}</Badge></td><td><span className="source-count" aria-label="Inspect linked evidence">Open ↗</span></td></tr>)}</tbody></table>{facts.length === 0 && <div className="empty">No facts match the current search and status filter.</div>}</div>{total > facts.length && <p className="result-limit">Showing the newest {facts.length} of {total} matching facts. Refine the search to narrow the record.</p>}</div>
}

function Documents({ documents, onUpload, selectedDocument, onSelect, onSetActive }) {
  const active = documents.filter((document) => document.status !== 'archived')
  const archived = documents.filter((document) => document.status === 'archived')
  const SourceCard = ({ document, removed = false }) => <article className={`${selectedDocument?.id === document.id ? 'document-card selected' : 'document-card'}${removed ? ' archived' : ''}`}>
    <button className="document-inspect" onClick={() => onSelect(document)} aria-label={`Inspect ${document.name}`}>
      <div className="doc-icon" aria-hidden="true">PDF</div><div className="document-info"><strong>{document.name}</strong><span>{document.publisher || 'Publisher not detected'}</span><small>{document.page_count || 0} PDF pages · {document.parser || 'parser pending'} · {removed ? 'removed from active knowledge' : document.status === 'complete' ? 'parsed and active' : document.status}</small></div><Badge tone={removed ? 'neutral' : document.status === 'complete' ? 'good' : 'warn'}>{removed ? 'removed' : document.status}</Badge><span className="document-open" aria-hidden="true">Inspect →</span>
    </button>
    <div className="source-actions"><span>{removed ? 'Evidence retained for audit' : 'Included in canonical facts'}</span><button className={removed ? 'source-restore' : 'source-remove'} onClick={() => onSetActive(document, removed)}>{removed ? 'Restore source' : 'Remove from workspace'}</button></div>
  </article>
  return <div className="content"><div className="section-heading"><div><span className="eyebrow">SOURCE LIBRARY</span><h2>Sources</h2><p>Add PDFs to this workspace or remove them from active knowledge without losing the audit trail.</p></div><label className="secondary-button">＋ Add PDFs<input aria-label="Add PDFs" type="file" accept="application/pdf" multiple onChange={onUpload} /></label></div>{active.length ? <div className="document-grid">{active.map((document) => <SourceCard document={document} key={document.id} />)}</div> : <div className="panel empty-state source-empty"><h3>No active sources.</h3><p>Add one or several PDFs to start this workspace’s evidence record.</p><label className="upload-button">＋ Add first PDFs<input aria-label="Add first PDFs" type="file" accept="application/pdf" multiple onChange={onUpload} /></label></div>}{archived.length > 0 && <section className="removed-sources"><div><span className="eyebrow">REMOVED SOURCES</span><p>Excluded from current facts and Trust Gate decisions. Restore any source in one click.</p></div><div className="document-grid">{archived.map((document) => <SourceCard document={document} removed key={document.id} />)}</div></section>}</div>
}

function Relationships({ relationships, selected, onSelect }) {
  const summary = (item, side) => `${item[`subject_${side}`]} · ${item[`predicate_${side}`].replaceAll('_', ' ')} · ${item[`value_${side}`]}`
  return <div className="content"><div className="section-heading"><div><span className="eyebrow">EVIDENCE RELATIONSHIPS</span><h2>Reasoning</h2><p>Evidence is compared only after entity, concept, period, modality, and scope resolution.</p></div></div>{relationships.length ? <div className="case-grid">{relationships.map((item, index) => <button className={selected?.id === item.id ? 'case-card selected' : 'case-card'} onClick={() => onSelect(item)} key={item.id}><span className="case-number">{String(index + 1).padStart(2, '0')}</span><Badge tone={item.relationship_type === 'CONTRADICTS' ? 'bad' : item.relationship_type === 'RECONCILES' ? 'warn' : 'good'}>{item.relationship_type}</Badge><h3>{summary(item, 'a')}</h3><p className="relationship-versus">compared with</p><h4>{summary(item, 'b')}</h4><p>{item.reason}</p><div className="relationship-sources"><span>{item.document_a}</span><i>↔</i><span>{item.document_b}</span></div><div className="case-footer"><span>{Math.round(Number(item.confidence || 0) * 100)}% confidence</span><span>Inspect both sides →</span></div></button>)}</div> : <div className="panel empty-state"><h3>No relationships discovered.</h3><p>The current grounded claims do not yet share a resolved fact lane. Add another disclosure with overlapping facts; unrelated claims remain separate by design.</p></div>}</div>
}

function Changes({ overview, changes }) {
  const [selected, setSelected] = useState(null)
  const symbol = (kind) => kind.includes('conflict') ? ['!', 'conflict'] : kind.includes('reconcile') ? ['↻', 'reconcile'] : ['+', 'plus']
  return <div className="content"><div className="section-heading"><div><span className="eyebrow">REVISION HISTORY</span><h2>Knowledge Diff</h2><p>Every change is tied to its source, run, revision, and recorded time.</p></div></div><div className="diff-legend" aria-label="Change legend"><span><i className="change-symbol plus">+</i> Added fact</span><span><i className="change-symbol conflict">!</i> Conflict</span><span><i className="change-symbol reconcile">↻</i> Reconciled context</span></div><div className="diff-layout"><div className="panel diff-detail"><div className="diff-banner"><span className="revision-dot">●</span><div><strong>Committed knowledge revision</strong><span>Revision {overview?.workspace?.active_revision || 1} · {changes.length} recorded changes</span></div></div>{changes.length ? changes.map((change) => { const [icon, tone] = symbol(change.kind); return <button className={`change-line${selected?.id === change.id ? ' selected' : ''}`} onClick={() => setSelected(change)} key={change.id}><span className={`change-symbol ${tone}`}>{icon}</span><div><strong>{change.summary}</strong><small>{change.kind.replaceAll('_', ' ')} · {new Date(change.created_at).toLocaleString()}</small></div><b>View →</b></button> }) : <div className="empty">No knowledge changes have been published yet.</div>}</div>{selected && <aside className="panel change-detail"><span className="eyebrow">CHANGE RECORD</span><h3>{selected.summary}</h3><dl><dt>Type</dt><dd>{selected.kind.replaceAll('_', ' ')}</dd><dt>Source</dt><dd>{selected.document_name || 'No source document recorded'}</dd><dt>Run</dt><dd className="mono">{selected.run_id || 'System event'}</dd><dt>Revision</dt><dd>{selected.details?.knowledge_revision || overview?.workspace?.active_revision || '—'}</dd><dt>Recorded</dt><dd>{new Date(selected.created_at).toLocaleString()}</dd>{selected.details?.period && <><dt>Period</dt><dd>{selected.details.period}</dd></>}{selected.details?.raw_value && <><dt>New source value</dt><dd>{selected.details.raw_value}</dd></>}</dl><details><summary>Identifiers and raw detail</summary><pre>{JSON.stringify(selected.details || {}, null, 2)}</pre></details></aside>}</div></div>
}

function Runs({ runs, onRefresh }) {
  const [expandedRunId, setExpandedRunId] = useState(null)
  const [callsByRun, setCallsByRun] = useState({})
  const [stagesByRun, setStagesByRun] = useState({})
  const [loadingRunId, setLoadingRunId] = useState(null)
  const [telemetryError, setTelemetryError] = useState('')
  const act = async (run, path) => { try { await post(`/runs/${run.id}/${path}`); onRefresh() } catch (error) { /* the app-level notice remains available for the next refresh */ onRefresh() } }
  const inspectTelemetry = async (run) => {
    if (expandedRunId === run.id) { setExpandedRunId(null); return }
    setExpandedRunId(run.id); setTelemetryError('')
    setLoadingRunId(run.id)
    try {
      const [callData, stageData] = await Promise.all([get(`/runs/${run.id}/model-calls`), get(`/runs/${run.id}/stages`)])
      setCallsByRun((current) => ({ ...current, [run.id]: callData.items || [] }))
      setStagesByRun((current) => ({ ...current, [run.id]: stageData.items || [] }))
    } catch (error) { setTelemetryError(error.message || 'Unable to load model telemetry') } finally { setLoadingRunId(null) }
  }
  useEffect(() => {
    if (!expandedRunId) return undefined
    const expanded = runs.find((run) => run.id === expandedRunId)
    if (!expanded || !['queued', 'processing', 'cancel_requested'].includes(expanded.status)) return undefined
    const timer = window.setInterval(async () => {
      try {
        const [callData, stageData] = await Promise.all([get(`/runs/${expandedRunId}/model-calls`), get(`/runs/${expandedRunId}/stages`)])
        setCallsByRun((current) => ({ ...current, [expandedRunId]: callData.items || [] }))
        setStagesByRun((current) => ({ ...current, [expandedRunId]: stageData.items || [] }))
      } catch (error) { setTelemetryError(error.message || 'Unable to refresh telemetry') }
    }, 1500)
    return () => window.clearInterval(timer)
  }, [expandedRunId, runs])
  const calls = expandedRunId ? (callsByRun[expandedRunId] || []) : []
  const stages = expandedRunId ? (stagesByRun[expandedRunId] || []) : []
  const spend = calls.reduce((total, call) => total + Number(call.estimated_cost || 0), 0)
  const cacheHits = calls.reduce((total, call) => total + Number(call.cache_hit || 0), 0)
  return <div className="content"><div className="section-heading"><div><span className="eyebrow">OBSERVABILITY</span><h2>Runs</h2><p>Live parser, extraction, schema, relationship, and publication progress.</p></div></div><div className="panel run-list">{runs.length ? runs.map((run) => <React.Fragment key={run.id}><div className="run-row"><div><strong>{run.mode === 'retry' ? 'Retried ingestion' : 'PDF ingestion'}</strong><small>{run.message || 'Queued'}</small><time>{new Date(run.updated_at).toLocaleString()}</time></div><div className="run-progress"><Badge tone={run.status === 'complete' ? 'good' : run.status === 'failed' ? 'bad' : run.status === 'cancelled' ? 'neutral' : 'warn'}>{run.status}</Badge><span>{run.progress}%</span><i aria-hidden="true"><b style={{ width: `${run.progress || 0}%` }} /></i><div className="run-actions">{['queued', 'processing'].includes(run.status) && <button className="text-button" onClick={() => act(run, 'cancel')}>Cancel</button>}{['failed', 'cancelled'].includes(run.status) && <button className="text-button" onClick={() => act(run, 'resume')}>Retry run</button>}<button className="text-button" aria-expanded={expandedRunId === run.id} onClick={() => inspectTelemetry(run)}>{expandedRunId === run.id ? 'Hide telemetry' : 'Inspect telemetry'}</button></div></div></div>{expandedRunId === run.id && <div className="run-telemetry" role="region" aria-label={`Model telemetry for ${run.id}`}>{loadingRunId === run.id ? <div className="empty">Loading current telemetry…</div> : telemetryError ? <div className="empty">{telemetryError}</div> : <><div className="telemetry-summary"><span><strong>{calls.length}</strong> calls</span><span><strong>${spend.toFixed(4)}</strong> spend</span><span><strong>{cacheHits}</strong> cache hits</span><span><strong>{stages.length}</strong> stages</span></div>{stages.length > 0 && <div className="stage-strip">{stages.map((stage) => <div key={stage.stage}><span>{stage.stage.replaceAll('_', ' ')}</span><strong>{stage.current_count}/{stage.total_count || '—'}</strong><small>{stage.duration_ms == null ? 'active' : `${stage.duration_ms} ms`}</small></div>)}</div>}{calls.length ? <table><thead><tr><th scope="col">ROLE</th><th scope="col">MODEL</th><th scope="col">STATUS</th><th scope="col">TOKENS IN / OUT</th><th scope="col">LATENCY</th><th scope="col">ATTEMPTS</th><th scope="col">COST</th></tr></thead><tbody>{calls.map((call) => <tr key={call.id}><td>{call.role}</td><td className="mono">{call.model || '—'}</td><td><Badge tone={call.status === 'complete' ? 'good' : call.status === 'failed' ? 'bad' : 'warn'}>{call.status}</Badge></td><td className="mono">{call.input_tokens || 0} / {call.output_tokens || 0}</td><td className="mono">{call.latency_ms == null ? '—' : `${call.latency_ms} ms`}</td><td className="mono">{call.attempts || 1}</td><td className="mono">${Number(call.estimated_cost || 0).toFixed(4)}</td></tr>)}</tbody></table> : <div className="empty compact">No model calls were needed or recorded for this run.</div>}</>}</div>}</React.Fragment>) : <div className="empty">No runs recorded for this workspace yet.</div>}</div></div>
}

function Settings() {
  const [settings, setSettings] = useState(null)
  const [activeRole, setActiveRole] = useState('extraction')
  const [drafts, setDrafts] = useState({})
  const [status, setStatus] = useState('')
  const [saving, setSaving] = useState(false)
  const [copyOpen, setCopyOpen] = useState(false)
  const [copyTargets, setCopyTargets] = useState([])
  const [copyModel, setCopyModel] = useState(false)
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
  const loadSettings = () => {
    setStatus('')
    get('/settings').then(hydrate).catch((error) => setStatus(error.message || 'Settings could not be loaded.'))
  }
  useEffect(loadSettings, [])
  if (!settings) return <div className="content"><div className="section-heading"><div><span className="eyebrow">RUNTIME CONFIGURATION</span><h2>Provider desk</h2><p>Configure each OpenAI-compatible role independently.</p></div></div><div className="panel settings-loading" role="status">{status ? <><h3>Provider settings are unavailable.</h3><p>{status}</p><button className="secondary-button" onClick={loadSettings}>Retry</button></> : <><div className="spinner" /><span>Loading the active provider contract…</span></>}</div></div>
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
  const openProviderCopy = () => {
    setCopyTargets(activeRole === 'extraction' ? ['reasoning'] : activeRole === 'reasoning' ? ['extraction'] : [])
    setCopyModel(false); setCopyOpen((value) => !value); setStatus('')
  }
  const toggleCopyTarget = (role) => setCopyTargets((current) => current.includes(role) ? current.filter((item) => item !== role) : [...current, role])
  const applyProviderCopy = async () => {
    if (!copyTargets.length) return setStatus('Choose at least one compatible target role.')
    setSaving(true); setStatus('')
    try {
      hydrate(await post('/settings/actions/copy-provider', { source_role: activeRole, target_roles: copyTargets, copy_model: copyModel }))
      setStatus(`Copied ${activeRole} endpoint and authentication to ${copyTargets.join(', ')}. Role-specific paths and capability settings were preserved.`)
      setCopyOpen(false)
    } catch (error) { setStatus(error.message) } finally { setSaving(false) }
  }
  return <div className="content"><div className="section-heading"><div><span className="eyebrow">RUNTIME CONFIGURATION</span><h2>Provider desk</h2><p>Configure each OpenAI-compatible role independently. Changes last until this container restarts.</p></div></div><div className="provider-tabs" role="tablist">{roleCards.map(([key, label]) => { const role = settings?.roles?.[key]; return <button key={key} role="tab" aria-selected={activeRole === key} className={activeRole === key ? 'provider-tab active' : 'provider-tab'} onClick={() => { setActiveRole(key); setStatus(''); setCopyOpen(false) }}><span>{label}</span><Badge tone={role?.configured ? 'good' : 'warn'}>{role?.configured ? 'ready' : 'offline'}</Badge><small>{role?.model || 'No model'}</small></button> })}</div><form className="provider-editor" onSubmit={save}><div className="provider-editor-head"><div><span className="eyebrow">{activeRole.toUpperCase()} ROLE</span><h3>Connection contract</h3></div><div className="provider-head-actions"><select aria-label="Provider preset" defaultValue="" onChange={(event) => applyPreset(event.target.value)}><option value="" disabled>Choose a preset…</option>{settings?.presets?.map((preset) => <option value={preset.id} key={preset.id}>{preset.label}</option>)}</select><button className="secondary-button" type="button" onClick={openProviderCopy}>Use this provider for…</button></div></div>{copyOpen && <div className="provider-copy"><div><strong>Share {activeRole} provider connection</strong><p>Copy the endpoint and authentication only. Each target keeps its request path, limits, and capability options.</p></div><div className="provider-copy-targets">{roleCards.filter(([key]) => key !== activeRole).map(([key, label]) => <label className="checkbox" key={key}><input type="checkbox" checked={copyTargets.includes(key)} onChange={() => toggleCopyTarget(key)} /> {label}</label>)}<label className="checkbox"><input type="checkbox" checked={copyModel} onChange={(event) => setCopyModel(event.target.checked)} /> Also copy model name</label></div><div className="provider-copy-actions"><button className="secondary-button" type="button" onClick={() => setCopyOpen(false)}>Cancel</button><button className="upload-button" type="button" disabled={saving || !copyTargets.length} onClick={applyProviderCopy}>Apply to selected roles</button></div></div>}<div className="provider-fields"><label className="wide">BASE URL<input value={draft.base_url || ''} onChange={(event) => change('base_url', event.target.value)} placeholder="https://provider.example/v1" /></label><label>MODEL<input value={draft.model || ''} onChange={(event) => change('model', event.target.value)} placeholder="Any provider model name" /></label><label>API KEY<input type="password" autoComplete="new-password" value={draft.api_key || ''} onChange={(event) => change('api_key', event.target.value)} placeholder={settings?.roles?.[activeRole]?.key_configured ? 'Configured · enter to replace' : 'Optional for local endpoints'} /></label><label className="wide">REQUEST PATH<input value={draft.path || ''} onChange={(event) => change('path', event.target.value)} placeholder={activeRole === 'embeddings' ? '/embeddings' : '/chat/completions'} /></label><label>TIMEOUT · SECONDS<input type="number" min="1" max="600" value={draft.timeout_seconds || 90} onChange={(event) => change('timeout_seconds', Number(event.target.value))} /></label><label>CONCURRENCY<input type="number" min="1" max="64" value={draft.concurrency || 1} onChange={(event) => change('concurrency', Number(event.target.value))} /></label>{activeRole === 'embeddings' ? <><label>DIMENSIONS<input type="number" min="1" value={draft.dimensions || 768} onChange={(event) => change('dimensions', Number(event.target.value))} /></label><label>TASK TYPE<input value={draft.task_type || ''} onChange={(event) => change('task_type', event.target.value)} /></label></> : <><label>OUTPUT TOKEN LIMIT<input type="number" min="1" value={draft.max_output_tokens || 1200} onChange={(event) => change('max_output_tokens', Number(event.target.value))} /></label><label>STRUCTURED OUTPUT<select value={draft.structured_output_mode || 'none'} onChange={(event) => change('structured_output_mode', event.target.value)}><option value="json_object">JSON object</option><option value="json_schema">JSON schema</option><option value="none">None</option></select></label></>}<label>AUTH HEADER<input value={draft.auth_header || ''} onChange={(event) => change('auth_header', event.target.value)} /></label><label>AUTH SCHEME<input value={draft.auth_scheme ?? ''} onChange={(event) => change('auth_scheme', event.target.value)} placeholder="Bearer or blank" /></label><label className="wide">EXTRA REQUEST BODY · JSON<input value={draft.extra_body_json || ''} onChange={(event) => change('extra_body_json', event.target.value)} placeholder='{"thinking":{"type":"disabled"}}' /></label></div><div className="provider-controls"><label className="checkbox"><input type="checkbox" checked={draft.send_model ?? true} onChange={(event) => change('send_model', event.target.checked)} /> Send model field</label>{activeRole === 'embeddings' && <label className="checkbox"><input type="checkbox" checked={draft.include_dimensions ?? true} onChange={(event) => change('include_dimensions', event.target.checked)} /> Send dimensions</label>}<label className="checkbox danger"><input type="checkbox" checked={draft.clear_api_key || false} onChange={(event) => change('clear_api_key', event.target.checked)} /> Clear saved runtime key</label><div className="provider-actions"><button type="button" className="secondary-button" disabled={saving} onClick={testConnection}>Test connection</button><button className="upload-button" disabled={saving} type="submit">{saving ? 'Working…' : 'Apply settings'}</button></div></div>{status && <p className="provider-status" role="status">{status}</p>}</form><div className="settings-ledger"><div><span>Parser</span><strong>{settings?.parser?.backend || 'liteparse'} · {settings?.parser?.local_ocr_enabled ? 'selective local OCR' : 'native only'}</strong></div><div><span>Budget remaining</span><strong>${settings?.budget?.remaining_usd?.toFixed?.(4) || '20.0000'}</strong></div><div><span>Retry policy</span><strong>{settings?.provider_retry?.attempts || 1} attempts · {settings?.provider_retry?.backoff_seconds || 0}s backoff</strong></div><p>API keys stay in process memory, are never returned by the API, and disappear when the container restarts. Remote endpoints require HTTPS; local HTTP is restricted to localhost.</p></div></div>
}

function Review({ workspace, reviews, facts, onRefresh }) {
  const reviewFacts = facts.filter((fact) => ['CONTESTED', 'UNRESOLVED'].includes(fact.status))
  const [factId, setFactId] = useState(reviewFacts[0]?.id || '')
  const [action, setAction] = useState('keep_unresolved')
  const [rationale, setRationale] = useState('')
  const [notice, setNotice] = useState('')
  useEffect(() => { if (!reviewFacts.some((fact) => fact.id === factId)) setFactId(reviewFacts[0]?.id || '') }, [facts, factId])
  const submit = async (event) => { event.preventDefault(); if (!factId || !rationale.trim()) return setNotice('Choose a fact and provide a rationale.'); try { await post('/reviews', { workspace_id: workspace, fact_id: factId, action, rationale }); setNotice('Immutable review recorded.'); setRationale(''); onRefresh() } catch (error) { setNotice(error.message) } }
  const revoke = async (review) => { if (!window.confirm('Revoke this active decision? The audit record will remain.')) return; const reason = window.prompt('Optional revocation rationale:', 'Decision no longer applies.') || 'Decision revoked by reviewer.'; try { await post('/reviews', { workspace_id: workspace, fact_id: review.fact_id, action: 'revoke', rationale: reason, revokes_review_id: review.id }); setNotice('Decision revoked; audit history retained.'); onRefresh() } catch (error) { setNotice(error.message) } }
  const actionLabel = (value) => ({ keep_unresolved: 'Keep unresolved', prefer: 'Prefer source for this use', select: 'Select this value', confirm_context: 'Confirm contextual distinction', revoke: 'Revoke decision' }[value] || value.replaceAll('_', ' '))
  return <div className="content narrow-content"><div className="section-heading"><div><span className="eyebrow">HUMAN REVIEW</span><h2>Review queue</h2><p>Only contested or unresolved facts need a decision. Source claims remain immutable.</p></div></div>{reviewFacts.length ? <div className="review-queue">{reviewFacts.map((fact) => <button className={fact.id === factId ? 'review-item selected' : 'review-item'} onClick={() => setFactId(fact.id)} key={fact.id}><Badge tone={fact.status === 'CONTESTED' ? 'bad' : 'warn'}>{fact.status}</Badge><div><strong>{fact.subject} · {fact.predicate.replaceAll('_', ' ')}</strong><span>{fact.period || 'No period'} · {fact.display_value}</span><small>{fact.status === 'CONTESTED' ? 'Conflicting grounded sources require a choice or explicit abstention.' : fact.reason}</small></div></button>)}</div> : <div className="panel empty-state"><h3>No facts currently require human review.</h3><p>Supported facts remain available in the Facts record and Trust Gate.</p></div>}<div className={`review-layout${reviewFacts.length ? '' : ' ledger-only'}`}>{reviewFacts.length > 0 && <form className="panel review-form" onSubmit={submit}><span className="eyebrow">RECORD DECISION</span><label>ACTION<select value={action} onChange={(event) => setAction(event.target.value)}><option value="keep_unresolved">Keep unresolved</option><option value="prefer">Prefer this source for a named use</option><option value="confirm_context">Confirm contextual distinction</option></select></label><p className="field-help">A decision applies to the current fact revision. Later evidence makes it stale automatically.</p><label>RATIONALE<textarea value={rationale} onChange={(event) => setRationale(event.target.value)} placeholder="Explain the use, source preference, or contextual distinction." rows="5" /></label><button className="upload-button" type="submit">Record auditable decision</button>{notice && <p className="form-notice">{notice}</p>}</form>}<div className="panel decision-ledger"><span className="eyebrow">DECISION LEDGER</span>{reviews.length ? reviews.map((review) => <div className="review-row" key={review.id}><Badge tone={review.stale ? 'warn' : review.status === 'revoked' ? 'neutral' : 'good'}>{review.stale ? 'stale' : review.status}</Badge><div><strong>{actionLabel(review.action)}</strong><small>{review.rationale}</small><span className="mono">Based on fact revision {review.based_on_revision}</span></div>{review.status === 'active' && !review.stale && <button className="revoke-button" onClick={() => revoke(review)}>Revoke decision</button>}</div>) : <div className="empty">No review decisions have been recorded.</div>}</div></div></div>
}

function TrustGate({ workspace, facts }) {
  const [factId, setFactId] = useState('')
  const [subject, setSubject] = useState('')
  const [predicate, setPredicate] = useState('')
  const [period, setPeriod] = useState('')
  const [policy, setPolicy] = useState('strict')
  const [result, setResult] = useState(null)
  useEffect(() => {
    const firstFact = facts.find((fact) => fact.subject && fact.predicate)
    setFactId(firstFact?.id || '')
    setSubject(firstFact?.subject || '')
    setPredicate(firstFact?.predicate || '')
    setPeriod(firstFact?.period || '')
    setResult(null)
  }, [workspace, facts])
  const chooseFact = (id) => { const fact = facts.find((item) => item.id === id); setFactId(id); setSubject(fact?.subject || ''); setPredicate(fact?.predicate || ''); setPeriod(fact?.period || ''); setResult(null) }
  const run = async (event) => { event.preventDefault(); try { setResult(await post('/resolve', { workspace_id: workspace, subject, predicate, period, policy })) } catch (error) { setResult({ error: error.message }) } }
  return <div className="content narrow-content"><div className="section-heading"><div><span className="eyebrow">MACHINE CONSUMPTION</span><h2>Trust Gate</h2><p>Trust Gate decides whether a canonical fact is safe for downstream automation to consume.</p></div></div><div className="trust-layout"><form className="panel trust-form" onSubmit={run}><label>SELECT A CANONICAL FACT<select value={factId} onChange={(event) => chooseFact(event.target.value)}><option value="">Choose a fact…</option>{facts.map((fact) => <option value={fact.id} key={fact.id}>{fact.subject} · {fact.predicate.replaceAll('_', ' ')} · {fact.period || 'no period'}</option>)}</select></label>{factId && <div className="selected-fact"><span>{subject}</span><strong>{predicate.replaceAll('_', ' ')}</strong><b>{period || 'No period'} · {facts.find((fact) => fact.id === factId)?.display_value}</b></div>}<label>RESOLUTION POLICY<select value={policy} onChange={(event) => setPolicy(event.target.value)}><option value="strict">Strict evidence only</option><option value="human_preference">Allow active human preference</option></select></label><p className="field-help">{policy === 'strict' ? 'Returns a value only when current grounded evidence safely supports one.' : 'An active review decision may resolve an otherwise ambiguous fact.'}</p><button className="upload-button" type="submit" disabled={!factId}>Resolve selected fact</button></form><div className="panel gate-result">{result ? result.error ? <div className="failure-box"><h3>Request failed</h3><p>{result.error}</p></div> : <><Badge tone={result.safe_to_use ? 'good' : result.decision === 'needs_context' || result.decision === 'needs_review' ? 'warn' : 'bad'}>{result.safe_to_use ? 'ALLOW' : result.decision?.replaceAll('_', ' ')}</Badge><h3>{result.safe_to_use ? result.display_value : 'Automation blocked'}</h3><p>{(result.reason_codes || []).map((code) => code.replaceAll('_', ' ').toLowerCase()).join(' · ')}</p>{result.safe_to_use && <div className="gate-proof"><span>Executable value</span><strong>{result.normalized_value || result.display_value}</strong></div>}{result.alternatives?.length > 0 && <div className="gate-alternatives"><strong>Alternatives requiring context</strong>{result.alternatives.slice(0, 5).map((item, index) => <span key={item.id || index}>{item.display_value || item.normalized_value} · {item.period || 'no period'}</span>)}</div>}<details><summary>View API response</summary><pre>{JSON.stringify(result, null, 2)}</pre></details></> : <div className="empty">Choose a fact and resolve it to see an allow, block, context, or review decision.</div>}</div></div></div>
}

function Inspector({ fact, relationship, document, documentLoading, onClose }) {
  const factTone = fact?.fact.status === 'CONTESTED' ? 'bad' : fact?.fact.status === 'UNRESOLVED' ? 'warn' : 'good'
  const relationSummary = (side) => <div className="relationship-side"><span>{relationship[`document_${side}`] || 'Source document'}</span><strong>{relationship[`subject_${side}`]} · {String(relationship[`predicate_${side}`] || '').replaceAll('_', ' ')}</strong><b>{relationship[`value_${side}`]} · {relationship[`period_${side}`] || 'no period'} · {relationship[`modality_${side}`] || 'unspecified'}</b><small className="mono">{relationship[`claim_${side}`]}</small></div>
  return <aside className="inspector" aria-label="Evidence inspector"><div className="inspector-top"><span className="eyebrow">EVIDENCE INSPECTOR</span><button className="close-button" aria-label="Close evidence inspector" onClick={onClose}>×</button></div>{fact ? <><Badge tone={factTone}>{fact.fact.status}</Badge><h2>{fact.fact.predicate.replaceAll('_', ' ')}</h2><p className="fact-subject">{fact.fact.subject}</p><div className="inspector-value">{fact.fact.display_value}</div><div className="inspector-meta">Period: {fact.fact.period || 'unspecified'} · Statement type: {fact.fact.modality || 'unspecified'} · Scope: {fact.fact.scope || 'unspecified'}</div><div className="why-state"><strong>Why this state</strong><p>{fact.fact.reason}</p></div><div className="inspector-rule" /><h4>SOURCE EVIDENCE · {fact.anchors?.length || 0}</h4>{(fact.anchors || []).map((anchor) => <div className="evidence-block" key={`${anchor.id}-${anchor.claim_id}`}><div><strong>{anchor.document_name || 'Source document'}</strong><span>{anchor.publisher || 'Publisher not detected'} · PDF p.{anchor.pdf_page}{anchor.printed_page ? ` · printed p.${anchor.printed_page}` : ''}</span></div><p>“{anchor.text}”</p><div className="evidence-status"><Badge tone={anchor.grounding_status === 'grounded' ? 'good' : 'warn'}>{anchor.grounding_status}</Badge><span>{anchor.precision} · {anchor.parser || 'parser unrecorded'}</span></div>{anchor.pdf_url && <a className="document-source-link" href={anchor.pdf_url} target="_blank" rel="noreferrer">Open PDF at page {anchor.pdf_page} ↗</a>}<small className="mono">Claim {anchor.claim_id}</small></div>)}{!fact.anchors?.length && <div className="failure-box"><strong>Evidence unavailable</strong><p>{fact.evidence_unavailable_reason || 'No usable anchor is linked to this published fact.'}</p></div>}<div className="inspector-rule" /><h4>NORMALIZED INTERPRETATION</h4>{fact.interpretations?.slice(0, 6).map((interpretation) => <div className="interpretation-card" key={interpretation.id}><div><span>Concept</span><strong>{interpretation.predicate.replaceAll('_', ' ')}</strong></div><div><span>Normalized value</span><strong>{interpretation.normalized_value || 'Text claim'}</strong></div><div><span>Eligibility</span><strong>{interpretation.eligibility}</strong></div></div>)}{fact.relationships?.length > 0 && <><h4>RELATED EVIDENCE</h4>{fact.relationships.map((entry) => <div className="relation-chip" key={entry.id}><Badge tone={entry.relationship_type === 'CONTRADICTS' ? 'bad' : entry.relationship_type === 'RECONCILES' ? 'warn' : 'good'}>{entry.relationship_type}</Badge><span>{entry.reason}</span></div>)}</>}</> : relationship ? <><Badge tone={relationship.relationship_type === 'CONTRADICTS' ? 'bad' : relationship.relationship_type === 'RECONCILES' ? 'warn' : 'good'}>{relationship.relationship_type}</Badge><h2>{relationship.relationship_type.toLowerCase().replaceAll('_', ' ')}</h2><p className="case-description">{relationship.reason}</p><div className="inspector-rule" /><h4>EVIDENCE COMPARED</h4><div className="relationship-pair">{relationSummary('a')}<span className="pair-divider">compared with</span>{relationSummary('b')}</div><h4>COMPARISON DIMENSIONS</h4><div className="dimension-list">{Object.entries(relationship.dimensions || {}).map(([key, value]) => <div key={key}><span>{key.replaceAll('_', ' ')}</span><strong>{String(value)}</strong></div>)}</div><p className="confidence-note">Relationship confidence: {Math.round(Number(relationship.confidence || 0) * 100)}%</p></> : document ? <DocumentInspector document={document} loading={documentLoading} /> : null}</aside>
}

function DocumentInspector({ document, loading }) {
  const pages = document.pages || []
  const sourceHref = document.document.stored_path ? `${API}/documents/${encodeURIComponent(document.document.id)}/file` : document.document.source_url
  const parseFlags = (page) => Array.isArray(page.quality_flags) ? page.quality_flags : []
  const pageHref = (page) => sourceHref ? `${sourceHref}${sourceHref.includes('#') ? '&' : '#'}page=${encodeURIComponent(page.page_number)}` : ''
  return <>{loading ? <div className="empty">Loading document evidence…</div> : <><Badge tone={document.document.status === 'complete' ? 'good' : 'warn'}>{document.document.status}</Badge><h2 className="document-inspector-title">{document.document.name}</h2><div className="inspector-meta">{document.document.publisher} · {document.document.page_count || pages.length} PDF pages</div>{sourceHref && <a className="document-source-link" href={sourceHref} target="_blank" rel="noreferrer">Open original PDF ↗</a>}<div className="inspector-rule" /><h4>PARSE ARTIFACT</h4><div className="document-metadata"><div><span>Parser</span><strong>{document.document.parser || 'pending'}</strong></div><div><span>Quality score</span><strong>{document.document.quality_score == null ? '—' : Number(document.document.quality_score).toFixed(2)}</strong></div><div><span>Publication</span><strong>{document.document.published_at || '—'}</strong></div></div><h4 className="document-pages-heading">PAGE MAP</h4>{pages.length ? <div className="page-list">{pages.map((page) => { const flags = parseFlags(page); return <div className="page-row" key={page.id}><div><strong>PDF p.{page.page_number}</strong><span>Printed p.{page.printed_label || '—'} · {page.parser}</span></div><div className="page-status"><Badge tone={page.disposition === 'native' ? 'good' : page.disposition === 'visual' ? 'warn' : 'neutral'}>{page.disposition}</Badge><small>{page.native_text?.length || 0} native chars{flags.length ? ` · ${flags.join(', ')}` : ''}</small>{pageHref(page) && <a className="page-link" href={pageHref(page)} target="_blank" rel="noreferrer">Open page ↗</a>}</div></div> })}</div> : <div className="empty">No page artifacts recorded yet.</div>}</>}</>
}

createRoot(document.getElementById('root')).render(<App />)
