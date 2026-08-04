import pathlib

def test_readme_contains_quick_start():
    readme_path = pathlib.Path(__file__).parents[1] / "README.md"
    content = readme_path.read_text()
    assert "## Quick start" in content
    assert "Provider environment variables" in content
    assert "| Provider | Environment variable |" in content
