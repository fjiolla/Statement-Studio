import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
# isolate runtime data for tests
os.environ.setdefault("BEFREE_DATA_DIR", tempfile.mkdtemp(prefix="befree-test-"))

SAMPLES = ROOT / "tests" / "data" / "synthetic_pdfs"   # generated, exact ground truth
DEMO = ROOT / "samples"                                   # shown in the app
TRUTH = ROOT / "tests" / "data" / "synthetic"
REAL = ROOT.parent / "sample_pdf"
