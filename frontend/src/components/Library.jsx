import React, { useEffect, useRef, useState } from 'react';

const PAGE_SIZE = 20;
const TYPE_LABELS = { pdf: 'PDF', docx: 'Word document', pptx: 'PowerPoint', txt: 'Text file' };
const MARK = /(⟦[^⟧]*⟧)/;   // ⟦match⟧ markers from the server; no HTML is ever injected

// Where a value came from, in words (never colour alone).
const SOURCE_LABELS = {
  original: 'From the document',
  rule: 'Set by the site administrator',
  machine: 'Machine-generated, not yet reviewed',
  human: 'Written or reviewed by a person',
};
const FIELD_LABELS = { title: 'Title', author: 'Author', language: 'Language', doc_type: 'File type', folder: 'Folder', agency: 'Agency', tag: 'Tag', created: 'Created', modified: 'Modified', summary: 'Summary' };

function Snippet({ text }) {
  if (!text) return null;
  return (
    <p className="text-sm mt-1 opacity-90">
      {text.split(MARK).map((part, i) =>
        part.startsWith('⟦')
          ? <mark key={i} className="bg-yellow-200 text-gray-900 rounded px-0.5">{part.slice(1, -1)}</mark>
          : <React.Fragment key={i}>{part}</React.Fragment>)}
    </p>
  );
}

const fmtDate = (iso) => {
  if (!iso) return null;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d;
};

export default function Library({ isDark, cardClasses, onOpen, readingRoom }) {
  const [draft, setDraft] = useState('');
  const [params, setParams] = useState({ q: '', agency: '', tag: '', type: '', sort: 'relevance', page: 0 });
  const [facets, setFacets] = useState({ agency: [], tag: [], type: [] });
  // The results shown, tagged with the query they belong to; "loading" is simply "the shown results are for an older query".
  const [res, setRes] = useState({ key: null, data: { total: 0, results: [] }, error: '' });
  const queryKey = JSON.stringify(params);
  const loading = res.key !== queryKey;
  const data = res.data;
  const error = loading ? '' : res.error;
  const headingRef = useRef(null);
  const pageChanged = useRef(false);

  useEffect(() => {
    fetch('/library/facets').then(r => r.json()).then(setFacets).catch(() => {});
  }, []);

  useEffect(() => {
    const ctl = new AbortController();
    const qs = new URLSearchParams();
    if (params.q) qs.set('q', params.q);
    if (params.agency) qs.set('agency', params.agency);
    if (params.tag) qs.set('tag', params.tag);
    if (params.type) qs.set('type', params.type);
    qs.set('sort', params.q || params.sort !== 'relevance' ? params.sort : 'date');
    qs.set('limit', PAGE_SIZE);
    qs.set('offset', params.page * PAGE_SIZE);
    const key = JSON.stringify(params);
    fetch(`/library/search?${qs}`, { signal: ctl.signal })
      .then(r => { if (!r.ok) throw new Error('The library could not be searched right now.'); return r.json(); })
      .then(d => setRes({ key, data: d, error: '' }))
      .catch(e => { if (e.name !== 'AbortError') setRes({ key, data: { total: 0, results: [] }, error: e.message }); });
    return () => ctl.abort();
  }, [params]);

  useEffect(() => {   // after paging, move focus to the results heading so keyboard and screen-reader users land at the top of the new page
    if (!loading && pageChanged.current) { headingRef.current?.focus(); pageChanged.current = false; }
  }, [loading]);

  const set = (patch) => setParams(p => ({ ...p, ...patch, page: 0 }));
  const go = (page) => { pageChanged.current = true; setParams(p => ({ ...p, page })); };
  const pages = Math.max(1, Math.ceil(data.total / PAGE_SIZE));
  const anyFilter = params.q || params.agency || params.tag || params.type;
  const field = `w-full p-3 rounded-xl border text-base ${isDark ? 'bg-gray-900 border-gray-600 text-gray-100' : 'bg-white border-gray-300 text-gray-900'}`;
  const btn = `px-4 py-3 rounded-xl font-semibold ${isDark ? 'bg-indigo-500 text-white hover:bg-indigo-400' : 'bg-indigo-700 text-white hover:bg-indigo-600'}`;
  const ghost = `px-4 py-2 rounded-xl border font-medium disabled:opacity-60 ${isDark ? 'border-gray-600 hover:bg-white/10' : 'border-gray-300 hover:bg-gray-100'}`;

  return (
    <section aria-labelledby="library-title" className={`w-full rounded-[2rem] border p-6 sm:p-10 ${cardClasses}`}>
      <h2 id="library-title" className="text-2xl font-semibold tracking-tight mb-1">{readingRoom ? 'Reading room' : 'Library'}</h2>
      <p className={`mb-6 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>Search by title, subject, agency or any word in a document.</p>

      <form role="search" onSubmit={e => { e.preventDefault(); set({ q: draft.trim() }); }} className="flex flex-col sm:flex-row gap-3 mb-5">
        <div className="flex-1">
          <label htmlFor="lib-q" className="block text-sm font-medium mb-1">Search documents</label>
          <input id="lib-q" type="search" value={draft} onChange={e => setDraft(e.target.value)} maxLength={200}
                 autoComplete="off" className={field} placeholder="For example: zoning, budget, snow removal" />
        </div>
        <button type="submit" className={`${btn} sm:self-end`}>Search</button>
      </form>

      <fieldset className="mb-6">
        <legend className="text-sm font-medium mb-2">Narrow the results</legend>
        <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
          {[['lib-agency', 'Agency', 'agency', facets.agency], ['lib-tag', 'Subject', 'tag', facets.tag]].map(([id, label, key, opts]) => (
            <div key={id}>
              <label htmlFor={id} className="block text-sm mb-1">{label}</label>
              <select id={id} value={params[key]} onChange={e => set({ [key]: e.target.value })} className={field}>
                <option value="">All</option>
                {opts.map(o => <option key={o.value} value={o.value}>{o.value} ({o.count})</option>)}
              </select>
            </div>
          ))}
          <div>
            <label htmlFor="lib-type" className="block text-sm mb-1">Kind of document</label>
            <select id="lib-type" value={params.type} onChange={e => set({ type: e.target.value })} className={field}>
              <option value="">All</option>
              {facets.type.map(o => <option key={o.value} value={o.value}>{TYPE_LABELS[o.value] || o.value} ({o.count})</option>)}
            </select>
          </div>
          <div>
            <label htmlFor="lib-sort" className="block text-sm mb-1">Sort by</label>
            <select id="lib-sort" value={params.sort} onChange={e => set({ sort: e.target.value })} className={field}>
              <option value="relevance">Best match</option>
              <option value="date">Newest first</option>
              <option value="title">Title, A to Z</option>
            </select>
          </div>
        </div>
        {anyFilter && (
          <button type="button" className={`${ghost} mt-3`}
                  onClick={() => { setDraft(''); setParams({ q: '', agency: '', tag: '', type: '', sort: 'relevance', page: 0 }); }}>
            Clear search and filters
          </button>
        )}
      </fieldset>

      <h3 ref={headingRef} tabIndex={-1} className="text-lg font-semibold mb-1 outline-offset-4">Results</h3>
      <p role="status" aria-live="polite" className="text-sm mb-4">
        {loading ? 'Searching…' : error ? '' : `${data.total} ${data.total === 1 ? 'document' : 'documents'} found${params.q ? ` for “${params.q}”` : ''}.`}
      </p>
      {error && <p role="alert" className="mb-4 font-medium">{error}</p>}

      {!loading && !error && data.total === 0 && (
        <p className="mb-4">{anyFilter ? 'No documents match. Try fewer words or clear the filters.' : 'This library has no documents yet.'}</p>
      )}

      <ol aria-label="Search results" className="space-y-4">
        {data.results.map(r => {
          const d = fmtDate(r.date);
          return (
            <li key={r.id} className={`rounded-2xl border p-4 ${isDark ? 'border-white/10 bg-black/20' : 'border-gray-200 bg-white'}`}>
              <h4 className="text-lg font-semibold">
                <button type="button" onClick={() => onOpen(r)} className="text-left underline decoration-2 underline-offset-4 hover:no-underline">{r.title}</button>
              </h4>
              <p className={`text-sm mt-1 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                {TYPE_LABELS[r.file_type] || r.file_type}
                {r.agency && <> · {r.agency}</>}
                {d && <> · <time dateTime={r.date}>{d.toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric' })}</time></>}
              </p>
              {r.title_source === 'machine' && (
                <p className={`text-xs mt-1 font-medium ${isDark ? 'text-amber-300' : 'text-amber-800'}`}>Title inferred by software, not yet reviewed</p>
              )}
              <Snippet text={r.snippet} />
              {r.tags.length > 0 && <p className="text-xs mt-2 opacity-90"><span className="font-medium">Subjects:</span> {r.tags.join(', ')}</p>}
            </li>
          );
        })}
      </ol>

      {pages > 1 && (
        <nav aria-label="Results pages" className="flex items-center gap-4 mt-6">
          <button type="button" className={ghost} disabled={params.page === 0 || loading} onClick={() => go(params.page - 1)}>Previous page</button>
          <span aria-live="polite">Page {params.page + 1} of {pages}</span>
          <button type="button" className={ghost} disabled={params.page + 1 >= pages || loading} onClick={() => go(params.page + 1)}>Next page</button>
        </nav>
      )}
    </section>
  );
}

