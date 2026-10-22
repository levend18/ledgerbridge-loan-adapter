export type Kind = "RETAIL" | "COMMERCIAL";
export type Dataset = "credit" | "payment_plan";
export type Session = { access: string; tenant: string; username: string };
export type Row = Record<string, string | number | boolean | null>;
export type Snapshot = {
  batch_id: string;
  source_version: number;
  published_at: string;
  row_count: number;
  row_counts: Record<string, number>;
};
export type Page = {
  results: Row[];
  next_cursor: string | null;
  snapshot: Snapshot;
};
export type Run = {
  id: string;
  loan_type: Kind;
  status: string;
  trigger: string;
  source_version: number;
  counts: Record<string, number>;
  issues_summary: Record<string, number>;
  duration_ms: number;
  created_at: string;
  error: string;
};
export type Stats = {
  count: number;
  null_ratio: number;
  min?: string | number | null;
  max?: string | number | null;
  mean?: number | null;
  stddev?: number | null;
  distinct_count?: number | null;
  most_frequent?: string | null;
  high_cardinality?: boolean;
  top?: { value: string; count: number }[];
};
export type Profile = {
  snapshot: Snapshot;
  datasets: Record<Dataset, Record<string, Stats>>;
};
