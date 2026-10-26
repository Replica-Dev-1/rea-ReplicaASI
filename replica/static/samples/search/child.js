/* Descendant extension: reuse the inherited implementation; add all-word matching and a result limit. MIT. */
(function (root) {
  const parent = typeof module !== 'undefined' && module.exports ? require('./search.js') : root.ReplicaSearch;
  function search(notes, query, options = {}) {
    const terms = String(query).trim().toLowerCase().split(/\s+/).filter(Boolean);
    let results = parent.search(notes, terms[0] || '', options);
    if (terms.length > 1) results = results.filter(note => terms.every(term => (note.title + ' ' + note.body).toLowerCase().includes(term)));
    if (Number.isInteger(options.limit) && options.limit >= 0) results = results.slice(0, options.limit);
    return results;
  }
  if (typeof module !== 'undefined' && module.exports) module.exports = { search }; else root.ReplicaSearchChild = { search };
})(typeof window !== 'undefined' ? window : globalThis);
