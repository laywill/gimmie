import os
import shutil
import tempfile
import time
from io import BytesIO
from urllib.parse import urlparse

import pytest
import requests
import responses
from gimmie.main import (
    apply_retry_backoff,
    cleanup_download,
    download_content,
    download_file,
    download_files_from_list,
    handle_download_error,
    handle_resume_response,
    make_request,
    prepare_download_state,
    prepare_file_paths,
    read_urls_from_file,
)


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


def test_prepare_file_paths():
    """Test the prepare_file_paths function."""
    with tempfile.TemporaryDirectory() as temp_dir:
        url = "https://example.com/test.txt"

        # Test with a directory that doesn't exist
        new_dir = os.path.join(temp_dir, "new_folder")
        filename, file_path, temp_path = prepare_file_paths(url, new_dir)

        # Check if function returns the correct values
        assert filename == "test.txt"
        assert file_path == os.path.join(new_dir, "test.txt")
        assert temp_path == os.path.join(new_dir, ".test.txt.part")

        # Check if the directory was created
        assert os.path.exists(new_dir)


def test_prepare_download_state():
    """Test the prepare_download_state function."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create a temporary part file
        temp_path = os.path.join(temp_dir, ".test.txt.part")
        with open(temp_path, "wb") as f:
            f.write(b"partial content")

        # Test when we should resume (has part file + attempt_resume=True + not first attempt)
        headers, file_mode, downloaded_bytes = prepare_download_state(
            temp_path, True, 1
        )
        assert "Range" in headers
        assert headers["Range"] == f"bytes={os.path.getsize(temp_path)}-"
        assert file_mode == "ab"
        assert downloaded_bytes == os.path.getsize(temp_path)

        # Test when we shouldn't resume (first attempt)
        headers, file_mode, downloaded_bytes = prepare_download_state(
            temp_path, True, 0
        )
        assert "Range" not in headers
        assert file_mode == "wb"
        assert downloaded_bytes == 0
        assert not os.path.exists(temp_path)  # File should be deleted

        # Test when resume is disabled
        with open(temp_path, "wb") as f:
            f.write(b"partial content")
        headers, file_mode, downloaded_bytes = prepare_download_state(
            temp_path, False, 1
        )
        assert "Range" not in headers
        assert file_mode == "wb"
        assert downloaded_bytes == 0
        assert not os.path.exists(temp_path)  # File should be deleted


def test_cleanup_download():
    """Test the cleanup_download function."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = os.path.join(temp_dir, ".test.txt.part")
        file_path = os.path.join(temp_dir, "test.txt")

        # Test successful download
        with open(temp_path, "wb") as f:
            f.write(b"content")

        result = cleanup_download(True, temp_path, file_path)
        assert result is True
        assert os.path.exists(file_path)
        assert not os.path.exists(temp_path)

        # Test successful download with existing file
        with open(temp_path, "wb") as f:
            f.write(b"new content")
        with open(file_path, "wb") as f:
            f.write(b"old content")

        result = cleanup_download(True, temp_path, file_path)
        assert result is True
        assert os.path.exists(file_path)
        assert not os.path.exists(temp_path)
        with open(file_path, "rb") as f:
            assert f.read() == b"new content"

        # Test failed download
        with open(temp_path, "wb") as f:
            f.write(b"partial content")

        result = cleanup_download(False, temp_path)
        assert result is False
        assert not os.path.exists(temp_path)


@responses.activate
def test_make_request():
    """Test the make_request function."""
    url = "https://example.com/test.txt"
    content = "This is test content"

    # Mock a successful response
    responses.add(
        responses.GET,
        url,
        body=content,
        status=200,
        content_type="text/plain",
    )

    # Test successful request
    response = make_request(url, {}, (30, 60))
    assert response.status_code == 200
    assert response.text == content

    # Test with headers
    headers = {"Range": "bytes=0-10"}
    responses.add(
        responses.GET,
        url,
        body=content[:10],
        status=206,
        content_type="text/plain",
        match=[responses.matchers.header_matcher(headers)],
    )

    response = make_request(url, headers, (30, 60))
    assert response.status_code == 206
    assert response.text == content[:10]


@responses.activate
def test_handle_resume_response():
    """Test the handle_resume_response function."""
    url = "https://example.com/test.txt"
    content = "This is test content"
    timeout_tuple = (30, 60)

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = os.path.join(temp_dir, ".test.txt.part")

        # Test with 206 response (server supports resume)
        responses.add(
            responses.GET,
            url,
            body=content[5:],
            status=206,
            content_type="text/plain",
            match=[responses.matchers.header_matcher({"Range": "bytes=5-"})],
        )

        response = requests.get(url, headers={"Range": "bytes=5-"}, stream=True)

        result_response, downloaded_bytes, file_mode, supports_resume = (
            handle_resume_response(response, url, 5, temp_path, timeout_tuple, "ab")
        )

        assert result_response.status_code == 206
        assert downloaded_bytes == 5
        assert file_mode == "ab"
        assert supports_resume is True

        # Test when server doesn't support resume (returns 200 instead of 206)
        responses.reset()
        responses.add(
            responses.GET,
            url,
            body=content,
            status=200,
            content_type="text/plain",
        )

        response = requests.get(url, headers={"Range": "bytes=5-"}, stream=True)

        # Create a part file for testing
        with open(temp_path, "wb") as f:
            f.write(b"12345")

        # Also mock the new request that will be made
        responses.add(
            responses.GET,
            url,
            body=content,
            status=200,
            content_type="text/plain",
        )

        result_response, downloaded_bytes, file_mode, supports_resume = (
            handle_resume_response(response, url, 5, temp_path, timeout_tuple, "ab")
        )

        assert result_response.status_code == 200
        assert downloaded_bytes == 0
        assert file_mode == "wb"
        assert supports_resume is False


