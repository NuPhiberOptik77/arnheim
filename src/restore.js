// Restore points (connect/restore.py): the files as they were just before an agent changed them, kept
// by git beside the project's own history. The hook takes one before the first change after each message
// you send an agent, and before any command that deletes or overwrites files in bulk; with control on,
// the building can put the files back to one. Plain module, so tests/test_restore.py can run it under Node.
//
// A point: { id, at (seconds), project, key (its conversation), title, why, by: 'agent' | 'you', files }.

const POINT = /^rp-[0-9a-f]{12}$/;

// What someone asks the receptionist about them: "can I undo what the agent did?", "restore points".
export const RESTORE_ASKED = /\b(?:restore points?|undo (?:what|the|its|their|that|everything)|go(?:ing)? back to (?:before|how|where)|put (?:it|them|the files|everything|things) back|roll(?:ing)? (?:it |them |that )?back)\b/i;

// The points for one conversation (key) or one floor (project), newest first.
export function pointsOf(points, { key, project } = {}) {
  return (Array.isArray(points) ? points : [])
    .filter((p) => p && POINT.test(p.id) && Number.isFinite(p.at) && (key == null || p.key === key) && (project == null || p.project === project))
    .sort((a, b) => b.at - a.at);
}

const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

// One point in a line: "10:42, before changing files for "Fix the login"".
export function sayPoint(p, clock) {
  const files = Number.isFinite(p.files) && p.files > 0 ? `. ${plural(p.files, 'file', 'files')} not yet committed then` : '';
  return `${clock(p.at)}, ${p.why || 'before changing files'}${files}`;
}

// The receptionist's answer: the latest few, or how to have them.
export function sayRestore(points, label = (p) => p, clock = (t) => String(t), most = 3) {
  const list = pointsOf(points);
  if (!list.length) {
    return 'There are no restore points yet. With the PreToolUse hook switched on (docs/connect.md, "Restore points"), '
      + "one is taken before an agent changes a project's files, and you can go back to it from the conversation's page.";
  }
  const lines = list.slice(0, most).map((p) => `${label(p.project)} at ${clock(p.at)}, ${p.why || 'before changing files'}`);
  return `${plural(list.length, 'restore point is', 'restore points are')} kept. The latest: ${lines.join('; ')}. `
    + "Open a conversation or a floor to go back to one. Going back keeps how things are now as a restore point too, so it can be undone.";
}

// What going back did, in words.
export function wentBack(out) {
  const left = Array.isArray(out?.left) ? out.left : [];
  const more = Number(out?.more) || 0;
  const made = left.length
    ? ` ${plural(left.length + more, "file that wasn't there then was", "files that weren't there then were")} left as ${left.length + more === 1 ? 'it is' : 'they are'}: ${left.join(', ')}${more ? ` and ${more} more` : ''}.`
    : '';
  return `The files are back as they were.${made}${out?.kept ? ' How they were a moment ago is kept as a restore point too.' : ''}`;
}
