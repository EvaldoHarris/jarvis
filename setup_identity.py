"""Download official face models for optional local recognition."""
from pathlib import Path

import requests

from core.person_identity import MODELS

ASSETS = {
    "yunet.onnx": "https://huggingface.co/opencv/face_detection_yunet/resolve/main/face_detection_yunet_2023mar.onnx",
    "sface.onnx": "https://huggingface.co/opencv/face_recognition_sface/resolve/main/face_recognition_sface_2021dec.onnx",
}
VOICE_ASSETS = {
    "speaker.onnx": "https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/wespeaker_en_voxceleb_resnet34_LM.onnx",
}


def download_assets(assets):
    MODELS.mkdir(parents=True, exist_ok=True)
    for name, url in assets.items():
        destination = MODELS / name
        if destination.is_file() and destination.stat().st_size > 100_000:
            print(f"Já disponível: {name}")
            continue
        partial = destination.with_suffix(".part")
        try:
            print(f"Baixando {name}...")
            with requests.get(url, stream=True, timeout=(15, 60)) as response:
                response.raise_for_status()
                with partial.open("wb") as output:
                    for chunk in response.iter_content(1024 * 1024):
                        output.write(chunk)
            if partial.stat().st_size < 100_000:
                raise ValueError(f"Download inválido: {name}")
            partial.replace(destination)
        finally:
            partial.unlink(missing_ok=True)
def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--voice", action="store_true", help="Prepare Jarvis keyword and speaker recognition")
    args = parser.parse_args()
    download_assets(ASSETS)
    if args.voice:
        from core.voice_activation import install_and_download
        ok, message = install_and_download()
        if not ok:
            raise RuntimeError(message)
    from core import person_identity
    person_identity._require_models()
    print("Modelos prontos para reconhecimento pela câmera.")


if __name__ == "__main__":
    main()
