"""Automated model downloader for Sherpa-ONNX Parakeet ASR and Piper TTS."""

from pathlib import Path
import sys
import urllib.request


PARAKEET_BASE_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/"
    "sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8.tar.bz2"
)


def download_file(url: str, dest: Path) -> None:
    """Download a file with progress indication."""
    print(f"Downloading {dest.name} from {url}...")
    dest.parent.mkdir(parents=True, exist_ok=True)

    def report(count, block_size, total_size):
        percent = int(count * block_size * 100 / total_size) if total_size > 0 else 0
        sys.stdout.write(f"\r  Progress: {percent}%")
        sys.stdout.flush()

    urllib.request.urlretrieve(url, str(dest), reporthook=report)
    print("\n  Done.")


def setup_parakeet_model(models_dir: Path) -> None:
    """Download and extract Parakeet TDT INT8 model for Sherpa-ONNX."""
    import tarfile

    target_dir = models_dir / "parakeet-tdt-0.6b-int8"
    if (target_dir / "encoder.int8.onnx").exists():
        print(f"Parakeet model already exists in {target_dir}")
        return

    archive_path = models_dir / "parakeet-tdt-0.6b-v3-int8.tar.bz2"
    download_file(PARAKEET_BASE_URL, archive_path)

    print(f"Extracting {archive_path.name}...")
    with tarfile.open(archive_path, "r:bz2") as tar:
        tar.extractall(path=models_dir)

    # Rename extracted folder to standard target directory
    extracted_folder = models_dir / "sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8"
    if extracted_folder.exists() and not target_dir.exists():
        extracted_folder.rename(target_dir)

    if archive_path.exists():
        archive_path.unlink()  # Clean up tarball

    print(f"Parakeet model successfully installed to {target_dir}")


def main():
    root_dir = Path(__file__).resolve().parent.parent
    models_dir = root_dir / "models"
    models_dir.mkdir(exist_ok=True)

    print("=" * 60)
    print(" Setting up Computer-Auto Offline Models")
    print("=" * 60)
    setup_parakeet_model(models_dir)
    print("All offline models ready!")


if __name__ == "__main__":
    main()
