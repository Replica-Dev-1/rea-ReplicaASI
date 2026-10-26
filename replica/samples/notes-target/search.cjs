// Replica reference application, MIT license. Public sample, not third-party reverse engineering.
function findNotes(notes, query, options = {}) {
  const needle = String(query).trim().toLowerCase();
  const matches = [];
  for (let index = 0; index < notes.length; index++) {
    const note = notes[index];
    if (!options.archived && note.archived) continue;
    if (options.tag && !note.tags.includes(options.tag)) continue;
    const title = note.title.toLowerCase();
    const body = note.body.toLowerCase();
    if (needle && !title.includes(needle) && !body.includes(needle)) continue;
    matches.push({ note, rank: needle && title.includes(needle) ? 0 : 1, index });
  }
  matches.sort((a, b) => a.rank - b.rank || a.index - b.index);
  return matches.map(item => item.note);
}
module.exports = { findNotes };
