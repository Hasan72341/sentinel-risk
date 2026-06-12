// Typed view models for the quant demo pages, plus adapters from the raw
// backend demo payloads. The pages render the view models only, so a change in
// a backend key shows up here (and in tsc) instead of as an empty chart.

type Matrix = number[][];

function round(value: number, digits = 4): number {
  const factor = 10 ** digits;
  return Math.round(value * factor) / factor;
}

function meanPath(paths: Matrix): number[] {
  if (!paths.length) return [];
  return paths[0].map((_, i) => paths.reduce((sum, path) => sum + (path[i] ?? 0), 0) / paths.length);
}

function nearestIndex(values: number[], target: number): number {
  let best = 0;
  values.forEach((value, i) => {
    if (Math.abs(value - target) < Math.abs(values[best] - target)) best = i;
  });
  return best;
}

/* ------------------------------------------------------------------ */
/*  Stochastic calculus                                                */
/* ------------------------------------------------------------------ */

interface RawStochasticDemo {
  demo_title: string;
  description: string;
  gbm_ito_simulation: {
    paths: Matrix;
    statistics: { mean_final_price: number; theoretical_mean: number };
    parameters: { n_paths: number; days: number };
  };
  heston_stochastic_volatility: {
    asset_paths: Matrix;
    volatility_paths: Matrix;
    parameters: { n_paths: number; days: number; v0: number; theta: number; kappa: number; xi: number };
  };
  option_greeks_surface: {
    spot_points: number[];
    time_points: number[];
    delta_call: Matrix;
    gamma: Matrix;
    theta_call: Matrix;
    vega: Matrix;
    rho_call: Matrix;
    parameters: { strike: number };
  };
  barrier_option_pricing: {
    price: number;
    std_error: number;
    barrier_hit_probability: number;
    vanilla_price: number;
    parameters: { barrier: number; barrier_type: string; option_type: string };
  };
  jump_diffusion_model: {
    jump_diffusion_paths: Matrix;
    gbm_comparison_paths: Matrix;
    parameters: { n_paths: number; days: number; jump_lambda: number; jump_mu: number; jump_sigma: number };
  };
}

export interface StochasticDemoView {
  demo_title: string;
  description: string;
  gbm: { sample_paths: Matrix; n_paths: number; days: number; mean_final_price: number; theoretical_mean: number };
  heston: {
    asset_paths: Matrix; vol_paths: Matrix; n_paths: number; days: number;
    v0: number; theta: number; kappa: number; xi: number;
  };
  /** Call Greeks at the spot nearest the strike, for the longest maturity on the grid. */
  greeks_summary: { delta: number; gamma: number; theta: number; vega: number; rho: number; spot: number; maturity_years: number };
  /** Call delta across spot for the longest maturity on the grid. */
  delta_surface: { spot_prices: number[]; delta: number[] };
  barrier: {
    option_type: string; barrier_level: number; price: number; vanilla_price: number;
    probability_hit: number; std_error: number;
  };
  jump_diffusion: {
    n_paths: number; days: number; jump_intensity: number; jump_mean: number; jump_std: number;
    jump_diffusion_avg_path: number[]; gbm_avg_path: number[];
  };
}

