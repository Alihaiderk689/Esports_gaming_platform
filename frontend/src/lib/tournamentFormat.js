export const BRACKET_FORMAT_LABELS = {
  single: "Single Elimination", double: "Double Elimination", guarantee3: "3-Game Guarantee",
  round_robin: "Round Robin", swiss: "Swiss System", group_playoff: "Group Stage + Playoff",
};

export const formatMoney = (n) => `PKR ${Number(n || 0).toLocaleString()}`;

export function formatDateRange(start, end) {
  if (!start) return "TBA";
  const opts = { month: "short", day: "numeric" };
  const s = new Date(start);
  if (!end) return `${s.toLocaleDateString(undefined, opts)}, ${s.getFullYear()}`;
  const e = new Date(end);
  if (s.toDateString() === e.toDateString()) return `${s.toLocaleDateString(undefined, opts)}, ${s.getFullYear()}`;
  const sameMonth = s.getMonth() === e.getMonth() && s.getFullYear() === e.getFullYear();
  const endStr = sameMonth ? `${e.getDate()}` : e.toLocaleDateString(undefined, opts);
  return `${s.toLocaleDateString(undefined, opts)} – ${endStr}, ${e.getFullYear()}`;
}
