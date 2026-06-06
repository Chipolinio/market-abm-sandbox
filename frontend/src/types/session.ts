/** Session configure DTO (Spec 009 §3.1). */

export type SellerMixConfig = {
  catboost_pct: number;
  rule_based_pct: number;
  basic_pct: number;
};

export type SessionConfigureRequest = {
  n_buyers: number;
  seller_mix: SellerMixConfig;
  seed?: number | null;
};

export type SessionConfigureResponse = {
  status: string;
  n_buyers: number;
};