export function adaptStochasticDemo(raw: RawStochasticDemo): StochasticDemoView {
  const gbm = raw.gbm_ito_simulation;
  const heston = raw.heston_stochastic_volatility;
  const greeks = raw.option_greeks_surface;
  const barrier = raw.barrier_option_pricing;
  const jump = raw.jump_diffusion_model;
  const row = greeks.time_points.length - 1;
  const atm = nearestIndex(greeks.spot_points, greeks.parameters.strike);
  return {
    demo_title: raw.demo_title,
    description: raw.description,
    gbm: {
      sample_paths: gbm.paths,
      n_paths: gbm.parameters.n_paths,
      days: gbm.parameters.days,
      mean_final_price: gbm.statistics.mean_final_price,
      theoretical_mean: gbm.statistics.theoretical_mean,
    },
    heston: {
      asset_paths: heston.asset_paths,
      vol_paths: heston.volatility_paths,
      n_paths: heston.parameters.n_paths,
      days: heston.parameters.days,
      v0: heston.parameters.v0,
      theta: heston.parameters.theta,
      kappa: heston.parameters.kappa,
      xi: heston.parameters.xi,
    },
    greeks_summary: {
      delta: greeks.delta_call[row][atm],
      gamma: greeks.gamma[row][atm],
      theta: greeks.theta_call[row][atm],
      vega: greeks.vega[row][atm],
      rho: greeks.rho_call[row][atm],
      spot: greeks.spot_points[atm],
      maturity_years: greeks.time_points[row],
    },
    delta_surface: { spot_prices: greeks.spot_points, delta: greeks.delta_call[row] },
    barrier: {
      option_type: `${barrier.parameters.barrier_type} ${barrier.parameters.option_type}`,
      barrier_level: barrier.parameters.barrier,
      price: barrier.price,
      vanilla_price: barrier.vanilla_price,
      probability_hit: barrier.barrier_hit_probability,
      std_error: barrier.std_error,
    },
    jump_diffusion: {
      n_paths: jump.parameters.n_paths,
      days: jump.parameters.days,
      jump_intensity: jump.parameters.jump_lambda,
      jump_mean: jump.parameters.jump_mu,
      jump_std: jump.parameters.jump_sigma,
      jump_diffusion_avg_path: meanPath(jump.jump_diffusion_paths),
      gbm_avg_path: meanPath(jump.gbm_comparison_paths),
    },
  };
}

/* ------------------------------------------------------------------ */
/*  Network analysis                                                   */
/* ------------------------------------------------------------------ */

interface RawNetworkDemo {
  demo_info: { title: string; description: string };
  correlation_network: {
    network_stats: {
      n_nodes: number; n_edges: number; density: number;
      avg_clustering_coefficient: number; avg_path_length: number;
    };
    centrality_top5: { asset: string; degree_centrality: number; betweenness_centrality: number }[];
  };
  minimum_spanning_tree: {
    tree_stats: { n_edges: number; total_weight: number; max_edge_weight: number; min_edge_weight: number; diameter: number };
    edge_list: { source: string; target: string; distance: number }[];
  };
  contagion_simulation: {
    summary: { n_rounds_simulated: number; final_n_stressed: number; final_n_failed: number; total_system_loss_pct: number };
    too_big_to_fail_top5: { node: string; cascading_failures: number; systemic_impact_score: number }[];
    timeline_summary: { round: number; n_healthy: number; n_stressed: number; n_failed: number }[];
  };
  systemic_risk: {
    total_connectedness_index: number;
    top_srisk: { asset: string; srisk_score: number }[];
    top_mes: { asset: string; mes: number }[];
  };
}

export interface NetworkDemoView {
  demo_title: string;
  description: string;
  correlation_network: {
    n_assets: number; n_edges: number; density: number; avg_clustering: number; avg_path_length: number;
    degree_centrality: { asset: string; degree: number }[];
    betweenness_centrality: { asset: string; betweenness: number }[];
  };
  mst: {
    n_edges: number; total_weight: number; max_edge_weight: number; min_edge_weight: number; diameter: number;
    edges: { source: string; target: string; weight: number }[];
  };
  contagion: {
    n_rounds: number; initial_failed: number; total_failed: number; total_stressed: number; system_loss_pct: number;
    timeline: { round: number; healthy: number; stressed: number; failed: number }[];
    too_big_to_fail: { asset: string; cascading_failed: number; impact_score: number }[];
  };
  systemic_risk: {
    top_srisk_asset: string; top_mes_asset: string; connectedness_index: number;
    srisk_scores: { asset: string; srisk: number }[];
    mes_scores: { asset: string; mes: number }[];
  };
}

