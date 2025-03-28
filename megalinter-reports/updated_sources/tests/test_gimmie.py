import os
import shutil
import tempfile
from urllib.parse import urlparse

import pytest
import responses
from gimmie.main import download_file, download_files_from_list, read_urls_from_file


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test downloads."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    # Cleanup after test
    shutil.rmtree(temp_dir)


@pytest.fixture
def url_file():
    """Create a temporary file with test URLs."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        f.write(
            "https://raw.githubusercontent.com/laywill/gimmie/refs/heads/main/README.md\n"
        )
        f.write("# This is a comment\n")
        f.write("https://example.com/test.txt\n")
        f.write("https://example.com/file.pdf\n")
        f.write("\n")  # Empty line
        temp_filename = f.name

    yield temp_filename
    # Cleanup after test
    os.unlink(temp_filename)


def test_read_urls_from_file(url_file):
    """Test reading URLs from a file."""
    urls = read_urls_from_file(url_file)

    assert len(urls) == 3
    assert (
        urls[0]
        == "https://raw.githubusercontent.com/laywill/gimmie/refs/heads/main/README.md"
    )
    assert urls[1] == "https://example.com/test.txt"
    assert urls[2] == "https://example.com/file.pdf"


def test_read_urls_from_nonexistent_file():
    """Test reading URLs from a nonexistent file."""
    urls = read_urls_from_file("nonexistent_file.txt")
    assert urls == []


@responses.activate
def test_download_file(temp_dir):
    """Test downloading a file."""
    test_url = "https://example.com/test.txt"
    test_content = "This is a test file"

    # Mock the HTTP response
    responses.add(
        responses.GET,
        test_url,
        body=test_content,
        status=200,
        content_type="text/plain",
    )

    result = download_file(test_url, temp_dir)

    assert result is True

    # Check if file was downloaded correctly
    filename = os.path.basename(urlparse(test_url).path)
    file_path = os.path.join(temp_dir, filename)
    assert os.path.exists(file_path)

    with open(file_path) as f:
        content = f.read()
        assert content == test_content


@responses.activate
def test_download_file_http_error(temp_dir):
    """Test downloading a file with HTTP error."""
    test_url = "https://example.com/not_found.txt"

    # Mock the HTTP response
    responses.add(responses.GET, test_url, status=404)

    result = download_file(test_url, temp_dir)

    assert result is False

    # Check that no file was created
    filename = os.path.basename(urlparse(test_url).path)
    file_path = os.path.join(temp_dir, filename)
    assert not os.path.exists(file_path)


@responses.activate
def test_download_files_from_list(temp_dir):
    """Test downloading multiple files."""
    urls = [
        "https://example.com/file1.txt",
        "https://example.com/file2.txt",
        "https://example.com/error.txt",
    ]

    # Mock the HTTP responses
    responses.add(responses.GET, urls[0], body="Content of file 1", status=200)

    responses.add(responses.GET, urls[1], body="Content of file 2", status=200)

    responses.add(responses.GET, urls[2], status=500)

    download_files_from_list(urls, temp_dir)

    # Check if files were downloaded correctly
    assert os.path.exists(os.path.join(temp_dir, "file1.txt"))
    assert os.path.exists(os.path.join(temp_dir, "file2.txt"))
    assert not os.path.exists(os.path.join(temp_dir, "error.txt"))


def test_integration_with_real_file():
    """Integration test with a real file from GitHub.

    This test will make an actual HTTP request to GitHub.
    Skip this test if you don't want to make external requests.
    """
    # Create a temporary directory
    with tempfile.TemporaryDirectory() as temp_dir:
        url = (
            "https://raw.githubusercontent.com/laywill/gimmie/refs/heads/main/README.md"
        )

        # Try to download the file
        result = download_file(url, temp_dir)

        # If the repository exists and is public, this should succeed
        if result:
            assert os.path.exists(os.path.join(temp_dir, "README.md"))


@pytest.mark.skipif(
    not os.environ.get("RUN_INTEGRATION_TESTS"),
    reason="Integration tests are skipped by default",
)
def test_main_function():
    """
    Integration test for the main function.

    Set the environment variable RUN_INTEGRATION_TESTS=1 to run this test.
    """
    import sys

    from gimmie.main import main

    # Create temp dir and URL file
    with tempfile.TemporaryDirectory() as temp_dir:
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write(
                "https://raw.githubusercontent.com/laywill/gimmie/refs/heads/main/README.md\n"
            )
            url_file = f.name

        # Mock sys.argv
        original_argv = sys.argv
        sys.argv = ["gimmie", url_file, "-d", temp_dir]

        try:
            # Run main function
            exit_code = main()

            # Check results
            assert exit_code == 0
            assert os.path.exists(os.path.join(temp_dir, "README.md"))
        finally:
            # Restore argv and cleanup
            sys.argv = original_argv
            os.unlink(url_file)
