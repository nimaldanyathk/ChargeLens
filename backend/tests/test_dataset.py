"""Dataset generator invariants: reproducibility, split hygiene, balance."""

import pandas as pd

from riskmodel.generate import SCENARIOS, GenConfig, generate, split_by_customer


def test_reproducible():
    a = generate(GenConfig(n_cases=200, seed=99))
    b = generate(GenConfig(n_cases=200, seed=99))
    pd.testing.assert_frame_equal(a, b)


def test_different_seed_differs():
    a = generate(GenConfig(n_cases=200, seed=1))
    b = generate(GenConfig(n_cases=200, seed=2))
    assert not a.equals(b)


def test_no_customer_overlap_between_splits():
    df = generate(GenConfig(n_cases=2000, seed=5))
    df["split"] = split_by_customer(df, 5)
    by_split = df.groupby("split")["customer_id"].apply(set)
    assert not (by_split["train"] & by_split["test"])
    assert not (by_split["train"] & by_split["val"])
    assert not (by_split["val"] & by_split["test"])


def test_class_balance_reasonable():
    df = generate(GenConfig(n_cases=3000, seed=3))
    rate = df["label_abusive"].mean()
    assert 0.25 < rate < 0.55


def test_labels_follow_scenarios_with_noise():
    df = generate(GenConfig(n_cases=3000, seed=4))
    clean_label = df["scenario"].map(lambda s: SCENARIOS[s][0])
    flip_rate = (df["label_abusive"] != clean_label).mean()
    assert 0.01 < flip_rate < 0.06  # ~3% label noise


def test_distributions_overlap():
    """The problem must not be trivially separable on any single field."""
    df = generate(GenConfig(n_cases=4000, seed=6))
    delivered = df["delivery_status"] == "delivered"
    # delivered packages exist in BOTH classes
    assert df[delivered]["label_abusive"].nunique() == 2
    assert df[~delivered]["label_abusive"].nunique() == 2
    # confirmed deliveries also exist for legitimate disputes (mis-delivery)
    confirmed = df["delivery_confirmation"].isin(["signed", "otp", "photo"])
    assert (df[confirmed & (df["label_abusive"] == 0)]).shape[0] > 0
