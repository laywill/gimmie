# Gimmie

A simple command-line tool to download files from a list of URLs.

<!-- header-logo-start -->
<div align="center">
  <a href="https://github.com/laywill/gimmie" target="blank" title="Get Gimmie">
    <img src="https://github.com/laywill/gimmie/raw/main/docs/assets/images/gimmie_logo_1x1.jpeg" alt="Gimmie Logo" min-height="200px">
  </a>
</div>
<!-- header-logo-end -->

## Description

Gimmie ("Give me your files") is a lightweight utility that downloads files from a list of web addresses. Simply provide a text file with one URL per line, and Gimmie will handle the rest.

## Features

- Downloads files from multiple URLs in sequence
- Extracts filenames automatically from URLs
- Supports any file type available via HTTP/HTTPS
- Handles errors gracefully, continuing to the next file if one fails
- Option to specify a custom download directory

## Installation

### Requirements

- Python 3.10 or higher
- `pip` package manager

### From PyPI (Recommended)

```bash
pip install gimmie
```

### From Source

1. Clone the repository:

   ```bash
   git clone https://github.com/yourusername/gimmie.git
   cd gimmie
   ```

2. Install the package:

   ```bash
   pip install .
   ```

## Usage

### Basic Usage

1. Create a text file (e.g., `files-to-download.txt`) with one URL per line:

   ```plaintext
   https://example.com/file1.pdf
   https://example.com/file2.jpg
   https://example.com/file3.zip
   ```

2. Run Gimmie with the file as an argument:

   ```bash
   gimmie files-to-download.txt
   ```

3. Files will be downloaded to a `downloads` directory in your current working directory.

### Command-Line Options

```bash
gimmie [-h] [-d DIRECTORY] url_file
```

Arguments:

- `url_file`: Path to text file containing URLs (one per line)

Options:

- `-h, --help`: Show help message and exit
- `-d DIRECTORY, --directory DIRECTORY`: Directory to save downloaded files (default: downloads)

### Example

```bash
# Download files to a custom directory
gimmie files-to-download.txt -d my_files
```

## URL File Format

The URL file should contain one URL per line. The tool will:

- Strip whitespace from lines
- Skip empty lines and lines starting with '#' (for comments)

Example URL file:

```bash
# Files to download
https://example.com/file1.pdf
https://example.com/file2.jpg
https://example.com/file3.zip
```

## Development

### Docker Dev Container

The recommended approach is to use a Docker Dev Container as this includes everything you need.

1. Install VSCode
   1. Ensure the `ms-vscode-remote.remote-containers` extension is installed.
2. Install Docker Desktop
3. Clone the repository
4. Reopen in Container

### Setting Up Development Environment

1. Clone the repository
2. Create a virtual environment:

   ```powershell
   python -m venv venv
   source venv/bin/activate   # On Linux / MacOS
   venv\Scripts\activate      # On Windows
   ```

3. Install development dependencies:

   ```bash
   pip install -e ".[dev,test]"
   ```

### Dependency Management

This project uses pip with version constraints defined in `pyproject.toml`. To ensure reproducible builds and consistent environments, we use pip-tools to generate locked dependency files.

#### Locking Dependencies

To generate locked dependencies for all environments (runtime, dev, test):

```bash
pip install pip-tools
pip-compile -o requirements.txt pyproject.toml
pip-compile -o requirements-dev.txt --extra dev pyproject.toml
pip-compile -o requirements-test.txt --extra test pyproject.toml
```

#### Installing from Lock Files

To install exact versions specified in the lock files (reproducible environment):

```bash
# Runtime only
pip install -r requirements.txt

# Development (includes runtime)
pip install -r requirements-dev.txt

# Testing (includes runtime)
pip install -r requirements-test.txt

# All (dev + test)
pip install -r requirements-dev.txt -r requirements-test.txt
```

#### Updating Dependencies

To update dependencies to their latest compatible versions:

```bash
pip-compile --upgrade -o requirements.txt pyproject.toml
pip-compile --upgrade -o requirements-dev.txt --extra dev pyproject.toml
pip-compile --upgrade -o requirements-test.txt --extra test pyproject.toml
```

#### Automated Updates with Dependabot

Dependabot automatically monitors the repository for dependency updates and creates pull requests when newer versions are available. These PRs help keep dependencies current while maintaining security and compatibility. Lock files are compatible with OSV-scanner for vulnerability scanning.

### Running Tests

Run the tests using PyTest:

```bash
pytest
```

Set the environment variable `RUN_INTEGRATION_TESTS=1` to run integration tests that will actually download a file from the internet.

Linux:

```bash
export RUN_INTEGRATION_TESTS=1
```

Windows:

```bash
set RUN_INTEGRATION_TESTS=1
```

### Updating Release version number

Rather than set the version explicitly, use Hatch to roll version numbers:

```bash
$ hatch version minor
Old: 0.1.0
New: 0.2.0
```

The final word in the command above controls how the version is incremented:

| Segments                 | New version |
|:-------------------------|:------------|
| `release`                | 1.0.0       |
| `major`                  | 2.0.0       |
| `minor`                  | 1.1.0       |
| `micro` `patch` `fix`    | 1.0.1       |
| `a` `alpha`              | 1.0.0a0     |
| `b` `beta`               | 1.0.0b0     |
| `c` `rc` `pre` `preview` | 1.0.0rc0    |
| `r` `rev` `post`         | 1.0.0.post0 |
| `dev`                    | 1.0.0.dev0  |

This ensures that versions are rolled correctly.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request
