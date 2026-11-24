# notebooks

Jupyter notebooks working through deep learning fundamentals with PyTorch.

| Notebook | Topic |
|---|---|
| `tensors.ipynb` | Tensor basics |
| `tensor_tutorial.ipynb` | Tensors in more depth: initialization, operations, NumPy interop |
| `perceptron.ipynb` | A single perceptron, visualised with Graphviz |
| `neural_networks.ipynb` | The same classifier with 0 to 4 hidden layers (0 = logistic regression) |
| `object_detection_torchvision.ipynb` | Pretrained Faster R-CNN object detection on a webcam feed (OpenCV) |

The PNGs are network diagrams generated while working through these notebooks.

`tensor_tutorial.ipynb` is based on PyTorch's [Tensors tutorial](https://pytorch.org/tutorials/beginner/basics/tensorqs_tutorial.html) (BSD-3-Clause, © PyTorch contributors).

## Setup

```bash
cd notebooks
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/jupyter lab
```

`perceptron.ipynb` also needs the Graphviz system binary (`brew install graphviz`).
