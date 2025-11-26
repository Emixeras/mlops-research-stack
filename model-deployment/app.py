"""Minimal Gradio app: dropdown of registered MLflow model versions -> predict on uploaded images.

Usage:
    Set MLFLOW_TRACKING_URI if needed (defaults to http://localhost:5000)
    uv run python app.py

Dropdown entries: model_name:v<version>
Loads model via models:/model_name/version
"""
from __future__ import annotations

import os
import time
from functools import lru_cache
from typing import List, Optional

import mlflow
from mlflow.tracking import MlflowClient
import gradio as gr
import pandas as pd

DEFAULT_TRACKING_URI = "http://mlflow.localhost:8000"


def _init_tracking_uri() -> str:
    uri = os.getenv("MLFLOW_TRACKING_URI", DEFAULT_TRACKING_URI)
    mlflow.set_tracking_uri(uri)
    return uri


def _list_registered_model_versions(client: MlflowClient) -> List[str]:

    names = [rm.name for rm in client.search_registered_models()]

    uris: List[str] = []
    for name in names:
        try:
            versions = client.search_model_versions(f"name='{name}'")
        except Exception:
            continue
        for v in versions:
            full_version = client.get_model_version(name, v.version)
            aliases = full_version.aliases
            
            alias_str = f" 🏷️ {', '.join(aliases)}" if aliases else ""
            label = f"{name} v{v.version}{alias_str}"
            uris.append(label)
    print(uris)
    return sorted(uris)


@lru_cache(maxsize=128)
def _load_model(model_uri: str):
    print(mlflow.pyfunc.get_model_dependencies(model_uri))
    """Load and cache the pyfunc model for a model registry URI (models:/name/version)."""
    return mlflow.pyfunc.load_model(model_uri)


def get_model_choices() -> List[str]:
    
    _init_tracking_uri()
    client = MlflowClient()
    return _list_registered_model_versions(client)


def predict(model_uri: str, files: Optional[List[gr.File]]) -> pd.DataFrame:
    if not model_uri:
        return pd.DataFrame([{"error": "No model selected"}])
    if not files:
        return pd.DataFrame([{"error": "No images uploaded"}])
    # Extract actual URI (strip alias annotation if present)
    # Format: "name vVersion 🏷️ alias1, alias2" -> "models:/name/version"
    # Split on emoji to get clean model info
    model_info = model_uri.split(" 🏷️")[0] if " 🏷️" in model_uri else model_uri
    # Parse name and version from format "name vVersion"
    parts = model_info.rsplit(" v", 1)
    if len(parts) == 2:
        name, version = parts
        actual_uri = f"models:/{name}/{version}"
    else:
        # Fallback if format doesn't match
        actual_uri = model_uri
    model = _load_model(actual_uri)
    # Convert each file to bytes (model wrapper accepts bytes)
    payload: List[bytes] = []
    names: List[str] = []
    for f in files:
        with open(f.name, "rb") as fh:
            payload.append(fh.read())
        names.append(os.path.basename(f.name))

    preds: List[float] = model.predict(payload)  # type: ignore
    df = pd.DataFrame({"filename": names, "prediction": preds})
    return df


def build_interface() -> gr.Blocks:
    with gr.Blocks(title="Biomass Model Server") as demo:
        gr.Markdown("# Biomass Model Inference\nSelect a registered model version and upload images.")
        with gr.Row():
            # Revert to initial loading placeholder; allow custom values per request.
            model_dropdown = gr.Dropdown(
                choices=["(loading...)"] ,
                value="(loading...)",
                label="Model Version",
                interactive=True,
                allow_custom_value=True,
            )
            refresh_btn = gr.Button("Refresh", variant="secondary")
        files = gr.Files(label="Images", file_types=["image"], file_count="multiple")
        predict_btn = gr.Button("Predict", variant="primary")
        output_df = gr.Dataframe(label="Predictions", interactive=False)

        def _refresh_choices():
            uris = get_model_choices()
            if not uris:
                return gr.Dropdown(
                    choices=["(none)"],
                    value="(none)",
                    label="Model Version",
                    interactive=True,
                    allow_custom_value=True,
                )
            return gr.Dropdown(
                choices=uris,
                value=uris[0],
                label="Model Version",
                interactive=True,
                allow_custom_value=True,
            )

        def _do_predict(selection, file_list):
            df = predict(selection, file_list)
            return df
        # Wire events inside context
        refresh_btn.click(fn=_refresh_choices, outputs=[model_dropdown])
        predict_btn.click(fn=_do_predict, inputs=[model_dropdown, files], outputs=[output_df])
        demo.load(fn=_refresh_choices, outputs=[model_dropdown])
    return demo


if __name__ == "__main__":
    _init_tracking_uri()
    
    # Debug setup
    if os.getenv("DEBUG"):
        import debugpy
        debugpy.listen(("0.0.0.0", 5678))
        print("🐛 Waiting for debugger on port 5678...")
        debugpy.wait_for_client()
    
    iface = build_interface()
    
    root_path = os.getenv("GRADIO_ROOT_PATH", "")
    server_name = os.getenv("GRADIO_SERVER_NAME", "0.0.0.0")
    server_port = int(os.getenv("GRADIO_SERVER_PORT", "7860"))
    
    iface.launch(
        server_name=server_name,
        server_port=server_port,
        root_path=root_path
    )
