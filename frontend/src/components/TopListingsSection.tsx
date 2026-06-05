import { DenseMultiLineChart } from "@/components/DenseMultiLineChart";
import {
  downsampleListingWide,
  hasPlottableListingWide,
  listingLineKey,
  pivotListingMetricsToWide,
} from "@/state/listingSeries";
import type { ListingSeriesData } from "@/state/types";

type Props = {
  listings: ListingSeriesData[];
  loading: boolean;
};

function buildSeriesMeta(listings: ListingSeriesData[]) {
  return listings.map((l) => ({
    dataKey: listingLineKey(l.listing_id),
    label: `SKU ${l.listing_id}`,
  }));
}

function DenseMetricCard({
  title,
  listings,
  metric,
  emptyMessage,
}: {
  title: string;
  listings: ListingSeriesData[];
  metric: "price" | "gmv" | "volume";
  emptyMessage: string;
}) {
  const series = buildSeriesMeta(listings);
  const wide = downsampleListingWide(pivotListingMetricsToWide(listings, metric));
  const keys = series.map((s) => s.dataKey);
  const showChart = hasPlottableListingWide(wide, keys);

  return (
    <div className="chart-card dense-chart-card">
      <h3>{title}</h3>
      <DenseMultiLineChart
        data={showChart ? wide : []}
        series={showChart ? series : []}
        emptyMessage={emptyMessage}
      />
    </div>
  );
}

export function TopListingsSection({ listings, loading }: Props) {
  if (loading) {
    return (
      <section className="dense-section">
        <h2 className="dense-section-title">Top SKU (dense)</h2>
        <p className="backfill-status">Loading top listings…</p>
      </section>
    );
  }

  if (listings.length === 0) {
    return (
      <section className="dense-section">
        <h2 className="dense-section-title">Top SKU (dense)</h2>
        <p className="chart-empty">No listing data yet — start simulation with Parquet persistence.</p>
      </section>
    );
  }

  return (
    <section className="dense-section">
      <h2 className="dense-section-title">Top SKU by GMV (max 10 series, cap 600 ticks)</h2>
      <div className="dense-charts-grid">
        <DenseMetricCard
          title="Price by listing"
          listings={listings}
          metric="price"
          emptyMessage="Waiting for listing prices…"
        />
        <DenseMetricCard
          title="GMV by listing"
          listings={listings}
          metric="gmv"
          emptyMessage="Waiting for listing GMV…"
        />
        <DenseMetricCard
          title="Volume by listing"
          listings={listings}
          metric="volume"
          emptyMessage="Waiting for listing volume…"
        />
      </div>
    </section>
  );
}
