"""Run every test offline against a throwaway database and folders."""
import os
import sys
import tempfile

import pytest

_tmp = tempfile.mkdtemp(prefix="socratic_test_")
os.environ["GEMINI_API_KEY"] = ""  # offline: no network calls, deterministic
os.environ["SECRET_KEY"] = "test-secret"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{os.path.join(_tmp, 'test.db')}"
os.environ["FAISS_DIR"] = os.path.join(_tmp, "faiss")
os.environ["UPLOAD_DIR"] = os.path.join(_tmp, "uploads")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def make_pdf(path: str, pages: list[str]) -> str:
    """Write a text PDF, one string per page. The first line of each page is a
    large-font heading, like a real textbook section title."""
    import pymupdf

    doc = pymupdf.open()
    for text in pages:
        heading, body = text.split("\n\n", 1)
        page = doc.new_page()
        page.insert_text((50, 70), heading, fontsize=18)
        page.insert_textbox(pymupdf.Rect(50, 90, 550, 800), body, fontsize=11)
    doc.save(path)
    doc.close()
    return path


SAMPLE_PAGES = [
    "Gradient Descent\n\nGradient descent is an optimization algorithm that updates model parameters "
    "in the direction of the negative gradient of the loss function. The learning rate controls the step size. "
    "If the learning rate is too large the algorithm diverges; if it is too small, training is very slow.",
    "Stochastic Gradient Descent\n\nStochastic gradient descent computes the gradient on a single random "
    "training instance at each step instead of the whole training set. This makes each step much faster "
    "and helps escape local minima, but the loss bounces around instead of decreasing smoothly.",
    "Regularization\n\nRegularization constrains a model to reduce overfitting. Ridge regression adds an "
    "L2 penalty on the weights, while Lasso regression adds an L1 penalty that can drive weights to zero.",
]


@pytest.fixture
def sample_pdf(tmp_path):
    return make_pdf(str(tmp_path / "ml_notes.pdf"), SAMPLE_PAGES)
