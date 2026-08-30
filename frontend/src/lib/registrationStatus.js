// Shared source of truth for "can this registration check in" — used by
// both RegistrationRow and RegistrationDetailDialog (src/pages/tournamentdetail.jsx),
// which previously implemented this independently and drifted apart: the
// dialog only excluded "rejected", letting a cancelled or disqualified
// registration still show an active "Check in" button. The backend
// (RegistrationCheckInView, tourny_regist/views.py) is the authoritative
// source and already blocks all three statuses unconditionally — this just
// keeps the frontend's affordance consistent with what the backend allows.
export const TERMINAL_NEGATIVE_STATUSES = ["rejected", "cancelled", "disqualified"];

export function canCheckIn(registration, hasFee) {
  if (!registration || registration.checked_in) return false;
  if (TERMINAL_NEGATIVE_STATUSES.includes(registration.status)) return false;
  if (hasFee && registration.status !== "approved") return false;
  return true;
}
