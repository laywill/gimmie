#!/usr/bin/env python3
"""Main module for the Gimmie file downloader."""

import argparse
import os
import sys
import time
from urllib.parse import urlparse

import requests


def prepare_file_paths(url, destination_folder):
    """Prepare file paths for download."""
    # Create destination folder if it doesn't exist
    if not os.path.exists(destination_folder):
        os.makedirs(destination_folder)

    # Extract filename from URL
    filename = os.path.basename(urlparse(url).path)

    # Define paths for final and temporary files
    file_path = os.path.join(destination_folder, filename)
    temp_path = os.path.join(destination_folder, f".{filename}.part")

    return filename, file_path, temp_path


def prepare_download_state(temp_path, attempt_resume, attempts):
    """Prepare download state, determining if we should resume."""
    headers = {}
    file_mode = "wb"
    downloaded_bytes = 0

    # Check if we should try to resume a previous download
    if os.path.exists(temp_path) and attempt_resume and attempts > 0:
        downloaded_bytes = os.path.getsize(temp_path)
        headers["Range"] = f"bytes={downloaded_bytes}-"
        file_mode = "ab"
        print(f"Resuming download from {downloaded_bytes} bytes")
    else:
        # Remove any existing partial download if we're not resuming
        if os.path.exists(temp_path):
            os.remove(temp_path)

    return headers, file_mode, downloaded_bytes


def cleanup_download(success, temp_path, file_path=None):
    """Clean up after download attempt."""
    if success and file_path:
        # Download succeeded, rename temp file to final file
        if os.path.exists(file_path):
            os.remove(file_path)  # Remove any existing file first
        os.rename(temp_path, file_path)
        return True
    elif not success and os.path.exists(temp_path):
        # Download failed completely, remove temp file
        os.remove(temp_path)
    return False


def make_request(url, headers, timeout_tuple):
    """Make HTTP request with proper error handling."""
    return requests.get(url, stream=True, timeout=timeout_tuple, headers=headers)


def handle_resume_response(
    response, url, downloaded_bytes, temp_path, timeout_tuple, file_mode
):
    """Handle response when attempting to resume a download."""
    # Check if the server supports resume
    supports_resume = response.status_code == 206  # Partial Content

    # If we tried to resume but got a 200 instead of 206, start over
    if downloaded_bytes > 0 and not supports_resume and response.status_code == 200:
        print("Server doesn't support resuming, starting download from beginning")
        os.remove(temp_path)
        downloaded_bytes = 0
        file_mode = "wb"
        # Make a new request without the Range header
        response = make_request(url, {}, timeout_tuple)

    response.raise_for_status()  # Raise an exception for HTTP errors

    return response, downloaded_bytes, file_mode, supports_resume


def download_content(
    response,
    temp_path,
    file_mode,
    downloaded_bytes,
    supports_resume,
    total_timeout,
    start_time,
):
    """Download content from response with progress tracking."""
    # Initial estimate of total size
    initial_content_length = int(response.headers.get("content-length", 0))

    # For resumed downloads with a valid Content-Range header
    if supports_resume and "Content-Range" in response.headers:
        try:
            range_header = response.headers.get("Content-Range", "")
            # Format is like "bytes 100-600/1000" where 1000 is the total size
            total_size = int(range_header.split("/")[-1])
        except (ValueError, IndexError):
            # If parsing fails, use content_length + downloaded_bytes
            total_size = downloaded_bytes + initial_content_length
    elif downloaded_bytes > 0:
        # For resumed downloads without Content-Range
        total_size = downloaded_bytes + initial_content_length
    else:
        # For fresh downloads
        total_size = initial_content_length

    # Track data received
    bytes_in_this_attempt = 0

    # For progress display
    show_percentage = total_size > 0

    # Save the file
    with open(temp_path, file_mode) as file:
        for chunk in response.iter_content(chunk_size=8192):
            # Check if total timeout has been exceeded
            if total_timeout and (time.time() - start_time > total_timeout):
                raise TimeoutError(
                    f"Total download time exceeded {total_timeout} seconds"
                )

            # If we got data, update our trackers
            if chunk:
                file.write(chunk)
                bytes_in_this_attempt += len(chunk)

                # Check if we've exceeded initial size estimate
                current_downloaded = downloaded_bytes + bytes_in_this_attempt
                if show_percentage and current_downloaded > total_size:
                    # Switch to byte count display if our estimate was wrong
                    show_percentage = False

                # Update progress display
                if show_percentage:
                    percent = min((current_downloaded / total_size) * 100, 100.0)
                    print(
                        f"\rProgress: {percent:.1f}% ({current_downloaded}/{total_size} bytes)",
                        end="",
                    )
                else:
                    # Just show downloaded bytes when total size is unknown or unreliable
                    print(f"\rDownloaded: {current_downloaded} bytes", end="")

    # Final newline after progress updates
    print()

    return bytes_in_this_attempt


def handle_download_error(e, url, read_timeout, bytes_in_this_attempt, temp_path):
    """Handle download errors with appropriate messaging."""
    if isinstance(e, requests.exceptions.ConnectTimeout):
        print(f"Connection timeout while connecting to {url}")
        return True  # Retryable
    elif isinstance(e, requests.exceptions.ReadTimeout):
        if bytes_in_this_attempt > 0:
            print(f"Download stalled - no data received for {read_timeout} seconds")
        else:
            print(f"Server did not respond within {read_timeout} seconds")
        return True  # Retryable
    elif isinstance(e, TimeoutError):
        print(f"Timeout error: {e}")
        return True  # Retryable
    elif isinstance(e, requests.exceptions.RequestException):
        print(f"Error downloading {url}: {e}")
        # Don't retry on 4xx errors (except 429 Too Many Requests)
        if hasattr(e, "response") and 400 <= e.response.status_code < 500:
            if e.response.status_code != 429:  # 429 is recoverable
                if os.path.exists(temp_path):
                    os.remove(temp_path)  # Clean up the partial file
                return False  # Not Retryable
        return True  # Retryable
    else:
        print(f"Unexpected error: {e}")
        return True  # Retryable