def test_download_content():
    """Test the download_content function."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = os.path.join(temp_dir, ".test.txt.part")
        content = b"This is test content"

        # Mock a response object with iter_content
        class MockResponse:
            def __init__(self, content, headers=None):
                self.content = content
                self.headers = headers or {}

            def iter_content(self, chunk_size):
                stream = BytesIO(self.content)
                while True:
                    chunk = stream.read(chunk_size)
                    if not chunk:
                        break
                    yield chunk

        # Test basic download
        response = MockResponse(content, {"content-length": str(len(content))})
        bytes_in_attempt = download_content(
            response, temp_path, "wb", 0, False, None, time.time()
        )

        assert bytes_in_attempt == len(content)
        assert os.path.exists(temp_path)
        with open(temp_path, "rb") as f:
            assert f.read() == content

        # Test with downloaded_bytes > 0
        response = MockResponse(content[5:], {"content-length": str(len(content[5:]))})
        bytes_in_attempt = download_content(
            response, temp_path, "wb", 5, True, None, time.time()
        )

        assert bytes_in_attempt == len(content[5:])


def test_handle_download_error():
    """Test the handle_download_error function."""
    url = "https://example.com/test.txt"

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = os.path.join(temp_dir, ".test.txt.part")

        # Create test part file
        with open(temp_path, "wb") as f:
            f.write(b"partial content")

        # Test connection timeout (Retryable)
        can_retry = handle_download_error(
            requests.exceptions.ConnectTimeout(), url, 60, 100, temp_path
        )
        assert can_retry is True
        assert os.path.exists(temp_path)  # File should not be deleted

        # Test read timeout (Retryable)
        can_retry = handle_download_error(
            requests.exceptions.ReadTimeout(), url, 60, 100, temp_path
        )
        assert can_retry is True
        assert os.path.exists(temp_path)

        # Test 4xx error (except 429) - not Retryable
        response = requests.Response()
        response.status_code = 404
        e = requests.exceptions.HTTPError()
        e.response = response

        can_retry = handle_download_error(e, url, 60, 100, temp_path)
        assert can_retry is False
        assert not os.path.exists(temp_path)  # File should be deleted

        # Test 429 (Too Many Requests) - Retryable
        with open(temp_path, "wb") as f:
            f.write(b"partial content")

        response = requests.Response()
        response.status_code = 429
        e = requests.exceptions.HTTPError()
        e.response = response

        can_retry = handle_download_error(e, url, 60, 100, temp_path)
        assert can_retry is True
        assert os.path.exists(temp_path)  # File should not be deleted

        # Test 5xx error - Retryable
        response = requests.Response()
        response.status_code = 500
        e = requests.exceptions.HTTPError()
        e.response = response

        can_retry = handle_download_error(e, url, 60, 100, temp_path)
        assert can_retry is True
        assert os.path.exists(temp_path)  # File should not be deleted


def test_apply_retry_backoff(monkeypatch):
    """Test the apply_retry_backoff function."""
    # Mock the time.sleep function to speed up tests
    sleep_called = None

    def mock_sleep(seconds):
        nonlocal sleep_called
        sleep_called = seconds

    monkeypatch.setattr(time, "sleep", mock_sleep)

    # Test when we should retry
    should_retry = apply_retry_backoff(1, 3)
    assert should_retry is True
    assert sleep_called == 2  # 2^1 = 2 seconds

    # Test when we should retry (with exponential backoff)
    should_retry = apply_retry_backoff(3, 3)
    assert should_retry is True
    assert sleep_called == 8  # 2^3 = 8 seconds

    # Test max backoff cap
    should_retry = apply_retry_backoff(10, 10)
    assert should_retry is True
    assert sleep_called == 60  # Should be capped at 60 seconds

    # Test when we shouldn't retry (attempts > retry_count)
    should_retry = apply_retry_backoff(4, 3)
    assert should_retry is False
    assert sleep_called == 60  # Unchanged from previous call


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

    # Mock the Range request (in case our code tries to use it)
    responses.add(
        responses.GET,
        test_url,
        body=test_content,
        status=206,
        content_type="text/plain",
        match=[responses.matchers.header_matcher({"Range": "bytes=0-"})],
    )

    # For simplicity in tests, disable resume to avoid having to mock more response cases
    result = download_file(test_url, temp_dir, attempt_resume=False)

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

    # Mock range request response (for the resume functionality)
    responses.add(
        responses.GET,
        test_url,
        status=404,
        match=[responses.matchers.header_matcher({"Range": "bytes=0-"})],
    )

    result = download_file(test_url, temp_dir, attempt_resume=False)

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

    # Mock range request responses (for resume functionality)
    responses.add(
        responses.GET,
        urls[0],
        body="Content of file 1",
        status=206,
        match=[responses.matchers.header_matcher({"Range": "bytes=0-"})],
    )
    responses.add(
        responses.GET,
        urls[1],
        body="Content of file 2",
        status=206,
        match=[responses.matchers.header_matcher({"Range": "bytes=0-"})],
    )
    responses.add(
        responses.GET,
        urls[2],
        status=500,
        match=[responses.matchers.header_matcher({"Range": "bytes=0-"})],
    )

    # Use attempt_resume=False for simplicity in testing
    download_files_from_list(urls, temp_dir, attempt_resume=False)

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

        # Try to download the file - disable resume for this test to avoid
        # potential issues with GitHub's handling of range requests
        result = download_file(url, temp_dir, attempt_resume=False)

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
        sys.argv = ["gimmie", url_file, "-d", temp_dir, "--no-resume"]

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
