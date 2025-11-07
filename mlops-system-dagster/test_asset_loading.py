import pickle
import sys
from pathlib import Path
import numpy as np

# Apply the cross-platform patch
if sys.platform == 'win32':
    import pathlib._local as pathlib_local
    class CrossPlatformPosixPath(type(Path())):
        def __new__(cls, *args):
            if args:
                return Path(*args)
            return Path()
    pathlib_local.PosixPath = CrossPlatformPosixPath

# Load the asset
with open("dagster_outputs/train_features", "rb") as f:
    data = pickle.load(f)

# Extract the components
X = data['X']  # Shape: (100, 4096) - your feature matrix
y = data['y']  # Shape: (100,) - your target values
scaler = data['scaler']  # The fitted StandardScaler

# Now you can use them
print(f"Number of samples: {X.shape[0]}")
print(f"Number of features per sample: {X.shape[1]}")
print(f"Target range: {y.min()} to {y.max()}")

# Example: Transform new data using the scaler
# new_data_scaled = scaler.transform(new_data)