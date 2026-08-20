import React, { useState } from "react";
import { format, isValid } from "date-fns";
import { CalendarIcon, X } from "lucide-react";
import { Calendar } from "@/components/ui/calendar";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";

const pad2 = (n) => String(n).padStart(2, "0");
const HOURS = Array.from({ length: 12 }, (_, i) => i + 1);
const MINUTES = Array.from({ length: 12 }, (_, i) => i * 5);

// Local-time "YYYY-MM-DDTHH:mm" <-> Date, matching the native datetime-local
// value format this replaces — parent forms/validation are untouched.
function parseValue(value) {
  if (!value) return null;
  const d = new Date(value);
  return isValid(d) ? d : null;
}

function toValue(date) {
  return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}T${pad2(date.getHours())}:${pad2(date.getMinutes())}`;
}

const triggerClass =
  "w-full flex items-center gap-2 px-3.5 py-2.5 rounded-xl bg-muted/40 border border-border text-sm text-left outline-none focus:border-primary";
const timeSelectClass =
  "px-2 py-1.5 rounded-lg bg-muted/40 border border-border text-sm outline-none focus:border-primary disabled:opacity-40";

export default function DateTimePicker({ value, onChange, onBlur = undefined, min = undefined, max = undefined, placeholder = "Select date & time" }) {
  const [open, setOpen] = useState(false);
  const selected = parseValue(value);
  const minDate = parseValue(min);
  const maxDate = parseValue(max);

  const hour24 = selected ? selected.getHours() : 12;
  const hour12 = hour24 % 12 === 0 ? 12 : hour24 % 12;
  const minute = selected ? selected.getMinutes() : 0;
  const closestMinute = MINUTES.reduce((closest, m) => (Math.abs(m - minute) < Math.abs(closest - minute) ? m : closest), 0);
  const period = hour24 >= 12 ? "PM" : "AM";

  const commit = (date) => onChange(toValue(date));

  const handleOpenChange = (next) => {
    setOpen(next);
    if (!next) onBlur?.();
  };

  const handleDaySelect = (day) => {
    if (!day) return;
    const next = new Date(day.getFullYear(), day.getMonth(), day.getDate(), hour24, closestMinute);
    commit(next);
  };

  const setTime = (nextHour12, nextMinute, nextPeriod) => {
    const base = selected ?? new Date();
    const h24 = nextPeriod === "PM" ? (nextHour12 % 12) + 12 : nextHour12 % 12;
    commit(new Date(base.getFullYear(), base.getMonth(), base.getDate(), h24, nextMinute));
  };

  return (
    <Popover open={open} onOpenChange={handleOpenChange}>
      <div className="relative">
        <PopoverTrigger asChild>
          <button type="button" className={cn(triggerClass, selected && "pr-8")}>
            <CalendarIcon className="w-4 h-4 text-muted-foreground shrink-0" />
            <span className={cn("flex-1", !selected && "text-muted-foreground")}>
              {selected ? format(selected, "MMM d, yyyy · h:mm a") : placeholder}
            </span>
          </button>
        </PopoverTrigger>
        {selected && (
          <button
            type="button"
            onClick={() => onChange("")}
            className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
            aria-label="Clear date"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        )}
      </div>
      <PopoverContent className="w-auto p-0" align="start">
        <Calendar
          mode="single"
          selected={selected ?? undefined}
          onSelect={handleDaySelect}
          disabled={[
            ...(minDate ? [{ before: new Date(minDate.getFullYear(), minDate.getMonth(), minDate.getDate()) }] : []),
            ...(maxDate ? [{ after: new Date(maxDate.getFullYear(), maxDate.getMonth(), maxDate.getDate()) }] : []),
          ]}
          initialFocus
        />
        <div className="px-3 pb-3 pt-1 border-t border-border">
          <div className="flex items-center gap-2">
            <select
              className={timeSelectClass}
              disabled={!selected}
              value={hour12}
              onChange={(e) => setTime(Number(e.target.value), closestMinute, period)}
            >
              {HOURS.map((h) => <option key={h} value={h}>{h}</option>)}
            </select>
            <span className="text-muted-foreground">:</span>
            <select
              className={timeSelectClass}
              disabled={!selected}
              value={closestMinute}
              onChange={(e) => setTime(hour12, Number(e.target.value), period)}
            >
              {MINUTES.map((m) => <option key={m} value={m}>{pad2(m)}</option>)}
            </select>
            <select
              className={timeSelectClass}
              disabled={!selected}
              value={period}
              onChange={(e) => setTime(hour12, closestMinute, e.target.value)}
            >
              <option value="AM">AM</option>
              <option value="PM">PM</option>
            </select>
            {!selected && <span className="text-xs text-muted-foreground ml-1">Pick a date first</span>}
          </div>
          <div className="flex justify-end mt-2">
            <button
              type="button"
              disabled={!selected}
              onClick={() => handleOpenChange(false)}
              className="px-3 py-1.5 rounded-lg bg-primary text-primary-foreground text-xs font-heading font-bold disabled:opacity-40"
            >
              Done
            </button>
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
}