export function adaptNetworkDemo(raw: RawNetworkDemo): NetworkDemoView {
  const stats = raw.correlation_network.network_stats;
  const tree = raw.minimum_spanning_tree;
  const contagion = raw.contagion_simulation;
  const systemic = raw.systemic_risk;
  return {
    demo_title: raw.demo_info.title,
    description: raw.demo_info.description,
    correlation_network: {
      n_assets: stats.n_nodes,
      n_edges: stats.n_edges,
      density: stats.density,
      avg_clustering: stats.avg_clustering_coefficient,
      avg_path_length: stats.avg_path_length,
      degree_centrality: raw.correlation_network.centrality_top5.map((c) => ({ asset: c.asset, degree: c.degree_centrality })),
      betweenness_centrality: raw.correlation_network.centrality_top5.map((c) => ({ asset: c.asset, betweenness: c.betweenness_centrality })),
    },
    mst: {
      n_edges: tree.tree_stats.n_edges,
      total_weight: tree.tree_stats.total_weight,
      max_edge_weight: tree.tree_stats.max_edge_weight,
      min_edge_weight: tree.tree_stats.min_edge_weight,
      diameter: tree.tree_stats.diameter,
      edges: tree.edge_list.map((e) => ({ source: e.source, target: e.target, weight: e.distance })),
    },
    contagion: {
      n_rounds: contagion.summary.n_rounds_simulated,
      initial_failed: contagion.timeline_summary[0]?.n_failed ?? 0,
      total_failed: contagion.summary.final_n_failed,
      total_stressed: contagion.summary.final_n_stressed,
      system_loss_pct: contagion.summary.total_system_loss_pct,
      timeline: contagion.timeline_summary.map((t) => ({
        round: t.round, healthy: t.n_healthy, stressed: t.n_stressed, failed: t.n_failed,
      })),
      too_big_to_fail: contagion.too_big_to_fail_top5.map((t) => ({
        asset: t.node, cascading_failed: t.cascading_failures, impact_score: t.systemic_impact_score,
      })),
    },
    systemic_risk: {
      top_srisk_asset: systemic.top_srisk[0]?.asset ?? '—',
      top_mes_asset: systemic.top_mes[0]?.asset ?? '—',
      connectedness_index: systemic.total_connectedness_index,
      srisk_scores: systemic.top_srisk.map((s) => ({ asset: s.asset, srisk: s.srisk_score })),
      mes_scores: systemic.top_mes.map((m) => ({ asset: m.asset, mes: m.mes })),
    },
  };
}

/* ------------------------------------------------------------------ */
/*  Advanced optimisation                                              */
/* ------------------------------------------------------------------ */

interface RawPortfolioPoint { return: number; risk: number; sharpe: number }

interface RawAdvOptDemo {
  demo: string;
  assets: string[];
  sectors: Record<string, number[]>;
  socp_optimization: {
    optimal_weights: number[];
    expected_return: number;
    expected_risk: number;
    sharpe_ratio: number;
    constraint_report: Record<string, number | boolean>;
    convergence: { success: boolean };
  };
  robust_optimization: {
    parameters: { covariance_inflation: number };
    nominal_weights: number[];
    robust_weights: number[];
    nominal_metrics: { sharpe_ratio: number };
    robust_metrics: { expected_return: number; sharpe_ratio: number; worst_case_return: number };
  };
  hrp_optimization: {
    num_periods: number;
    hrp_weights: number[];
    dendrogram: { num_clusters: number };
    comparison: { equal_weight: { weights: number[] }; inverse_variance: { weights: number[] } };
  };
  pareto_frontier: {
    num_frontier_points: number;
    frontier: RawPortfolioPoint[];
    minimum_variance_portfolio: RawPortfolioPoint;
    max_sharpe_portfolio: RawPortfolioPoint;
    capital_market_line: { tangency_portfolio: RawPortfolioPoint };
  };
}

export interface AdvOptDemoView {
  demo_title: string;
  description: string;
  assets: { name: string; sector?: string }[];
  socp_optimization: {
    weights: number[];
    /** Percent. */
    expected_return: number;
    /** Percent. */
    expected_risk: number;
    sharpe_ratio: number;
    converged: boolean;
    constraint_violations: number;
  };
  robust_optimization: {
    nominal_weights: number[];
    robust_weights: number[];
    nominal_sharpe: number;
    robust_sharpe: number;
    /** Percent. */
    robust_return: number;
    /** Percent. */
    worst_case_return: number;
    /** Percent. */
    covariance_inflation_pct: number;
  };
  hrp: {
    weights: number[];
    equal_weights: number[];
    inverse_variance_weights: number[];
    n_clusters: number;
    n_periods: number;
  };
  pareto_frontier: {
    frontier: { risk: number; return: number }[];
    tangency_portfolio: { risk: number; return: number };
    min_variance_portfolio: { risk: number; return: number };
    n_points: number;
    /** Percent. */
    max_sharpe_portfolio_return: number;
    /** Percent. */
    min_var_portfolio_risk: number;
  };
}

