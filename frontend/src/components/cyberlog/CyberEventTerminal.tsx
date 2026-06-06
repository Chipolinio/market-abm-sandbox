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
        CYBER-LOG
      </div>
      <div
        data-testid="cyber-log-scroll"
        className="flex flex-1 flex-col-reverse overflow-y-auto px-3 py-2 font-mono text-xs"
      >
        {lines.length === 0 ? (
          <div className="text-slate-500">Waiting for events…</div>
        ) : (
          lines.map((line) => (
            <div
              key={line.event_id}
              data-testid="cyber-log-line"
              className={severityClass(line)}
            >
              {formatCyberLine(line)}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
