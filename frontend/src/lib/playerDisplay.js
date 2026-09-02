export function displayName(p) {
  return [p.first_name, p.last_name].filter(Boolean).join(" ") || p.email;
}

export function initials(p) {
  return displayName(p).charAt(0).toUpperCase();
}

const ROLE_LABELS = { admin: "Admin", organizer: "Organizer", player: "Player" };

export function roleLabel(role) {
  return ROLE_LABELS[role] || "Player";
}
