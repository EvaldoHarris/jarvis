"""Download only the requested local models; never runs as part of audio capture."""
import argparse
from core.local_translation import MODEL_ROOT, language_code


def main():
    parser = argparse.ArgumentParser(description="Prepare offline video translation")
    parser.add_argument("--model", default="small", choices=("tiny", "base", "small", "medium", "large-v3-turbo"))
    parser.add_argument("--source", default="en")
    parser.add_argument("--target", default="pt")
    parser.add_argument("--voice", default="", help="Piper voice to download, e.g. pt_BR-faber-medium")
    args = parser.parse_args()
    if args.voice:
        from providers.tts_piper import download
        download(args.voice, lambda message: print(message, flush=True))
        return
    from faster_whisper.utils import download_model
    print(f"Downloading Whisper {args.model}…", flush=True)
    download_model(args.model, output_dir=str(MODEL_ROOT / args.model))
    import argostranslate.package as package
    source, target = language_code(args.source), language_code(args.target)
    if source == target:
        return
    installed = package.get_installed_packages()

    def have(a, b):
        return any(p.from_code == a and p.to_code == b for p in installed)

    if have(source, target):
        print(f"Argos {source} -> {target} already installed.", flush=True)
        return
    package.update_package_index()
    available = package.get_available_packages()

    def find(a, b):
        return next((p for p in available if p.from_code == a and p.to_code == b), None)

    # No direct model (e.g. zh -> pt): pivot through English.
    hops = [(source, target)] if find(source, target) else [(source, "en"), ("en", target)]
    for a, b in hops:
        if have(a, b):
            print(f"Argos {a} -> {b} already installed.", flush=True)
            continue
        match = find(a, b)
        if match is None:
            raise SystemExit(f"No Argos model available for {source} -> {target} (missing {a} -> {b}).")
        print(f"Downloading Argos {a} -> {b}…", flush=True)
        package.install_from_path(match.download())
    print("Local translation models ready.", flush=True)


if __name__ == "__main__":
    main()
