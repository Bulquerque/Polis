from __future__ import annotations
import itertools, math
from decimal import Decimal
from statistics import NormalDist
from .models_qualification import StatisticalDiagnostics, StatisticalEvidence

def _moments(values: tuple[Decimal, ...]) -> tuple[float, float, float, float]:
    xs = [float(v) for v in values]
    n = len(xs)
    mean = sum(xs) / n
    centered = [x - mean for x in xs]
    var = sum(x*x for x in centered) / (n-1)
    std = math.sqrt(var)
    if std == 0:
        return mean, std, 0.0, 3.0
    skew = (n / ((n-1)*(n-2))) * sum((x/std)**3 for x in centered) if n > 2 else 0.0
    kurt = (sum((x/std)**4 for x in centered) / n) if n > 3 else 3.0
    return mean, std, skew, kurt

def _sharpe(values: tuple[Decimal, ...], periods: int) -> float | None:
    if len(values) < 2:
        return None
    mean, std, _, _ = _moments(values)
    return None if std == 0 else mean / std * math.sqrt(periods)

def _expected_max_sharpe(trials: tuple[Decimal, ...]) -> float:
    if len(trials) <= 1:
        return 0.0
    xs = [float(v) for v in trials]
    mean = sum(xs)/len(xs)
    std = math.sqrt(sum((x-mean)**2 for x in xs)/(len(xs)-1))
    if std == 0:
        return mean
    n = len(xs)
    gamma = 0.5772156649015329
    normal = NormalDist()
    z1 = normal.inv_cdf(1 - 1/n)
    z2 = normal.inv_cdf(1 - 1/(n*math.e))
    return mean + std*((1-gamma)*z1 + gamma*z2)

def deflated_sharpe_ratio(evidence: StatisticalEvidence) -> Decimal | None:
    n = len(evidence.returns)
    sr = _sharpe(evidence.returns, evidence.periods_per_year)
    if sr is None or n < 3:
        return None
    _, _, skew, kurt = _moments(evidence.returns)
    benchmark = _expected_max_sharpe(evidence.trial_sharpes)
    denom_sq = 1 - skew*sr + ((kurt-1)/4)*(sr**2)
    if denom_sq <= 0:
        return Decimal("0")
    z = (sr-benchmark)*math.sqrt(n-1)/math.sqrt(denom_sq)
    return Decimal(str(NormalDist().cdf(z)))

def _column_sharpe(matrix: tuple[tuple[Decimal, ...], ...], rows: tuple[int, ...], col: int) -> float:
    values = tuple(matrix[row][col] for row in rows)
    result = _sharpe(values, 1)
    return float("-inf") if result is None else result

def probability_backtest_overfitting(evidence: StatisticalEvidence) -> Decimal | None:
    matrix = evidence.strategy_returns
    if len(matrix) < 4 or not matrix or len(matrix[0]) < 2 or len(matrix) % 2:
        return None
    width = len(matrix[0])
    if any(len(row) != width for row in matrix):
        return None
    blocks = min(6, len(matrix))
    if blocks % 2:
        blocks -= 1
    block_size = len(matrix)//blocks
    block_rows = [tuple(range(i*block_size, (i+1)*block_size)) for i in range(blocks)]
    logits: list[float] = []
    combos = list(itertools.combinations(range(blocks), blocks//2))[:64]
    for combo in combos:
        ins = tuple(i for b in combo for i in block_rows[b])
        outs = tuple(i for b in range(blocks) if b not in combo for i in block_rows[b])
        in_scores = [_column_sharpe(matrix, ins, c) for c in range(width)]
        winner = max(range(width), key=in_scores.__getitem__)
        out_scores = [_column_sharpe(matrix, outs, c) for c in range(width)]
        rank = sorted(out_scores).index(out_scores[winner]) + 1
        relative = rank/(width+1)
        logits.append(math.log(relative/(1-relative)))
    return Decimal(str(sum(value <= 0 for value in logits)/len(logits))) if logits else None

def build_diagnostics(evidence: StatisticalEvidence) -> StatisticalDiagnostics:
    sr = _sharpe(evidence.returns, evidence.periods_per_year)
    dsr = deflated_sharpe_ratio(evidence)
    pbo = probability_backtest_overfitting(evidence)
    return StatisticalDiagnostics(observation_count=len(evidence.returns),
        sharpe_ratio=None if sr is None else Decimal(str(sr)),
        deflated_sharpe_ratio=dsr, probability_backtest_overfitting=pbo)
