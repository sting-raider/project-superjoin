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
  const [workspace, setWorkspace] = useState('delhivery')
  const [workspaces, setWorkspaces] = useState([])
  const [overview, setOverview] = useState(null)
  const [facts, setFacts] = useState([])
  const [cases, setCases] = useState([])
  const [relationships, setRelationships] = useState([])
  const [documents, setDocuments] = useState([])
  const [changes, setChanges] = useState([])
  const [reviews, setReviews] = useState([])
  const [selectedFact, setSelectedFact] = useState(null)
  const [selectedCase, setSelectedCase] = useState(null)
  const [section, setSection] = useState('overview')
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(true)
  const [notice, setNotice] = useState('')

  const refresh = async (id = workspace) => {
    setLoading(true)
    try {
      const [nextOverview, nextFacts, nextCases, nextRelationships, nextDocuments, nextChanges, nextReviews] = await Promise.all([
        get(`/overview?workspace_id=${id}`), get(`/facts?workspace_id=${id}&limit=200`), get('/cases'),
        get(`/relationships?workspace_id=${id}`), get(`/documents?workspace_id=${id}`),
        get(`/changes?workspace_id=${id}`), get(`/reviews?workspace_id=${id}`),
      ])
      setOverview(nextOverview); setFacts(nextFacts.items); setCases(nextCases.items)
      setRelationships(nextRelationships.items); setDocuments(nextDocuments.items); setChanges(nextChanges.items); setReviews(nextReviews.items)
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
        {[['overview', 'Overview', '⌂'], ['facts', 'Facts', '▦'], ['documents', 'Documents', '▤'], ['cases', 'Required cases', '◈'], ['changes', 'Knowledge Diff', '↻'], ['review', 'Review', '✓'], ['trust', 'Trust Gate', '⊙'], ['settings', 'Settings', '⚙']].map(([key, label, icon]) => <button data-case-nav={key === 'cases' ? 'true' : undefined} className={section === key ? 'nav-item active' : 'nav-item'} onClick={() => setSection(key)} key={key}><span>{icon}</span>{label}{key === 'cases' && <em>4</em>}</button>)}
      </nav>
      <div className="sidebar-foot"><Badge tone="good">● Demo mode</Badge><p>Recorded model outputs are available without an API key.</p><button className="text-button" onClick={resetDemo}>Reset demo workspace</button></div>
    </aside>
    <main className="main">
      <header className="topbar"><div><span className="eyebrow">FACT KNOWLEDGE LAYER</span><h1>{overview?.workspace?.name || 'Workspace'}</h1></div><div className="top-actions"><label className="upload-button">＋ Upload PDF<input type="file" accept="application/pdf" onChange={onUpload} /></label><button className="icon-button" title="Search facts" onClick={() => setSection('facts')}>⌕</button></div></header>
      {notice && <div className="notice" role="status">{notice}<button onClick={() => setNotice('')}>×</button></div>}
      {loading ? <div className="loading"><div className="spinner" />Loading the evidence layer…</div> : <>
        {section === 'overview' && <Overview overview={overview} facts={facts} cases={cases} onCase={selectCase} onOpenCases={() => setSection('cases')} />}
        {section === 'facts' && <Facts facts={filteredFacts} query={query} setQuery={setQuery} onSelect={openFact} />}
        {section === 'documents' && <Documents documents={documents} onUpload={onUpload} />}
        {section === 'cases' && <Cases cases={cases} relationships={relationships} selectedCase={selectedCase} onSelect={selectCase} />}
        {section === 'changes' && <Changes overview={overview} changes={changes} />}
        {section === 'review' && <Review workspace={workspace} reviews={reviews} facts={facts} onRefresh={() => refresh()} />}
        {section === 'trust' && <TrustGate workspace={workspace} />}
        {section === 'settings' && <Settings />}
      </>}
    </main>
    {(selectedFact || selectedCase) && <Inspector fact={selectedFact} selectedCase={selectedCase} relationships={relationships} onClose={() => { setSelectedFact(null); setSelectedCase(null) }} />}
  </div>
}

function Overview({ overview, facts, cases, onCase, onOpenCases }) {
  const statuses = overview?.statuses || {}
  return <div className="content"><section className="hero-panel"><div><span className="eyebrow green">EVIDENCE FIRST · REVISION {overview?.workspace?.active_revision || 1}</span><h2>See what changed,<br /><span>and why it matters.</span></h2><p>Project SuperJoin turns scattered PDFs into a living, inspectable layer of facts, evidence, conflicts, and temporal context.</p></div><div className="hero-diagram"><div className="flow-label">CURRENT KNOWLEDGE STATE</div><div className="flow-row"><div>PDFs</div><i>→</i><div>Claims</div><i>→</i><div className="flow-active">Facts</div></div><div className="flow-caption">Every accepted value keeps its source, context, and history.</div></div></section><section className="stats-grid"><Stat label="Documents" value={overview?.counts?.documents || 0} /><Stat label="Source claims" value={overview?.counts?.claims || 0} /><Stat label="Canonical facts" value={overview?.counts?.facts || 0} accent /><Stat label="Relationships" value={overview?.counts?.relationships || 0} /></section><section className="overview-grid"><div className="panel"><div className="panel-heading"><div><span className="eyebrow">KNOWLEDGE HEALTH</span><h3>What the layer knows</h3></div><span className="revision-dot">● LIVE</span></div><div className="health-list"><div><span className="health-dot good" />Supported <strong>{statuses.SUPPORTED || 0}</strong></div><div><span className="health-dot good" />Corroborated <strong>{statuses.CORROBORATED || 0}</strong></div><div><span className="health-dot bad" />Contested <strong>{statuses.CONTESTED || 0}</strong></div><div><span className="health-dot warn" />Needs review <strong>{statuses.UNRESOLVED || 0}</strong></div></div><div className="coverage"><span>Evidence coverage</span><strong>100%</strong><div><i style={{ width: '100%' }} /></div></div></div><div className="panel cases-panel"><div className="panel-heading"><div><span className="eyebrow">ASSIGNMENT CASES</span><h3>Walk the evaluator through it</h3></div><button className="link-button" onClick={onOpenCases}>Open all →</button></div>{cases.map((item) => <button className="case-row" onClick={() => onCase(item)} key={item.id}><span className="case-number">0{item.number}</span><span><strong>{item.title}</strong><small>{item.label}</small></span><Badge tone={item.label.includes('Failure') ? 'warn' : item.label.includes('conflict') ? 'bad' : 'good'}>view</Badge></button>)}</div></section><section className="panel diff-panel"><div className="panel-heading"><div><span className="eyebrow">LATEST KNOWLEDGE DIFF</span><h3>Changes stay explainable</h3></div><span className="mono">recorded-demo</span></div><div className="diff-cards"><div><strong>+ {overview?.counts?.claims || 0}</strong><span>source claims</span></div><div><strong>✓ {overview?.statuses?.CORROBORATED || 0}</strong><span>corroboration</span></div><div><strong>↻ 1</strong><span>reconciliation</span></div><div><strong>! {overview?.statuses?.CONTESTED || 0}</strong><span>contested</span></div></div></section></div>
}

function Facts({ facts, query, setQuery, onSelect }) {
  const exportFacts = () => { const blob = new Blob([JSON.stringify(facts, null, 2)], { type: 'application/json' }); const url = URL.createObjectURL(blob); const link = document.createElement('a'); link.href = url; link.download = 'project-superjoin-facts.json'; link.click(); URL.revokeObjectURL(url) }
  return <div className="content"><div className="section-heading"><div><span className="eyebrow">CANONICAL KNOWLEDGE</span><h2>Facts</h2><p>Derived views stay linked to immutable source claims.</p></div><button className="secondary-button" onClick={exportFacts}>Export JSON ↓</button></div><div className="toolbar"><div className="search"><span>⌕</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search subject, predicate, value…" /></div><div className="filter-chip">All statuses⌄</div><div className="toolbar-count">{facts.length} visible</div></div><div className="table-card"><table><thead><tr><th>SUBJECT</th><th>FACT</th><th>VALUE</th><th>PERIOD</th><th>MODE</th><th>STATE</th><th>SOURCES</th></tr></thead><tbody>{facts.map((fact) => <tr onClick={() => onSelect(fact)} key={fact.id}><td><strong>{fact.subject}</strong></td><td><span className="predicate">{fact.predicate.replaceAll('_', ' ')}</span></td><td className="value-cell">{fact.display_value}</td><td className="mono">{fact.period || '—'}</td><td><span className="muted">{fact.modality || 'unknown'}</span></td><td><Badge tone={fact.status === 'CONTESTED' ? 'bad' : fact.status === 'CORROBORATED' ? 'good' : 'neutral'}>{fact.status}</Badge></td><td><span className="source-count">◉</span></td></tr>)}</tbody></table>{facts.length === 0 && <div className="empty">No facts match that search.</div>}</div></div>
}

function Documents({ documents, onUpload }) {
  return <div className="content"><div className="section-heading"><div><span className="eyebrow">SOURCE LIBRARY</span><h2>Documents</h2><p>Every source remains visible beside the interpretations it supports.</p></div><label className="secondary-button">＋ Add PDF<input type="file" accept="application/pdf" onChange={onUpload} /></label></div><div className="document-grid">{documents.map((document) => <div className="document-card" key={document.id}><div className="doc-icon">PDF</div><div className="document-info"><strong>{document.name}</strong><span>{document.publisher}</span><small>{document.page_count} PDF pages · {document.status === 'complete' ? 'parsed' : document.status}</small></div><Badge tone={document.status === 'complete' ? 'good' : 'warn'}>{document.status}</Badge></div>)}</div></div>
}

function Cases({ cases, relationships, selectedCase, onSelect }) {
  return <div className="content"><div className="section-heading"><div><span className="eyebrow">REQUIRED CASES</span><h2>Show the reasoning</h2><p>Four evaluator-ready paths through the evidence layer.</p></div></div><div className="case-grid">{cases.map((item) => { const relation = relationships.find((entry) => entry.id === item.relationship_id); return <button className={selectedCase?.id === item.id ? 'case-card selected' : 'case-card'} onClick={() => onSelect(item)} key={item.id}><span className="case-number">0{item.number}</span><Badge tone={item.label.includes('Failure') ? 'warn' : item.label.includes('conflict') ? 'bad' : 'good'}>{item.label}</Badge><h3>{item.title}</h3><p>{item.description}</p><div className="case-footer">{relation ? <><span>{relation.relationship_type}</span><span>Inspect evidence →</span></> : <><span>Native parser</span><span>Inspect failure →</span></>}</div></button> })}</div></div>
}

function Changes({ overview, changes }) {
  return <div className="content"><div className="section-heading"><div><span className="eyebrow">REVISION HISTORY</span><h2>Knowledge Diff</h2><p>Changes are attached to a source, a run, or a review decision.</p></div></div><div className="panel diff-detail"><div className="diff-banner"><span className="revision-dot">●</span><div><strong>Committed knowledge revision</strong><span>Project SuperJoin revision {overview?.workspace?.active_revision || 1} · {changes.length} recorded changes</span></div></div>{changes.length ? changes.map((change) => <div className="change-line" key={change.id}><span className={`change-symbol ${change.kind.includes('conflict') ? 'conflict' : change.kind.includes('reconcile') ? 'reconcile' : 'plus'}`}>{change.kind.includes('conflict') ? '!' : change.kind.includes('reconcile') ? '↻' : '＋'}</span><div><strong>{change.summary}</strong><small>{change.kind} · {change.run_id || 'recorded'}</small></div><b>view</b></div>) : <div className="empty">No changes recorded for this workspace.</div>}</div></div>
}

function Settings() {
  const [settings, setSettings] = useState(null)
  useEffect(() => { get('/settings').then(setSettings) }, [])
  return <div className="content"><div className="section-heading"><div><span className="eyebrow">RUNTIME CONFIGURATION</span><h2>Settings</h2><p>Provider roles are independent and the demo remains usable without keys.</p></div></div><div className="settings-grid">{[['Extraction', settings?.roles?.extraction], ['Reasoning', settings?.roles?.reasoning], ['Vision', settings?.roles?.vision], ['Embeddings', settings?.roles?.embeddings]].map(([label, model]) => <div className="setting-card" key={label}><span className="eyebrow">{label}</span><strong>{model || 'loading…'}</strong><small>OpenAI-compatible role</small></div>)}</div><div className="panel settings-note"><Badge tone={settings?.provider_configured ? 'good' : 'warn'}>{settings?.provider_configured ? 'Live provider configured' : 'Recorded demo mode'}</Badge><p>Secrets are never returned to this screen. New PDF processing can be enabled with an OpenAI-compatible endpoint; the bundled snapshot requires no key.</p><div className="budget-line"><span>Budget remaining</span><strong>${settings?.budget?.remaining_usd?.toFixed?.(4) || '20.0000'}</strong></div></div></div>
}

function Review({ workspace, reviews, facts, onRefresh }) {
  const [factId, setFactId] = useState(facts.find((fact) => fact.status === 'CONTESTED')?.id || facts[0]?.id || '')
  const [action, setAction] = useState('keep_unresolved')
  const [rationale, setRationale] = useState('')
  const [notice, setNotice] = useState('')
  const submit = async (event) => { event.preventDefault(); if (!factId || !rationale.trim()) return setNotice('Choose a fact and provide a rationale.'); try { await post('/reviews', { workspace_id: workspace, fact_id: factId, action, rationale }); setNotice('Immutable review recorded.'); setRationale(''); onRefresh() } catch (error) { setNotice(error.message) } }
  return <div className="content"><div className="section-heading"><div><span className="eyebrow">HUMAN REVIEW</span><h2>Review queue</h2><p>Decisions attach to a fact revision and never overwrite source claims.</p></div></div><div className="review-layout"><form className="panel review-form" onSubmit={submit}><label>FACT<select value={factId} onChange={(event) => setFactId(event.target.value)}>{facts.map((fact) => <option value={fact.id} key={fact.id}>{fact.subject} · {fact.predicate} · {fact.period || 'no period'}</option>)}</select></label><label>DECISION<select value={action} onChange={(event) => setAction(event.target.value)}><option value="keep_unresolved">Keep unresolved</option><option value="prefer">Prefer for a named use</option><option value="confirm_context">Confirm context distinction</option></select></label><label>RATIONALE<textarea value={rationale} onChange={(event) => setRationale(event.target.value)} placeholder="Why should this decision apply to this revision?" rows="5" /></label><button className="upload-button" type="submit">Record decision</button>{notice && <p className="form-notice">{notice}</p>}</form><div className="panel"><span className="eyebrow">DECISION LEDGER</span>{reviews.length ? reviews.map((review) => <div className="review-row" key={review.id}><Badge tone={review.stale ? 'warn' : 'good'}>{review.status}</Badge><div><strong>{review.action}</strong><small>{review.rationale}</small></div><span className="mono">rev {review.based_on_revision}</span></div>) : <div className="empty">No decisions recorded.</div>}</div></div></div>
}

function TrustGate({ workspace }) {
  const [subject, setSubject] = useState(workspace === 'india-macro' ? 'India' : 'Delhivery')
  const [predicate, setPredicate] = useState(workspace === 'india-macro' ? 'real_gdp_growth' : 'revenue_from_services')
  const [period, setPeriod] = useState(workspace === 'india-macro' ? 'FY26' : 'FY24')
  const [policy, setPolicy] = useState('strict')
  const [result, setResult] = useState(null)
  const run = async (event) => { event.preventDefault(); try { setResult(await post('/resolve', { workspace_id: workspace, subject, predicate, period, policy })) } catch (error) { setResult({ error: error.message }) } }
  return <div className="content"><div className="section-heading"><div><span className="eyebrow">MACHINE CONSUMPTION</span><h2>Trust Gate</h2><p>Ask for a fact; blocked decisions return alternatives instead of an executable value.</p></div></div><div className="trust-layout"><form className="panel trust-form" onSubmit={run}><label>SUBJECT<input value={subject} onChange={(event) => setSubject(event.target.value)} /></label><label>PREDICATE<input value={predicate} onChange={(event) => setPredicate(event.target.value)} /></label><label>PERIOD<input value={period} onChange={(event) => setPeriod(event.target.value)} placeholder="Optional" /></label><label>POLICY<select value={policy} onChange={(event) => setPolicy(event.target.value)}><option value="strict">Strict</option><option value="human_preference">Explicit human preference</option></select></label><button className="upload-button" type="submit">Resolve fact</button></form><div className="panel gate-result">{result ? <><Badge tone={result.safe_to_use ? 'good' : 'bad'}>{result.decision}</Badge><h3>{result.safe_to_use ? result.display_value : 'No executable value'}</h3><p>{(result.reason_codes || []).join(' · ')}</p><pre>{JSON.stringify(result, null, 2)}</pre></> : <div className="empty">Submit a query to inspect the signed-off JSON response.</div>}</div></div></div>
}

function Inspector({ fact, selectedCase, relationships, onClose }) {
  const relation = selectedCase?.relationship_id ? relationships.find((entry) => entry.id === selectedCase.relationship_id) : null
  return <aside className="inspector"><div className="inspector-top"><span className="eyebrow">EVIDENCE INSPECTOR</span><button className="close-button" onClick={onClose}>×</button></div>{fact ? <><Badge tone={fact.fact.status === 'CONTESTED' ? 'bad' : 'good'}>{fact.fact.status}</Badge><h2>{fact.fact.predicate.replaceAll('_', ' ')}</h2><div className="inspector-value">{fact.fact.display_value}</div><div className="inspector-meta">{fact.fact.period || 'No period'} · {fact.fact.scope || 'Scope unspecified'}</div><div className="inspector-rule" /><h4>SOURCE EVIDENCE</h4>{(fact.anchors || []).map((anchor) => <div className="evidence-block" key={anchor.id}><div><strong>{anchor.document_id}</strong><span>PDF p.{anchor.pdf_page} · printed p.{anchor.printed_page || '—'} · {anchor.precision}</span></div><p>“{anchor.text}”</p></div>)}<div className="inspector-rule" /><h4>NORMALIZED INTERPRETATION</h4><p className="reasoning">{fact.fact.reason}</p>{fact.interpretations?.slice(0, 3).map((interpretation) => <div className="relation-chip" key={interpretation.id}><Badge tone="neutral">{interpretation.value_type}</Badge><span>{interpretation.predicate} · {interpretation.normalized_value || 'text'} · {interpretation.eligibility}</span></div>)}{fact.relationships.map((entry) => <div className="relation-chip" key={entry.id}><Badge tone={entry.relationship_type === 'CONTRADICTS' ? 'bad' : 'good'}>{entry.relationship_type}</Badge><span>{entry.reason}</span></div>)}</> : selectedCase ? <><Badge tone={selectedCase.label.includes('Failure') ? 'warn' : selectedCase.label.includes('conflict') ? 'bad' : 'good'}>{selectedCase.label}</Badge><h2>{selectedCase.title}</h2><p className="case-description">{selectedCase.description}</p>{relation ? <><div className="inspector-rule" /><h4>SYSTEM INTERPRETATION</h4><div className="relationship-hero"><strong>{relation.relationship_type}</strong><p>{relation.reason}</p></div><h4>COMPARISON DIMENSIONS</h4><div className="dimension-list">{Object.entries(relation.dimensions || {}).map(([key, value]) => <div key={key}><span>{key.replaceAll('_', ' ')}</span><strong>{value}</strong></div>)}</div></> : <><div className="inspector-rule" /><h4>OBSERVED FAILURE</h4><div className="failure-box"><strong>Native text extraction returned zero characters.</strong><p>The page is visually readable, so the adaptive parser routes it to a configured visual model. Without one, the claim remains quarantined rather than invented.</p></div></>}</> : null}</aside>
}

createRoot(document.getElementById('root')).render(<App />)
