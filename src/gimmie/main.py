#!/usr/bin/env python3
"""Main module for the Gimmie file downloader."""

import argparse
import os
import sys
from urllib.parse import urlparse

import requests


def download_file(
    url,
    destination_folder="downloads",
    connect_timeout=30,
    read_timeout=60,
    total_timeout=None,
    retry_count=3,
):
    """
    Download a file from a URL to the specified destination folder with timeout handling

    Args:
        url (str): URL to download
        destination_folder (str): Folder to save the file
        connect_timeout (int): Seconds to wait for connection establishment
        read_timeout (int): Seconds to wait between data chunks
        total_timeout (int, optional): Maximum seconds for the entire download
        retry_count (int): Number of retry attempts

    Returns:
        bool: True if download succeeded, False otherwise
    """
    # Create destination folder if it doesn't exist
    if not os.path.exists(destination_folder):
        os.makedirs(destination_folder)

    # Extract filename from URL
    filename = os.path.basename(urlparse(url).path)

    # Create the full path for saving the file
    file_path = os.path.join(destination_folder, filename)

    print(f"Downloading {url} to {file_path}")

    # Track start time for total timeout
    start_time = time.time()

    # Initialize retry counter
    attempts = 0

    while attempts <= retry_count:
        try:
            # Track if we received any data (for retry logic)
            received_data = False

            # Set timeout as tuple (connect_timeout, read_timeout)
            response = requests.get(
                url, stream=True, timeout=(connect_timeout, read_timeout)
            )
            response.raise_for_status()  # Raise an exception for HTTP errors

            # Get total file size if available
            total_size = int(response.headers.get("content-length", 0))

            # Track last data received time for stall detection
            last_data_time = time.time()
            downloaded_bytes = 0

            # Save the file
            with open(file_path, "wb") as file:
                for chunk in response.iter_content(chunk_size=8192):
                    # Check if total timeout has been exceeded
                    if total_timeout and (time.time() - start_time > total_timeout):
                        raise TimeoutError(
                            f"Total download time exceeded {total_timeout} seconds"
                        )

                    # If we got data, update our trackers
                    if chunk:
                        received_data = True
                        file.write(chunk)
                        downloaded_bytes += len(chunk)
                        last_data_time = time.time()

                        # Update progress if we know the size
                        if total_size > 0:
                            percent = (downloaded_bytes / total_size) * 100
                            print(
                                f"\rProgress: {percent:.1f}% ({downloaded_bytes}/{total_size})",
                                end="",
                            )

            # Clear the progress line
            if total_size > 0:
                print()

            print(f"Successfully downloaded {filename}")
            return True

        except requests.exceptions.ConnectTimeout:
            print(f"Connection timeout while connecting to {url}")
        except requests.exceptions.ReadTimeout:
            if received_data:
                print(f"Download stalled - no data received for {read_timeout} seconds")
            else:
                print(f"Server did not respond within {read_timeout} seconds")
        except TimeoutError as e:
            print(f"Timeout error: {e}")
        except requests.exceptions.RequestException as e:
            print(f"Error downloading {url}: {e}")
            # Don't retry on 4xx errors
            if hasattr(e, "response") and 400 <= e.response.status_code < 500:
                return False

        attempts += 1
        if attempts <= retry_count:
            wait_time = 2**attempts  # Exponential backoff
            print(
                f"Retrying in {wait_time} seconds... (Attempt {attempts}/{retry_count})"
            )
            time.sleep(wait_time)
        else:
            print(f"Failed to download after {retry_count} attempts")

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
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
