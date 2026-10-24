const timeFmt = new Intl.DateTimeFormat(undefined, { weekday: "short", hour: "numeric", minute: "2-digit" });
const dateTimeFmt = new Intl.DateTimeFormat(undefined, {
  weekday: "short",
  month: "short",
  day: "numeric",
  hour: "numeric",
  minute: "2-digit",
  timeZoneName: "short",
});

export const fmtTime = (iso: string | Date) => timeFmt.format(new Date(iso));
export const fmtDateTime = (iso: string | Date) => dateTimeFmt.format(new Date(iso));

export function fmtDuration(seconds: number): string {
  const minutes = Math.round(seconds / 60);
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return h ? `${h}h ${String(m).padStart(2, "0")}m` : `${m}m`;
}

export const fmtMiles = (mi: number) => `${mi.toLocaleString(undefined, { maximumFractionDigits: mi < 10 ? 1 : 0 })} mi`;

export const fmtLbs = (lbs: number) => `${lbs.toLocaleString()} lb`;

/** Short description for WMO weather codes returned by Open-Meteo. */
export function describeWeatherCode(code: number | null): string {
  if (code === null) return "";
  if (code === 0) return "Clear";
  if (code <= 3) return "Cloudy";
  if (code <= 48) return "Fog";
  if (code <= 57) return "Drizzle";
  if (code <= 67) return "Rain";
  if (code <= 77) return "Snow";
  if (code <= 82) return "Rain showers";
  if (code <= 86) return "Snow showers";
  return "Thunderstorm";
}

/** `<input type="datetime-local">` value for a Date, in the browser's local time. */
export function toLocalInputValue(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function escapeHtml(s: string): string {
  return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);
}
