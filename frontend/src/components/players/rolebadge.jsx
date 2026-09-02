import { Badge } from "@/components/ui/badge";
import { roleLabel } from "@/lib/playerDisplay";

const VARIANTS = { admin: "destructive", organizer: "default", player: "secondary" };

export default function RoleBadge({ role, className = "" }) {
  return (
    <Badge variant={VARIANTS[role] || "secondary"} className={className}>
      {roleLabel(role)}
    </Badge>
  );
}
