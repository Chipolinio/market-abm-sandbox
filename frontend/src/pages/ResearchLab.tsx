import { useCallback, useEffect, useMemo, useState } from "react";

import {
  fetchCurrentJob,
  fetchExperimentSummary,
  fetchJob,
  postExperimentRun,
} from "@/api/experiments";
import type {
  ExperimentPreset,
  ExperimentRunRequest,
  ExperimentSummaryRow,
  JobStatus,
} from "@/types/experiments";
import { PAPER_PRESET, SMOKE_PRESET } from "@/types/experiments";

const METRIC_LABELS: Record<string, string> = {
  consumer_surplus_proxy: "Излишек потребителя (proxy)",
  producer_surplus: "Излишек производителя",
  platform_profit: "Прибыль платформы",
  gmv: "GMV",
  hhi: "HHI",
  median_price: "Медианная цена",
  n_tx: "Число транзакций",
  price_std: "Стд. откл. цены",
};

const WINDOW_LABELS: Record<string, string> = {
  post_burn_in: "после прогрева",
  full: "весь период",
};

const STATUS_LABELS: Record<string, string> = {
  QUEUED: "В очереди",
  RUNNING: "Выполняется",
  DONE: "Готово",
  FAILED: "Ошибка",
};

function metricLabel(metric: string): string {
  return METRIC_LABELS[metric] ?? metric;
}

function windowLabel(window: string): string {
  return WINDOW_LABELS[window] ?? window;
}

function statusLabel(status: string): string {
  return STATUS_LABELS[status] ?? status;
}

function newExperimentId(): string {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `exp_${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}_${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`;
}

function applyPreset(preset: ExperimentPreset): Omit<ExperimentRunRequest, "experiment_id"> {
  if (preset === "paper") {
    return { ...PAPER_PRESET };
  }
  if (preset === "smoke") {
    return { ...SMOKE_PRESET };
  }
  return { ...SMOKE_PRESET, preset: "custom" };
}

type ConfirmFn = (message: string) => boolean;

type Props = {
  /** Injected for Vitest — defaults to window.confirm. */
  confirmFn?: ConfirmFn;
  /** Injected poll interval ms (default 2000). */
  pollIntervalMs?: number;
};

