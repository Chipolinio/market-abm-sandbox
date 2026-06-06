import {
  formatCyberLine,
  severityClass,
  type CyberLogLine,
} from "@/state/cyberLog";

type Props = {
  lines: CyberLogLine[];
};

export function CyberEventTerminal({ lines }: Props) {
  return (
    <div className="flex h-full flex-col bg-slate-950">
      <div className="shrink-0 border-b border-slate-800 px-3 py-2 text-xs font-semibold uppercase tracking-wider text-slate-400">
        System Terminals / Cyber Log
      </div>
      <div
        data-testid="cyber-log-scroll"
        className="flex flex-grow flex-col-reverse space-y-1 overflow-y-auto p-2 font-mono text-xs"
      >
        {lines.length === 0 ? (
          <div className="text-slate-600">Waiting for events…</div>
        ) : (
          lines.map((line) => (
            <div
              key={line.event_id}
              data-testid="cyber-log-line"
              className={severityClass(line.severity)}
            >
              {formatCyberLine(line)}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
