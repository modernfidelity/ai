import torch
from torchvision.models import RegNet_Y_400MF_Weights, regnet_y_400mf

model = regnet_y_400mf(weights=RegNet_Y_400MF_Weights.DEFAULT)  # ImageNet-pretrained
x = torch.randn(1, 3, 224, 224)
out = model(x)
print(out.shape)  # logits for 1000 classes (ImageNet)



from torchvision.models import (
    regnet_y_400mf, regnet_y_800mf, regnet_y_1_6gf,
    regnet_x_400mf, regnet_x_800mf
)
