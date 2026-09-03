from __future__ import annotations
import numpy as np
import pandas as pd


def rolling_sum(series:pd.Series,window:int) -> pd.Series:
    if window<1: raise ValueError("window must be >=1")
    return series.rolling(window,min_periods=window).sum()


def robust_zscore(series:pd.Series,window:int) -> pd.Series:
    if window<3: raise ValueError("robust window must be >=3")
    median=series.rolling(window,min_periods=window).median()
    mad=(series-median).abs().rolling(window,min_periods=window).median()
    scale=mad.mul(1.4826).where(mad>0)
    return series.sub(median).div(scale)


def aligned_frame(index, mapping:dict[str,pd.Series]) -> pd.DataFrame:
    return pd.DataFrame({k:v.reindex(index) for k,v in mapping.items()},index=index)
