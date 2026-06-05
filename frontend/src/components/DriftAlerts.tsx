import { useState } from "react";

type Props = {
  alerts: Array<Record<string, unknown>>;
};

export function DriftAlerts({ alerts }: Props) {
  const [open, setOpen] = useState(false);

  if (alerts.length === 0) {
    return null;
  }

  return (
    <section className="drift-alerts">
      <button type="button" className="drift-toggle" onClick={() => setOpen((v) => !v)}>
        Drift Alerts ({alerts.length}) {open ? "▾" : "▸"}
      </button>
      {open ? (
        <ul>
          {alerts.map((alert, idx) => (
            <li key={idx}>
              <code>{JSON.stringify(alert)}</code>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