// Counts the constraints the solver reports as not met.
function countViolations(report: Record<string, number | boolean>): number {
  const tolerance = 1e-6;
  let violations = 0;
  if (typeof report.sum_to_one === 'number' && Math.abs(report.sum_to_one - 1) > 1e-4) violations += 1;
  if (report.no_short_selling === false) violations += 1;
  if (report.turnover_satisfied === false) violations += 1;
  for (const [key, exposure] of Object.entries(report)) {
    if (!key.startsWith('sector_') || !key.endsWith('_exposure')) continue;
    const limit = report[key.replace(/_exposure$/, '_limit')];
    if (typeof exposure === 'number' && typeof limit === 'number' && exposure > limit + tolerance) violations += 1;
  }
  return violations;
}

export function adaptAdvOptDemo(raw: RawAdvOptDemo): AdvOptDemoView {
  const sectorOf: Record<number, string> = {};
  for (const [sector, indices] of Object.entries(raw.sectors)) {
    indices.forEach((index) => { sectorOf[index] = sector; });
  }
  const socp = raw.socp_optimization;
  const robust = raw.robust_optimization;
  const hrp = raw.hrp_optimization;
  const pareto = raw.pareto_frontier;
  const pct = (value: number) => round(value * 100, 2);
  return {
    demo_title: 'Advanced Optimization',
    description: raw.demo,
    assets: raw.assets.map((name, i) => ({ name, sector: sectorOf[i] })),
    socp_optimization: {
      weights: socp.optimal_weights,
      expected_return: pct(socp.expected_return),
      expected_risk: pct(socp.expected_risk),
      sharpe_ratio: socp.sharpe_ratio,
      converged: socp.convergence.success,
      constraint_violations: countViolations(socp.constraint_report),
    },
    robust_optimization: {
      nominal_weights: robust.nominal_weights,
      robust_weights: robust.robust_weights,
      nominal_sharpe: robust.nominal_metrics.sharpe_ratio,
      robust_sharpe: robust.robust_metrics.sharpe_ratio,
      robust_return: pct(robust.robust_metrics.expected_return),
      worst_case_return: pct(robust.robust_metrics.worst_case_return),
      covariance_inflation_pct: pct(robust.parameters.covariance_inflation),
    },
    hrp: {
      weights: hrp.hrp_weights,
      equal_weights: hrp.comparison.equal_weight.weights,
      inverse_variance_weights: hrp.comparison.inverse_variance.weights,
      n_clusters: hrp.dendrogram.num_clusters,
      n_periods: hrp.num_periods,
    },
    pareto_frontier: {
      frontier: pareto.frontier.map((p) => ({ risk: p.risk, return: p.return })),
      tangency_portfolio: {
        risk: pareto.capital_market_line.tangency_portfolio.risk,
        return: pareto.capital_market_line.tangency_portfolio.return,
      },
      min_variance_portfolio: { risk: pareto.minimum_variance_portfolio.risk, return: pareto.minimum_variance_portfolio.return },
      n_points: pareto.num_frontier_points,
      max_sharpe_portfolio_return: pct(pareto.max_sharpe_portfolio.return),
      min_var_portfolio_risk: pct(pareto.minimum_variance_portfolio.risk),
    },
  };
}

/* ------------------------------------------------------------------ */
/*  Causal inference                                                   */
/* ------------------------------------------------------------------ */

type NullableMatrix = (number | null)[][];

interface RawCausalDemo {
  summary: {
    demo_name: string; n_days: number; n_variables: number;
    known_causal_links: string[]; granger_links_recovered: string;
  };
  granger_causality: {
    optimal_lag: { selected: number };
    /** [effect][cause] */
    causality_pvalues: NullableMatrix;
    significant_links: unknown[];
    n_variables: number;
    variable_names: string[];
  };
  impulse_response: {
    n_lags: number;
    horizon: number;
    /** [period][response][shock] */
    irf: number[][][];
    variable_names: string[];
  };
  transfer_entropy: { source: string; target: string; te_x_to_y: number; p_value: number }[];
  mutual_information: { n_variables: number; mi_matrix: Matrix; variable_names: string[] };
  causal_discovery: {
    n_variables: number;
    directed_edges: number;
    edges: { from: number; to: number; type: string }[];
    variable_names: string[];
  };
}

