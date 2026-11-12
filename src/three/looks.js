// Who may stand for the receptionist or the assistant in the photo-real look. A photo-real person is
// made from a company file's look (studio/blender/people_export.py records it in people.json), so one
// is used only for a company that gives the very same look: anyone else is drawn from their own look,
// never shown as someone else. No imports, so tests/test_looks.py can run it under Node.

// A look as one string, whatever order its settings were written in.
export const lookKey = (v) => (Array.isArray(v) ? `[${v.map(lookKey).join(',')}]`
  : v && typeof v === 'object' ? `{${Object.keys(v).sort().map((k) => `${JSON.stringify(k)}:${lookKey(v[k])}`).join(',')}}`
    : JSON.stringify(v ?? null));

// The first set of people (loadPeople's result, or null) that has `name` made from `look`, or null.
export function realPerson(sets, name, look) {
  const want = lookKey(look || {});
  return sets.find((set) => set?.has(name) && set.lookOf(name) && lookKey(set.lookOf(name)) === want) || null;
}
