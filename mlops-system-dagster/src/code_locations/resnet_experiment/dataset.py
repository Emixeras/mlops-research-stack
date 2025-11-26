import os
import pandas as pd
from PIL import Image
import torch
from torch.utils.data import Dataset
import torchvision.transforms as transforms

class BiomassImageDataset(Dataset):
    def __init__(self, df, img_dir, target_col, transform=None):
        self.df = df.reset_index(drop=True)
        self.img_dir = img_dir
        self.target_col = target_col
        self.transform = transform

    def __len__(self):
        return len(self.df)

    def __getitem__(self, idx):
        row = self.df.iloc[idx]
        # Assuming filename column exists, otherwise construct it
        # In the original train_table asset, we read train.csv. 
        # We need to ensure 'filename' or similar exists.
        # If the CSV has 'sample_id', we might need to append .png
        filename = row.get('filename')
        if not filename:
             # Fallback if filename col missing but sample_id exists
             filename = f"{row.get('sample_id')}.png"
        
        img_path = os.path.join(self.img_dir, filename)
        
        # Handle missing images gracefully or let it fail? 
        # For now let it fail to be visible
        image = Image.open(img_path).convert('RGB')
        
        if self.transform:
            image = self.transform(image)
            
        target = torch.tensor(row[self.target_col], dtype=torch.float32)
        return image, target

def get_transforms(img_size=224):
    return transforms.Compose([
        transforms.Resize((img_size, img_size)),
        transforms.ToTensor(),
        # values suggested for resnet
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
    ])
