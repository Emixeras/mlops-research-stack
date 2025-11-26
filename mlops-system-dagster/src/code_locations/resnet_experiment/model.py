import torch
import torch.nn as nn
import torchvision.models as models
from torchvision.models import ResNet18_Weights, ResNet50_Weights
import mlflow.pyfunc
from .dataset import get_transforms
from mlops_system_dagster.core_utils.preprocessing import coerce_images

def build_resnet_regressor(resnet_type='resnet18', pretrained=True, freeze_layers=True):
    # Load a pretrained ResNet
    weights = None
    if resnet_type == 'resnet18':
        if pretrained:
            weights = ResNet18_Weights.DEFAULT
        backbone = models.resnet18(weights=weights)
        num_features = backbone.fc.in_features
    elif resnet_type == 'resnet50':
        if pretrained:
            weights = ResNet50_Weights.DEFAULT
        backbone = models.resnet50(weights=weights)
        num_features = backbone.fc.in_features
    else:
        raise ValueError('Only resnet18 and resnet50 are supported')

    # Optionally freeze early layers
    if freeze_layers:
        for param in backbone.parameters():
            param.requires_grad = False
        # Unfreeze the final block and fc layer
        for param in backbone.layer4.parameters():
            param.requires_grad = True
        for param in backbone.fc.parameters():
            param.requires_grad = True

    # Replace the classification head with a regression head
    backbone.fc = nn.Sequential(
        nn.Linear(num_features, 128),
        nn.ReLU(),
        nn.Linear(128, 1)
    )
    return backbone

class ResNetBiomassModel(mlflow.pyfunc.PythonModel):
    def __init__(self, model):
        self.model = model
        self.transform = None

    def load_context(self, context):
        # Model is already loaded via pickle
        self.model.eval()
        self.transform = get_transforms(img_size=224)

    def predict(self, context, model_input):
        """
        Predicts biomass from images.
        model_input: List of file paths or bytes.
        """
        if self.transform is None:
            self.transform = get_transforms(img_size=224)

        device = torch.device('cpu')
        self.model.to(device)
        
        # Use shared utility to handle input (paths, bytes, etc.)
        # ResNet needs RGB images
        config = {"image_mode": "RGB", "image_size": (224, 224)} 
        images = coerce_images(model_input, config=config)
        
        preds = []
        with torch.no_grad():
            for img in images:
                input_tensor = self.transform(img).unsqueeze(0).to(device)
                output = self.model(input_tensor)
                preds.append(output.item())
        return preds
