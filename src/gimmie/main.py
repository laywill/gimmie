#!/usr/bin/env python3
"""Main module for the Gimmie file downloader."""

import argparse
import os
import sys
from urllib.parse import urlparse

import requests


def download_file(url, destination_folder="downloads"):
    """
    Download a file from a URL to the specified destination folder
    """
    # Create destination folder if it doesn't exist
    if not os.path.exists(destination_folder):
        os.makedirs(destination_folder)

    # Extract filename from URL
    filename = os.path.basename(urlparse(url).path)

    # Create the full path for saving the file
    file_path = os.path.join(destination_folder, filename)

    print(f"Downloading {url} to {file_path}")

    try:
        # Send a GET request to the URL
        response = requests.get(url, stream=True)
        response.raise_for_status()  # Raise an exception for HTTP errors

        # Save the file
        with open(file_path, "wb") as file:
            for chunk in response.iter_content(chunk_size=8192):
                file.write(chunk)

        print(f"Successfully downloaded {filename}")
        return True

    except Exception as e:
        print(f"Error downloading {url}: {e}")
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


def download_files_from_list(url_list, destination_folder="downloads"):
    """
    Download multiple files from a list of URLs
    """
    successful = 0
    total = len(url_list)

    for url in url_list:
        if download_file(url, destination_folder):
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

    args = parser.parse_args()

    # Read URLs from the specified file
    urls = read_urls_from_file(args.url_file)

    if not urls:
        print(f"No valid URLs found in {args.url_file}")
        return 1

    print(f"Found {len(urls)} URLs to download")

    # Execute the download
    download_files_from_list(urls, args.directory)
    return 0


if __name__ == "__main__":
    sys.exit(main())
