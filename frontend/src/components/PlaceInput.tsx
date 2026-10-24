import { useEffect, useId, useState } from "react";
import { searchPlaces } from "../api/client";
import type { Place } from "../api/types";
import { useDebouncedValue } from "../hooks/useDebouncedValue";

interface Props {
  label: string;
  value: Place | string;
  onChange: (value: Place | string) => void;
  placeholder?: string;
}

/** Accessible autocomplete: free text is allowed (geocoded server-side), picking a suggestion pins exact coordinates. */
export function PlaceInput({ label, value, onChange, placeholder }: Props) {
  const id = useId();
  const text = typeof value === "string" ? value : value.label;
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const [suggestions, setSuggestions] = useState<Place[]>([]);
  const query = useDebouncedValue(typeof value === "string" ? value.trim() : "", 250);

  useEffect(() => {
    if (query.length < 3) {
      setSuggestions([]);
      return;
    }
    const ctrl = new AbortController();
    searchPlaces(query, ctrl.signal)
      .then((results) => {
        setSuggestions(results);
        setActive(-1);
      })
      .catch(() => {}); // suggestions are best-effort; the server geocodes free text on submit anyway
    return () => ctrl.abort();
  }, [query]);

  const pick = (p: Place) => {
    onChange(p);
    setOpen(false);
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (!open || suggestions.length === 0) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((i) => (i + 1) % suggestions.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => (i <= 0 ? suggestions.length - 1 : i - 1));
    } else if (e.key === "Enter" && active >= 0) {
      e.preventDefault();
      pick(suggestions[active]);
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  };

  const showList = open && suggestions.length > 0 && typeof value === "string";

  return (
    <div className="field place-input">
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
        role="combobox"
        aria-expanded={showList}
        aria-controls={`${id}-list`}
        aria-activedescendant={active >= 0 ? `${id}-opt-${active}` : undefined}
        autoComplete="off"
        value={text}
        placeholder={placeholder}
        onChange={(e) => {
          onChange(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => window.setTimeout(() => setOpen(false), 120)}
        onKeyDown={onKeyDown}
        required
      />
      {typeof value !== "string" && <span className="pinned" title="Exact location selected">●</span>}
      {showList && (
        <ul id={`${id}-list`} role="listbox" className="suggestions">
          {suggestions.map((s, i) => (
            <li
              key={`${s.label}-${s.lat}`}
              id={`${id}-opt-${i}`}
              role="option"
              aria-selected={i === active}
              className={i === active ? "active" : undefined}
              onMouseDown={(e) => {
                e.preventDefault();
                pick(s);
              }}
            >
              {s.label}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
