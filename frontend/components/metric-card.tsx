import type { MetricCard as MetricCardType } from "@/lib/types";

export function MetricCard({ metric }: { metric: MetricCardType }) {
  return (
    <div className="panel metric-card">
      <div className="label">{metric.label}</div>
      <div className="value">{metric.value}</div>
      {metric.delta ? <div className="delta">{metric.delta}</div> : null}
    </div>
  );
}