// Shown above the reader for a library document: what is known about it, and where each fact came from.
export function DocumentAbout({ item, isDark, onBack }) {
  const rows = (item.metadata || []).filter(m => FIELD_LABELS[m.key]);
  const machine = rows.some(m => m.provenance === 'machine');
  return (
    <section aria-labelledby="about-title" className={`w-full rounded-2xl border p-5 ${isDark ? 'bg-[#181a20]/80 border-white/5' : 'bg-white/80 border-gray-200'}`}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id="about-title" className="text-xl font-semibold">{item.title}</h2>
        <button type="button" onClick={onBack}
                className={`px-4 py-2 rounded-xl border font-medium ${isDark ? 'border-gray-600 hover:bg-white/10' : 'border-gray-300 hover:bg-gray-100'}`}>
          Back to search results
        </button>
      </div>
      <details className="mt-3">
        <summary className="cursor-pointer font-medium">About this document{machine ? ' (some details were generated by software)' : ''}</summary>
        <table className="mt-3 w-full text-sm text-left">
          <caption className="sr-only">Facts about this document and where each came from</caption>
          <thead><tr><th scope="col" className="py-1 pr-4">Detail</th><th scope="col" className="py-1 pr-4">Value</th><th scope="col" className="py-1">Source</th></tr></thead>
          <tbody>
            {rows.map((m, i) => (
              <tr key={i} className="align-top">
                <th scope="row" className="py-1 pr-4 font-medium">{FIELD_LABELS[m.key]}</th>
                <td className="py-1 pr-4">{m.value}</td>
                <td className="py-1">{SOURCE_LABELS[m.provenance] || m.provenance}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </section>
  );
}
