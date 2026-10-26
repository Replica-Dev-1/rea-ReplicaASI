/* Reconstruction of the scoped Replica reference search behavior. MIT. */
(function (root) {
  function search(notes, query, options = {}) {
    const needle = String(query).trim().toLowerCase();
    const visible = notes.filter(note => (options.archived || !note.archived) && (!options.tag || note.tags.includes(options.tag)));
    const matched = visible.filter(note => !needle || [note.title, note.body].some(field => field.toLowerCase().includes(needle)));
    if (!needle) return matched;
    return matched.filter(note => note.title.toLowerCase().includes(needle)).concat(matched.filter(note => !note.title.toLowerCase().includes(needle)));
  }
  if (typeof module !== 'undefined' && module.exports) module.exports = { search }; else root.ReplicaSearch = { search };
})(typeof window !== 'undefined' ? window : globalThis);
