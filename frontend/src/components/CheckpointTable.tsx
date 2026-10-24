import { memo } from "react";
import type { Checkpoint, RouteOption } from "../api/types";
import { describeWeatherCode, fmtTime } from "../lib/format";
import { levelMeta } from "../lib/risk";

interface Props {
  route: RouteOption;
  onFocus: (cp: Checkpoint) => void;
}

export const CheckpointTable = memo(function CheckpointTable({ route, onFocus }: Props) {
  return (
    <section className="checkpoints" aria-label={`${route.name} checkpoints`}>
      <h3>
        {route.name} checkpoints <span className="muted">({route.checkpoints.length})</span>
      </h3>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Mile</th>
              <th>ETA</th>
              <th>Wind</th>
              <th>Rain</th>
              <th>Snow</th>
              <th>Risk</th>
            </tr>
          </thead>
          <tbody>
            {route.checkpoints.map((cp) => {
              const meta = levelMeta(cp.risk.level);
              return (
                <tr key={cp.index} onClick={() => onFocus(cp)} tabIndex={0} onKeyDown={(e) => e.key === "Enter" && onFocus(cp)}>
                  <td>{Math.round(cp.mile)}</td>
                  <td title={describeWeatherCode(cp.weather.weather_code)}>{fmtTime(cp.eta)}</td>
                  <td className={cp.risk.drivers.includes("wind") ? "driver" : undefined}>
                    {Math.round(cp.weather.wind_mph)}
                    <small> g{Math.round(cp.weather.gust_mph)}</small>
                  </td>
                  <td className={cp.risk.drivers.includes("rain") ? "driver" : undefined}>{cp.weather.rain_in_hr.toFixed(2)}</td>
                  <td className={cp.risk.drivers.includes("snow") ? "driver" : undefined}>{cp.weather.snow_in_hr.toFixed(2)}</td>
                  <td>
                    <span className="pill" style={{ background: meta.color }}>
                      {meta.label}
                      {cp.risk.load_rule_applied && " ⚖"}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="footnote">Wind mph (g = gust) · rain/snow in/hr at the truck's ETA · ⚖ = raised by load rule</p>
    </section>
  );
});
