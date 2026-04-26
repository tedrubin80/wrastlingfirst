---
title: Ringside Predictor
emoji: 🤼
colorFrom: red
colorTo: gray
sdk: gradio
sdk_version: "4.44.0"
app_file: app.py
pinned: true
license: apache-2.0
short_description: Predict pro wrestling outcomes from booking patterns
tags:
  - sports
  - wrestling
  - tabular-classification
  - xgboost
  - kayfabe
models:
  - datamatters24/ringside-match-winner
datasets:
  - datamatters24/ringside-analytics
---

# Ringside Predictor

Interactive demo for the [Ringside Analytics match-winner model](https://huggingface.co/datamatters24/ringside-match-winner) — pick two wrestlers, set the match context, get a win probability.

## What it does

- Loads `xgboost.joblib` + `scaler.joblib` from the model repo
- Loads pre-computed snapshots of 500 wrestlers' current state from `data/`
- Builds a 35-feature row at request time and returns `predict_proba`
- Shows top contributing features so you can see why the model leans the way it does

## What it cannot do

Pro wrestling outcomes are **scripted**. The model learns booking patterns, not athletic ability. **Not for betting.**

The companion paper at <https://tedrubin80.github.io/wrastlingfirst/paper.html> walks through what this means in practice.

## Resources

- 📊 [Dataset on HF](https://huggingface.co/datasets/datamatters24/ringside-analytics)
- 🎯 [Model on HF](https://huggingface.co/datamatters24/ringside-match-winner)
- 💻 [Source code](https://github.com/tedrubin80/wrastlingfirst)
- 📝 [Paper / portfolio](https://tedrubin80.github.io/wrastlingfirst/)