export interface CausalDemoView {
  demo_title: string;
  description: string;
  granger_causality: {
    n_variables: number;
    optimal_lag: number;
    significant_links: number;
    /** matrix[cause][effect] p-values; null on the diagonal. */
    causality_matrix: { variables: string[]; matrix: NullableMatrix };
  };
  impulse_response: {
    n_lags: number;
    horizon: number;
    irf_results: { response_var: string; shock_var: string; values: number[] }[];
  };
  transfer_entropy: {
    n_pairs: number; max_te: number; significant_directions: number;
    pairs: { source: string; target: string; te: number; p_value: number }[];
  };
  mutual_information: {
    n_variables: number; max_mi: number; avg_mi: number;
    pairs: { var1: string; var2: string; mi: number }[];
  };
  causal_discovery: {
    n_nodes: number; n_edges: number; n_directed: number;
    edges: { source: string; target: string; type: string }[];
  };
}

const IRF_SERIES_SHOWN = 5;

export function adaptCausalDemo(raw: RawCausalDemo): CausalDemoView {
  const granger = raw.granger_causality;
  const irf = raw.impulse_response;
  const mi = raw.mutual_information;
  const discovery = raw.causal_discovery;

  // The API stores p-values as [effect][cause]; the table reads cause by row.
  const names = granger.variable_names;
  const byCause: NullableMatrix = names.map((_, cause) => names.map((__, effect) => granger.causality_pvalues[effect]?.[cause] ?? null));

  // Cross-variable responses with the largest peak, so the chart stays readable.
  const responses: CausalDemoView['impulse_response']['irf_results'] = [];
  irf.variable_names.forEach((responseVar, i) => {
    irf.variable_names.forEach((shockVar, j) => {
      if (i === j) return;
      responses.push({ response_var: responseVar, shock_var: shockVar, values: irf.irf.map((period) => period[i][j]) });
    });
  });
  const peak = (values: number[]) => Math.max(...values.map(Math.abs));
  responses.sort((a, b) => peak(b.values) - peak(a.values));

  const miPairs: CausalDemoView['mutual_information']['pairs'] = [];
  mi.variable_names.forEach((var1, i) => {
    mi.variable_names.forEach((var2, j) => {
      if (j > i) miPairs.push({ var1, var2, mi: mi.mi_matrix[i][j] });
    });
  });
  const miValues = miPairs.map((p) => p.mi);

  const tePairs = raw.transfer_entropy.map((t) => ({ source: t.source, target: t.target, te: t.te_x_to_y, p_value: t.p_value }));

  return {
    demo_title: raw.summary.demo_name,
    description: `${raw.summary.n_days} simulated days, ${raw.summary.n_variables} variables. `
      + `Known lagged links recovered by the Granger test: ${raw.summary.granger_links_recovered}.`,
    granger_causality: {
      n_variables: granger.n_variables,
      optimal_lag: granger.optimal_lag.selected,
      significant_links: granger.significant_links.length,
      causality_matrix: { variables: names, matrix: byCause },
    },
    impulse_response: { n_lags: irf.n_lags, horizon: irf.horizon, irf_results: responses.slice(0, IRF_SERIES_SHOWN) },
    transfer_entropy: {
      n_pairs: tePairs.length,
      max_te: tePairs.length ? round(Math.max(...tePairs.map((p) => p.te))) : 0,
      significant_directions: tePairs.filter((p) => p.p_value <= 0.05).length,
      pairs: tePairs,
    },
    mutual_information: {
      n_variables: mi.n_variables,
      max_mi: miValues.length ? round(Math.max(...miValues)) : 0,
      avg_mi: miValues.length ? round(miValues.reduce((sum, v) => sum + v, 0) / miValues.length) : 0,
      pairs: miPairs,
    },
    causal_discovery: {
      n_nodes: discovery.n_variables,
      n_edges: discovery.edges.length,
      n_directed: discovery.directed_edges,
      edges: discovery.edges.map((e) => ({
        source: discovery.variable_names[e.from] ?? String(e.from),
        target: discovery.variable_names[e.to] ?? String(e.to),
        type: e.type,
      })),
    },
  };
}
