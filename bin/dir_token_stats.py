#!/bin/env python3

import os
import tiktoken
import numpy as np
import argparse
from tqdm import tqdm
import pandas as pd


def count_tokens(file_path, encoding_name="cl100k_base"):
    """Count tokens in a file using the specified encoding."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            text = f.read()

        encoding = tiktoken.get_encoding(encoding_name)
        tokens = encoding.encode(text)
        return len(tokens)
    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return 0

def analyze_directory(directory_path, encoding_name="cl100k_base", extensions=None):
    """
    Walk through a directory and analyze token counts for all files.

    Args:
        directory_path: Path to the directory to analyze
        encoding_name: Name of the tiktoken encoding to use
        extensions: List of file extensions to include (e.g., ['.txt', '.md'])
                   If None, all files will be processed
    """
    token_counts = []
    file_paths = []
    file_sizes = []

    # Get all files in the directory
    all_files = []
    for root, _, files in os.walk(directory_path):
        for file in files:
            file_path = os.path.join(root, file)
            if extensions is None or any(file.endswith(ext) for ext in extensions):
                all_files.append(file_path)

    print(f"Found {len(all_files)} files to process")

    # Process files with a progress bar
    for file_path in tqdm(all_files, desc="Processing files"):
        file_size = os.path.getsize(file_path)
        token_count = count_tokens(file_path, encoding_name)

        if token_count > 0:  # Only include successfully processed files
            token_counts.append(token_count)
            file_paths.append(file_path)
            file_sizes.append(file_size)

    # Calculate statistics
    if token_counts:
        stats = {
            "Total files processed": len(token_counts),
            "Min tokens": np.min(token_counts),
            "Max tokens": np.max(token_counts),
            "Mean tokens": np.mean(token_counts),
            "Median tokens": np.median(token_counts),
            "90th percentile": np.percentile(token_counts, 90),
            "95th percentile": np.percentile(token_counts, 95),
            "99th percentile": np.percentile(token_counts, 99),
            "Total tokens": np.sum(token_counts),
            "Avg bytes per token": np.sum(file_sizes) / np.sum(token_counts) if np.sum(token_counts) > 0 else 0
        }

        # Create a DataFrame for detailed file information
        df = pd.DataFrame({
            "file_path": file_paths,
            "file_size_bytes": file_sizes,
            "token_count": token_counts,
            "bytes_per_token": [s/t if t > 0 else 0 for s, t in zip(file_sizes, token_counts)]
        })

        # Sort by token count (descending)
        df = df.sort_values("token_count", ascending=False)

        return stats, df
    else:
        print("No files were successfully processed")
        return None, None

def main():
    parser = argparse.ArgumentParser(description="Analyze token counts in files")
    parser.add_argument("directory", help="Directory to analyze")
    parser.add_argument("--encoding", default="cl100k_base",
                        help="Tiktoken encoding to use (default: cl100k_base)")
    parser.add_argument("--extensions", nargs="+",
                        help="File extensions to include (e.g., .txt .md)")
    parser.add_argument("--output", help="Output CSV file for detailed results")
    parser.add_argument("--list-threshold", type=int, default=10,
                        help="List filenames for bins with fewer files than this threshold")

    args = parser.parse_args()

    extensions = args.extensions if args.extensions else None

    print(f"Analyzing directory: {args.directory}")
    print(f"Using encoding: {args.encoding}")
    if extensions:
        print(f"Including extensions: {', '.join(extensions)}")

    stats, df = analyze_directory(args.directory, args.encoding, extensions)

    if stats:
        print("\nToken Statistics:")
        for key, value in stats.items():
            if isinstance(value, (int, np.integer)):
                print(f"{key}: {value:,}")
            else:
                print(f"{key}: {value:.2f}")

        # Save detailed results if requested
        if args.output and df is not None:
            df.to_csv(args.output, index=False)
            print(f"\nDetailed results saved to {args.output}")

        # Print histogram of token counts and list files in small bins
        token_bins = [0, 100, 500, 1000, 2000, 4000, 8000, 16000, 32000, 64000, float('inf')]
        bin_labels = []

        for i in range(len(token_bins) - 1):
            if i == len(token_bins) - 2:
                bin_labels.append(f"{token_bins[i]:,}+")
            else:
                bin_labels.append(f"{token_bins[i]:,} - {token_bins[i+1]:,}")

        # Create a new column for bin labels
        df['token_bin'] = pd.cut(
            df['token_count'],
            bins=token_bins,
            labels=bin_labels,
            right=False
        )

        # Group by bin and count
        bin_counts = df.groupby('token_bin').size()

        print("\nToken Count Distribution:")
        for bin_label, count in bin_counts.items():
            print(f"{bin_label}: {count:,} files")

            # List filenames for bins with few files
            if count <= args.list_threshold:
                print("  Files in this bin:")
                bin_files = df[df['token_bin'] == bin_label].sort_values('token_count', ascending=False)
                for idx, row in bin_files.iterrows():
                    print(f"  - {row['file_path']} ({row['token_count']:,} tokens)")
                print()

if __name__ == "__main__":
    main()