def apply_retry_backoff(attempts, retry_count):
    """Apply exponential backoff for retries."""
    if attempts <= retry_count:
        wait_time = min(2**attempts, 60)  # Exponential backoff, max 60 seconds
        print(f"Retrying in {wait_time} seconds... (Attempt {attempts}/{retry_count})")
        time.sleep(wait_time)
        return True
    else:
        print(f"Failed to download after {retry_count} attempts")
        return False


def download_file(
    url,
    destination_folder="downloads",
    connect_timeout=30,
    read_timeout=60,
    total_timeout=None,
    retry_count=3,
    attempt_resume=True,
):
    """
    Download a file from a URL to the specified destination folder with timeout handling
    """
    # Prepare file paths
    filename, file_path, temp_path = prepare_file_paths(url, destination_folder)
    print(f"Downloading {url} to {file_path}")

    # Track start time for total timeout
    start_time = time.time()
    attempts = 0
    bytes_in_this_attempt = 0

    # Main download loop with retry logic
    while attempts <= retry_count:
        try:
            # Prepare download state (headers, file mode, etc.)
            headers, file_mode, downloaded_bytes = prepare_download_state(
                temp_path, attempt_resume, attempts
            )

            # Make the HTTP request
            timeout_tuple = (connect_timeout, read_timeout)
            response = make_request(url, headers, timeout_tuple)

            # Handle resume-related response adjustments
            response, downloaded_bytes, file_mode, supports_resume = (
                handle_resume_response(
                    response, url, downloaded_bytes, temp_path, timeout_tuple, file_mode
                )
            )

            # Download the content
            bytes_in_this_attempt = download_content(
                response,
                temp_path,
                file_mode,
                downloaded_bytes,
                supports_resume,
                total_timeout,
                start_time,
            )

            # Success! Clean up and return
            print(f"Successfully downloaded {filename}")
            return cleanup_download(True, temp_path, file_path)

        except Exception as e:
            # Handle the error and determine if we should retry
            can_retry = handle_download_error(
                e, url, read_timeout, bytes_in_this_attempt, temp_path
            )
            if not can_retry:
                return False

            # Apply retry backoff
            attempts += 1
            if not apply_retry_backoff(attempts, retry_count):
                return cleanup_download(False, temp_path)

    return False


def read_urls_from_file(file_path):
    """
    Read URLs from a text file, one URL per line
    """
    urls = []
    try:
        with open(file_path) as file:
            for line in file:
                # Strip whitespace and remove any quotes or commas
                url = line.strip().strip('"').strip(",").strip("'")
                if url and not url.startswith("#"):  # Skip empty lines and comments
                    urls.append(url)
        return urls
    except Exception as e:
        print(f"Error reading URL file: {e}")
        return []


def download_files_from_list(
    url_list,
    destination_folder="downloads",
    connect_timeout=30,
    read_timeout=60,
    total_timeout=None,
    retry_count=3,
    attempt_resume=True,
):
    """
    Download multiple files from a list of URLs
    """
    successful = 0
    total = len(url_list)

    for url in url_list:
        if download_file(
            url,
            destination_folder,
            connect_timeout=connect_timeout,
            read_timeout=read_timeout,
            total_timeout=total_timeout,
            retry_count=retry_count,
            attempt_resume=attempt_resume,
        ):
            successful += 1

    print(f"Downloaded {successful} out of {total} files")


def main():
    """Entry point for the command-line script."""
    parser = argparse.ArgumentParser(
        description="Download files from URLs listed in a text file."
    )
    parser.add_argument("url_file", help="Text file containing URLs (one per line)")
    parser.add_argument(
        "-d",
        "--directory",
        default="downloads",
        help="Directory to save downloaded files (default: downloads)",
    )

    # Add timeout-related arguments
    parser.add_argument(
        "--connect-timeout",
        type=int,
        default=30,
        help="Seconds to wait when establishing connection (default: 30)",
    )
    parser.add_argument(
        "--read-timeout",
        type=int,
        default=60,
        help="Seconds to wait between receiving data chunks (default: 60)",
    )
    parser.add_argument(
        "--total-timeout",
        type=int,
        default=None,
        help="Maximum seconds allowed for a download (default: no limit)",
    )
    parser.add_argument(
        "--retry",
        type=int,
        default=3,
        help="Number of retry attempts for failed downloads (default: 3)",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Do not attempt to resume partial downloads",
    )

    args = parser.parse_args()

    # Read URLs from the specified file
    urls = read_urls_from_file(args.url_file)

    if not urls:
        print(f"No valid URLs found in {args.url_file}")
        return 1

    print(f"Found {len(urls)} URLs to download")

    # Execute the download with timeout parameters
    download_files_from_list(
        urls,
        args.directory,
        connect_timeout=args.connect_timeout,
        read_timeout=args.read_timeout,
        total_timeout=args.total_timeout,
        retry_count=args.retry,
        attempt_resume=not args.no_resume,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