/** Spec 015.1 — Launch + status poll + summary results (thin client). */
export function ResearchLab({
  confirmFn = (msg) => window.confirm(msg),
  pollIntervalMs = 2000,
}: Props) {
  const [preset, setPreset] = useState<ExperimentPreset>("smoke");
  const [experimentId, setExperimentId] = useState(newExperimentId);
  const [form, setForm] = useState(() => applyPreset("smoke"));
  const [job, setJob] = useState<JobStatus | null>(null);
  const [summaryRows, setSummaryRows] = useState<ExperimentSummaryRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [launching, setLaunching] = useState(false);

  const running = job?.status === "RUNNING";

  const loadSummary = useCallback(async (id: string) => {
    try {
      const res = await fetchExperimentSummary(id);
      setSummaryRows(res.rows);
      setExperimentId(res.experiment_id);
    } catch {
      setSummaryRows([]);
    }
  }, []);

  // Mount recovery: if a job is still RUNNING, resume poll UI.
  useEffect(() => {
    let cancelled = false;
    void fetchCurrentJob()
      .then((res) => {
        if (cancelled || !res.job) {
          return;
        }
        setJob(res.job);
        if (res.job.status === "DONE") {
          void loadSummary(res.job.experiment_id);
        }
      })
      .catch(() => {
        /* idle */
      });
    return () => {
      cancelled = true;
    };
  }, [loadSummary]);

  // Poll while RUNNING.
  useEffect(() => {
    if (!job || job.status !== "RUNNING") {
      return;
    }
    const handle = window.setInterval(() => {
      void fetchJob(job.job_id)
        .then((next) => {
          setJob(next);
          if (next.status === "DONE") {
            void loadSummary(next.experiment_id);
          }
          if (next.status === "FAILED") {
            setError(next.error ?? "Задача эксперимента завершилась с ошибкой");
          }
        })
        .catch((err: unknown) => {
          setError(err instanceof Error ? err.message : "Ошибка опроса статуса");
        });
    }, pollIntervalMs);
    return () => window.clearInterval(handle);
  }, [job, loadSummary, pollIntervalMs]);

  const tickEstimate = useMemo(() => {
    return form.n_runs * form.ml_share_grid.length * form.n_ticks;
  }, [form]);

  const onPresetChange = (next: ExperimentPreset) => {
    setPreset(next);
    setForm(applyPreset(next));
  };

  const onLaunch = async () => {
    setError(null);
    if (preset === "paper") {
      const ok = confirmFn(
        `Paper-сетка выполнит примерно ${tickEstimate.toLocaleString("ru-RU")} тик-симуляций в фоне на этой машине. Продолжить?`,
      );
      if (!ok) {
        return;
      }
    }
    const body: ExperimentRunRequest = {
      experiment_id: experimentId,
      ...form,
      preset,
    };
    setLaunching(true);
    try {
      const accepted = await postExperimentRun(body);
      setJob({
        job_id: accepted.job_id,
        experiment_id: accepted.experiment_id,
        status: accepted.status,
        done: 0,
        total: form.n_runs * form.ml_share_grid.length,
      });
      setSummaryRows([]);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Не удалось запустить эксперимент");
    } finally {
      setLaunching(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 p-6 text-slate-900">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">Лаборатория исследований</h1>
        <p className="text-sm text-slate-600">
          Сравнение сценариев с разной долей ML-продавцов: запуск сетки прогонов и сводка метрик.
        </p>
      </header>

      <section className="mb-6 max-w-xl space-y-3 rounded border border-slate-200 bg-white p-4">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
          Запуск эксперимента
        </h2>
        <label className="block text-sm">
          Пресет
          <select
            className="mt-1 w-full rounded border border-slate-300 px-2 py-1"
            value={preset}
            disabled={running || launching}
            onChange={(e) => onPresetChange(e.target.value as ExperimentPreset)}
          >
            <option value="smoke">Smoke (быстрый)</option>
            <option value="paper">Paper (30×5×500)</option>
            <option value="custom">Свой</option>
          </select>
        </label>
        <label className="block text-sm">
          ID эксперимента
          <input
            className="mt-1 w-full rounded border border-slate-300 px-2 py-1 font-mono text-sm"
            value={experimentId}
            disabled={running || launching}
            onChange={(e) => setExperimentId(e.target.value)}
          />
        </label>
        <p className="text-xs text-slate-500">
          Оценка: {form.n_runs} прогонов × {form.ml_share_grid.length} долей × {form.n_ticks}{" "}
          тиков ≈ {tickEstimate.toLocaleString("ru-RU")} тик-симуляций
        </p>
        <button
          type="button"
          className="rounded bg-slate-900 px-3 py-2 text-sm text-white disabled:opacity-40"
          disabled={running || launching}
          onClick={() => void onLaunch()}
        >
          {launching ? "Запуск…" : "Запустить"}
        </button>
        {error ? (
          <p className="text-sm text-red-700" role="alert">
            {error}
          </p>
        ) : null}
      </section>

      {job ? (
        <section
          className="mb-6 max-w-xl rounded border border-slate-200 bg-white p-4"
          data-testid="job-status"
        >
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
            Статус задачи
          </h2>
          <p className="mt-2 font-mono text-sm">
            {statusLabel(job.status)} {job.done} / {job.total} прогонов — {job.experiment_id}
          </p>
          {job.error ? <p className="text-sm text-red-700">{job.error}</p> : null}
        </section>
      ) : null}

      <section className="overflow-x-auto rounded border border-slate-200 bg-white">
        <h2 className="border-b border-slate-200 bg-slate-100 px-3 py-2 text-sm font-semibold">
          Результаты{" "}
          {experimentId ? <span className="font-mono font-normal">({experimentId})</span> : null}
        </h2>
        <table className="min-w-full text-left text-sm">
          <thead className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-600">
            <tr>
              <th className="px-3 py-2">метрика</th>
              <th className="px-3 py-2">доля ML</th>
              <th className="px-3 py-2">окно</th>
              <th className="px-3 py-2">среднее</th>
              <th className="px-3 py-2">нижняя</th>
              <th className="px-3 py-2">верхняя</th>
            </tr>
          </thead>
          <tbody>
            {summaryRows.length === 0 ? (
              <tr>
                <td className="px-3 py-3 text-slate-500" colSpan={6}>
                  Сводки пока нет — запустите smoke или дождитесь завершения задачи.
                </td>
              </tr>
            ) : (
              summaryRows.map((row) => (
                <tr
                  key={`${row.metric}-${row.ml_share}-${row.window}`}
                  className="border-b border-slate-100"
                >
                  <td className="px-3 py-2" title={row.metric}>
                    {metricLabel(row.metric)}
                  </td>
                  <td className="px-3 py-2">{row.ml_share}</td>
                  <td className="px-3 py-2">{windowLabel(row.window)}</td>
                  <td className="px-3 py-2">{row.mean}</td>
                  <td className="px-3 py-2">{row.lo}</td>
                  <td className="px-3 py-2">{row.hi}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </section>
    </div>
  );
}
