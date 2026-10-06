"""Write the demo project's artefacts (examples/perov5) from the Perov-5 CSVs and the model files.

    python scripts/build_demo.py --data-dir data/perov5 --out examples/perov5 \
        --model meidnet-2k=checkpoints/dual_autoencoder_clip_earlyfusion_propertyaware_2k.pth \
        --model meidnet-alignment-seed3=checkpoints/meidnet_paper_rerun_seed3.pth

See matter/demo_build.py for what is written. `meidnet-matter build-demo` runs the same code.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from matter.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(["build-demo", *sys.argv[1:]]))
