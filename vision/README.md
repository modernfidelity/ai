# vision

Computer vision experiments with [RegNet](https://arxiv.org/abs/2003.13678) image classification models.

| Script | What it does |
|---|---|
| `regnets.py` | Loads torchvision's ImageNet-pretrained `regnet_y_400mf` and runs a dummy image through it (outputs 1000 class logits) |
| `regnets_scratch.py` | A simplified RegNet-style network built from scratch (bottleneck blocks, 3 stages) |

## Setup

```bash
cd vision
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python regnets.py
```

## Background

Notes started from MIT 6.S191 *Introduction to Deep Learning*, Lecture 1: <http://introtodeeplearning.com>
