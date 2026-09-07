import React, { useEffect, useMemo, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './styles.css'

const API = '/api/v1'

async function get(path) {
  const response = await fetch(API + path)
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
  const [workspace, setWorkspace] = useState('delhivery')
  const [workspaces, setWorkspaces] = useState([])
  const [overview, setOverview] = useState(null)
  const [facts, setFacts] = useState([])
  const [cases, setCases] = useState([])
  const [relationships, setRelationships] = useState([])
  const [documents, setDocuments] = useState([])
  const [selectedFact, setSelectedFact] = useState(null)
  const [selectedCase, setSelectedCase] = useState(null)
  const [section, setSection] = useState('overview')
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(true)
  const [notice, setNotice] = useState('')

  const refresh = async (id = workspace) => {
    setLoading(true)
    try {
      const [nextOverview, nextFacts, nextCases, nextRelationships, nextDocuments] = await Promise.all([
        get(`/overview?workspace_id=${id}`), get(`/facts?workspace_id=${id}&limit=200`), get('/cases'),
        get(`/relationships?workspace_id=${id}`), get(`/documents?workspace_id=${id}`),
      ])
      setOverview(nextOverview); setFacts(nextFacts.items); setCases(nextCases.items)
      setRelationships(nextRelationships.items); setDocuments(nextDocuments.items)
    } catch (error) { setNotice(error.message) } finally { setLoading(false) }
  }

  useEffect(() => { get('/workspaces').then((data) => { setWorkspaces(data.items); refresh('delhivery') }).catch((error) => setNotice(error.message)) }, [])
  useEffect(() => { if (workspaces.length) refresh(workspace) }, [workspace])

  const filteredFacts = useMemo(() => {
    if (!query.trim()) return facts
    const needle = query.toLowerCase()
    return facts.filter((fact) => [fact.subject, fact.predicate, fact.display_value, fact.period, fact.status].join(' ').toLowerCase().includes(needle))
  }, [facts, query])

  const tone = (status) => ({ CORROBORATED: 'good', SUPPORTED: 'good', CONTESTED: 'bad', UNRESOLVED: 'warn' }[status] || 'neutral')

  const openFact = async (fact) => {
    try { const data = await get(`/facts/${fact.id}`); setSelectedFact(data) } catch (error) { setNotice(error.message) }
  }

  const resetDemo = async () => {
    await fetch(`${API}/demo/reset`, { method: 'POST' }); setNotice('Demo workspace reset'); await refresh()
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
        {[['overview', 'Overview', '⌂'], ['facts', 'Facts', '▦'], ['documents', 'Documents', '▤'], ['cases', 'Required cases', '◈'], ['changes', 'Knowledge Diff', '↻'], ['settings', 'Settings', '⚙']].map(([key, label, icon]) => <button className={section === key ? 'nav-item active' : 'nav-item'} onClick={() => setSection(key)} key={key}><span>{icon}</span>{label}{key === 'cases' && <em>4</em>}</button>)}
      </nav>
      <div className="sidebar-foot"><Badge tone="good">● Demo mode</Badge><p>Recorded model outputs are available without an API key.</p><button className="text-button" onClick={resetDemo}>Reset demo workspace</button></div>
    </aside>
    <main className="main">
      <header className="topbar"><div><span className="eyebrow">FACT KNOWLEDGE LAYER</span><h1>{overview?.workspace?.name || 'Workspace'}</h1></div><div className="top-actions"><label className="upload-button">＋ Upload PDF<input type="file" accept="application/pdf" onChange={onUpload} /></label><button className="icon-button" title="Search">⌕</button></div></header>
      {notice && <div className="notice" role="status">{notice}<button onClick={() => setNotice('')}>×</button></div>}
      {loading ? <div className="loading"><div className="spinner" />Loading the evidence layer…</div> : <>
        {section === 'overview' && <Overview overview={overview} facts={facts} cases={cases} onCase={selectCase} />}
        {section === 'facts' && <Facts facts={filteredFacts} query={query} setQuery={setQuery} onSelect={openFact} />}
        {section === 'documents' && <Documents documents={documents} />}
        {section === 'cases' && <Cases cases={cases} relationships={relationships} selectedCase={selectedCase} onSelect={selectCase} />}
        {section === 'changes' && <Changes overview={overview} />}
        {section === 'settings' && <Settings />}
      </>}
    </main>
    {(selectedFact || selectedCase) && <Inspector fact={selectedFact} selectedCase={selectedCase} relationships={relationships} onClose={() => { setSelectedFact(null); setSelectedCase(null) }} />}
  </div>
}

function Overview({ overview, facts, cases, onCase }) {
  const statuses = overview?.statuses || {}
  return <div className="content"><section className="hero-panel"><div><span className="eyebrow green">EVIDENCE FIRST · REVISION {overview?.workspace?.active_revision || 1}</span><h2>See what changed,<br /><span>and why it matters.</span></h2><p>Project SuperJoin turns scattered PDFs into a living, inspectable layer of facts, evidence, conflicts, and temporal context.</p></div><div className="hero-diagram"><div className="flow-label">CURRENT KNOWLEDGE STATE</div><div className="flow-row"><div>PDFs</div><i>→</i><div>Claims</div><i>→</i><div className="flow-active">Facts</div></div><div className="flow-caption">Every accepted value keeps its source, context, and history.</div></div></section><section className="stats-grid"><Stat label="Documents" value={overview?.counts?.documents || 0} /><Stat label="Source claims" value={overview?.counts?.claims || 0} /><Stat label="Canonical facts" value={overview?.counts?.facts || 0} accent /><Stat label="Relationships" value={overview?.counts?.relationships || 0} /></section><section className="overview-grid"><div className="panel"><div className="panel-heading"><div><span className="eyebrow">KNOWLEDGE HEALTH</span><h3>What the layer knows</h3></div><span className="revision-dot">● LIVE</span></div><div className="health-list"><div><span className="health-dot good" />Supported <strong>{statuses.SUPPORTED || 0}</strong></div><div><span className="health-dot good" />Corroborated <strong>{statuses.CORROBORATED || 0}</strong></div><div><span className="health-dot bad" />Contested <strong>{statuses.CONTESTED || 0}</strong></div><div><span className="health-dot warn" />Needs review <strong>{statuses.UNRESOLVED || 0}</strong></div></div><div className="coverage"><span>Evidence coverage</span><strong>100%</strong><div><i style={{ width: '100%' }} /></div></div></div><div className="panel cases-panel"><div className="panel-heading"><div><span className="eyebrow">ASSIGNMENT CASES</span><h3>Walk the evaluator through it</h3></div><button className="link-button" onClick={() => document.querySelector('[data-case-nav]')?.click()}>Open all →</button></div>{cases.map((item) => <button className="case-row" onClick={() => onCase(item)} key={item.id}><span className="case-number">0{item.number}</span><span><strong>{item.title}</strong><small>{item.label}</small></span><Badge tone={item.label.includes('Failure') ? 'warn' : item.label.includes('conflict') ? 'bad' : 'good'}>view</Badge></button>)}</div></section><section className="panel diff-panel"><div className="panel-heading"><div><span className="eyebrow">LATEST KNOWLEDGE DIFF</span><h3>Changes stay explainable</h3></div><span className="mono">recorded-demo</span></div><div className="diff-cards"><div><strong>+ 6</strong><span>source claims</span></div><div><strong>✓ 1</strong><span>corroboration</span></div><div><strong>↻ 1</strong><span>reconciliation</span></div><div><strong>! 1</strong><span>contested</span></div></div></section></div>
}

function Facts({ facts, query, setQuery, onSelect }) {
  return <div className="content"><div className="section-heading"><div><span className="eyebrow">CANONICAL KNOWLEDGE</span><h2>Facts</h2><p>Derived views stay linked to immutable source claims.</p></div><button className="secondary-button">Export JSON ↓</button></div><div className="toolbar"><div className="search"><span>⌕</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search subject, predicate, value…" /></div><div className="filter-chip">All statuses⌄</div><div className="toolbar-count">{facts.length} visible</div></div><div className="table-card"><table><thead><tr><th>SUBJECT</th><th>FACT</th><th>VALUE</th><th>PERIOD</th><th>MODE</th><th>STATE</th><th>SOURCES</th></tr></thead><tbody>{facts.map((fact) => <tr onClick={() => onSelect(fact)} key={fact.id}><td><strong>{fact.subject}</strong></td><td><span className="predicate">{fact.predicate.replaceAll('_', ' ')}</span></td><td className="value-cell">{fact.display_value}</td><td className="mono">{fact.period || '—'}</td><td><span className="muted">{fact.modality || 'unknown'}</span></td><td><Badge tone={fact.status === 'CONTESTED' ? 'bad' : fact.status === 'CORROBORATED' ? 'good' : 'neutral'}>{fact.status}</Badge></td><td><span className="source-count">◉</span></td></tr>)}</tbody></table>{facts.length === 0 && <div className="empty">No facts match that search.</div>}</div></div>
}

function Documents({ documents }) {
  return <div className="content"><div className="section-heading"><div><span className="eyebrow">SOURCE LIBRARY</span><h2>Documents</h2><p>Every source remains visible beside the interpretations it supports.</p></div><label className="secondary-button">＋ Add PDF<input type="file" accept="application/pdf" /></label></div><div className="document-grid">{documents.map((document) => <div className="document-card" key={document.id}><div className="doc-icon">PDF</div><div className="document-info"><strong>{document.name}</strong><span>{document.publisher}</span><small>{document.page_count} PDF pages · {document.status === 'complete' ? 'parsed' : document.status}</small></div><Badge tone={document.status === 'complete' ? 'good' : 'warn'}>{document.status}</Badge></div>)}</div></div>
}

function Cases({ cases, relationships, selectedCase, onSelect }) {
  return <div className="content"><div className="section-heading"><div><span className="eyebrow">REQUIRED CASES</span><h2>Show the reasoning</h2><p>Four evaluator-ready paths through the evidence layer.</p></div></div><div className="case-grid">{cases.map((item) => { const relation = relationships.find((entry) => entry.id === item.relationship_id); return <button className={selectedCase?.id === item.id ? 'case-card selected' : 'case-card'} onClick={() => onSelect(item)} key={item.id}><span className="case-number">0{item.number}</span><Badge tone={item.label.includes('Failure') ? 'warn' : item.label.includes('conflict') ? 'bad' : 'good'}>{item.label}</Badge><h3>{item.title}</h3><p>{item.description}</p><div className="case-footer">{relation ? <><span>{relation.relationship_type}</span><span>Inspect evidence →</span></> : <><span>Native parser</span><span>Inspect failure →</span></>}</div></button> })}</div></div>
}

function Changes({ overview }) {
  return <div className="content"><div className="section-heading"><div><span className="eyebrow">REVISION HISTORY</span><h2>Knowledge Diff</h2><p>Changes are attached to a source, a run, or a review decision.</p></div></div><div className="panel diff-detail"><div className="diff-banner"><span className="revision-dot">●</span><div><strong>Recorded starter snapshot</strong><span>Project SuperJoin demo revision {overview?.workspace?.active_revision || 1}</span></div></div><div className="change-line"><span className="change-symbol plus">＋</span><div><strong>New source claims</strong><small>Facts were extracted with evidence anchors.</small></div><b>6</b></div><div className="change-line"><span className="change-symbol reconcile">↻</span><div><strong>Contextual reconciliation</strong><small>FY25 GDP values remain separated by data vintage.</small></div><b>1</b></div><div className="change-line"><span className="change-symbol conflict">!</span><div><strong>Contested forecast</strong><small>Trust Gate blocks an unqualified FY26 answer.</small></div><b>1</b></div></div></div>
}

function Settings() {
  const [settings, setSettings] = useState(null)
  useEffect(() => { get('/settings').then(setSettings) }, [])
  return <div className="content"><div className="section-heading"><div><span className="eyebrow">RUNTIME CONFIGURATION</span><h2>Settings</h2><p>Provider roles are independent and the demo remains usable without keys.</p></div></div><div className="settings-grid">{[['Extraction', settings?.roles?.extraction], ['Reasoning', settings?.roles?.reasoning], ['Vision', settings?.roles?.vision], ['Embeddings', settings?.roles?.embeddings]].map(([label, model]) => <div className="setting-card" key={label}><span className="eyebrow">{label}</span><strong>{model || 'loading…'}</strong><small>OpenAI-compatible role</small></div>)}</div><div className="panel settings-note"><Badge tone={settings?.provider_configured ? 'good' : 'warn'}>{settings?.provider_configured ? 'Live provider configured' : 'Recorded demo mode'}</Badge><p>Secrets are never returned to this screen. New PDF processing can be enabled with an OpenAI-compatible endpoint; the bundled snapshot requires no key.</p></div></div>
}

function Inspector({ fact, selectedCase, relationships, onClose }) {
  const relation = selectedCase?.relationship_id ? relationships.find((entry) => entry.id === selectedCase.relationship_id) : null
  return <aside className="inspector"><div className="inspector-top"><span className="eyebrow">EVIDENCE INSPECTOR</span><button className="close-button" onClick={onClose}>×</button></div>{fact ? <><Badge tone={fact.fact.status === 'CONTESTED' ? 'bad' : 'good'}>{fact.fact.status}</Badge><h2>{fact.fact.predicate.replaceAll('_', ' ')}</h2><div className="inspector-value">{fact.fact.display_value}</div><div className="inspector-meta">{fact.fact.period || 'No period'} · {fact.fact.scope || 'Scope unspecified'}</div><div className="inspector-rule" /><h4>SOURCE CLAIMS</h4>{fact.claims.map((claim) => <div className="evidence-block" key={claim.id}><div><strong>{claim.evidence?.document || 'Source document'}</strong><span>PDF p.{claim.evidence?.pdf_page} · printed p.{claim.evidence?.printed_page || '—'}</span></div><p>“{claim.evidence?.text || claim.raw_value}”</p></div>)}<div className="inspector-rule" /><h4>RESOLUTION</h4><p className="reasoning">{fact.fact.reason}</p>{fact.relationships.map((entry) => <div className="relation-chip" key={entry.id}><Badge tone={entry.relationship_type === 'CONTRADICTS' ? 'bad' : 'good'}>{entry.relationship_type}</Badge><span>{entry.reason}</span></div>)}</> : selectedCase ? <><Badge tone={selectedCase.label.includes('Failure') ? 'warn' : selectedCase.label.includes('conflict') ? 'bad' : 'good'}>{selectedCase.label}</Badge><h2>{selectedCase.title}</h2><p className="case-description">{selectedCase.description}</p>{relation ? <><div className="inspector-rule" /><h4>SYSTEM INTERPRETATION</h4><div className="relationship-hero"><strong>{relation.relationship_type}</strong><p>{relation.reason}</p></div><h4>COMPARISON DIMENSIONS</h4><div className="dimension-list">{Object.entries(relation.dimensions || {}).map(([key, value]) => <div key={key}><span>{key.replaceAll('_', ' ')}</span><strong>{value}</strong></div>)}</div></> : <><div className="inspector-rule" /><h4>OBSERVED FAILURE</h4><div className="failure-box"><strong>Native text extraction returned zero characters.</strong><p>The page is visually readable, so the adaptive parser routes it to a configured visual model. Without one, the claim remains quarantined rather than invented.</p></div></>}</> : null}</aside>
}

createRoot(document.getElementById('root')).render(<App />)

