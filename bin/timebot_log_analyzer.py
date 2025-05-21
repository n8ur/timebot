#!/usr/bin/env python3
# /usr/local/lib/timebot/bin/timebot_log_analyzer.py
# Copyright 2025 John Ackermann
# Licensed under the MIT License. See LICENSE.TXT for details.

import re
import argparse
from collections import defaultdict, Counter
from datetime import datetime
import sys
import locale
import traceback

# --- Regular Expressions ---
log_line_pattern = re.compile(
    r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - (INFO|WARNING|ERROR) - (.*)",
    re.DOTALL
)
login_patterns = [
    re.compile(r"User auto-logged in via token: (.+)"),
    re.compile(r"User logged in: (.+)"),
]
query_pattern = re.compile(r"User query: '(.*)'")
login_failed_pattern = re.compile(r"Login failed for (.+): Invalid credentials.")
invalid_email_pattern = re.compile(r"Invalid email address: (.+)")
signup_pattern = re.compile(r"New user signup: .+ \((.+)\)")
new_chat_pattern = re.compile(r"New chat started with ID: (\d+)")


def analyze_log_file(log_file_path, top_n=10):
    """
    Analyzes a chat server log file to extract summaries.
    """
    print("DEBUG: Starting analyze_log_file function...", file=sys.stderr)
    queries = []
    logins_per_day = defaultdict(set)
    total_logins_per_day = defaultdict(int)
    all_unique_logins = set()
    errors_warnings = []
    error_warning_summary = Counter()
    signups = set()
    chats_started = 0
    first_timestamp = None
    last_timestamp = None
    malformed_lines = 0
    processed_lines = 0

    try:
        file_encoding = locale.getpreferredencoding(False)
    except locale.Error:
        file_encoding = "utf-8"

    print(f"DEBUG: Attempting to read file '{log_file_path}' with encoding: {file_encoding}", file=sys.stderr)

    try:
        with open(log_file_path, "r", encoding=file_encoding, errors='replace') as f:
            print("DEBUG: File opened successfully. Starting line processing...", file=sys.stderr)
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue

                # Keep this periodic progress indicator
                if line_num % 1000 == 0: # Increased frequency slightly
                    print(f"DEBUG: Processing line {line_num}...", file=sys.stderr)
                    sys.stderr.flush() # Ensure it prints immediately

                match = log_line_pattern.match(line)
                if not match:
                    if line:
                         malformed_lines += 1
                    continue

                processed_lines += 1
                try:
                    timestamp_str, level, message = match.groups()
                    # Minimal debug for matched lines (optional, can be commented out)
                    # print(f"DEBUG: Line {line_num}: Matched basic format. Level={level}. MsgStart='{message[:80]}...'", file=sys.stderr)

                    timestamp = datetime.strptime(
                        timestamp_str, "%Y-%m-%d %H:%M:%S,%f"
                    )
                    date_str = timestamp.strftime("%Y-%m-%d")

                    if first_timestamp is None:
                        first_timestamp = timestamp
                    last_timestamp = timestamp

                    # --- Process based on Level and Message ---
                    if level == "INFO":
                        # print(f"DEBUG: Line {line_num}: Checking INFO patterns...", file=sys.stderr) # Commented out
                        user_logged_in = None
                        login_found = False
                        for i, pattern in enumerate(login_patterns):
                            # print(f"DEBUG: Line {line_num}: Checking login pattern {i}...", file=sys.stderr) # Commented out
                            login_match = pattern.search(message)
                            if login_match:
                                # print(f"DEBUG: Line {line_num}: Matched login pattern {i}.", file=sys.stderr) # Commented out
                                user_logged_in = login_match.group(1).strip()
                                logins_per_day[date_str].add(user_logged_in)
                                total_logins_per_day[date_str] += 1
                                all_unique_logins.add(user_logged_in)
                                login_found = True
                                break
                        if login_found: continue

                        # print(f"DEBUG: Line {line_num}: Checking query pattern...", file=sys.stderr) # Commented out
                        query_match = query_pattern.search(message)
                        if query_match:
                            # print(f"DEBUG: Line {line_num}: Matched query pattern.", file=sys.stderr) # Commented out
                            queries.append(query_match.group(1).strip())
                            continue

                        # print(f"DEBUG: Line {line_num}: Checking signup pattern...", file=sys.stderr) # Commented out
                        signup_match = signup_pattern.search(message)
                        if signup_match:
                            # print(f"DEBUG: Line {line_num}: Matched signup pattern.", file=sys.stderr) # Commented out
                            signups.add(signup_match.group(1).strip())
                            continue

                        # print(f"DEBUG: Line {line_num}: Checking new chat pattern...", file=sys.stderr) # Commented out
                        chat_match = new_chat_pattern.search(message)
                        if chat_match:
                            # print(f"DEBUG: Line {line_num}: Matched new chat pattern.", file=sys.stderr) # Commented out
                            chats_started += 1
                            continue
                        # print(f"DEBUG: Line {line_num}: No INFO pattern matched.", file=sys.stderr) # Commented out


                    elif level in ("WARNING", "ERROR"):
                        # print(f"DEBUG: Line {line_num}: Checking WARNING/ERROR patterns...", file=sys.stderr) # Commented out
                        errors_warnings.append(line)

                        # print(f"DEBUG: Line {line_num}: Checking login failed pattern...", file=sys.stderr) # Commented out
                        login_fail_match = login_failed_pattern.search(message)
                        if login_fail_match:
                            # print(f"DEBUG: Line {line_num}: Matched login failed pattern.", file=sys.stderr) # Commented out
                            error_warning_summary[
                                f"Login failed (Invalid credentials): {login_fail_match.group(1).strip()}"
                            ] += 1
                            continue

                        # print(f"DEBUG: Line {line_num}: Checking invalid email pattern...", file=sys.stderr) # Commented out
                        invalid_email_match = invalid_email_pattern.search(message)
                        if invalid_email_match:
                            # print(f"DEBUG: Line {line_num}: Matched invalid email pattern.", file=sys.stderr) # Commented out
                            error_warning_summary[
                                f"Invalid email address format: {invalid_email_match.group(1).strip()}"
                            ] += 1
                            continue

                        # print(f"DEBUG: Line {line_num}: No specific WARNING/ERROR pattern matched, adding generic.", file=sys.stderr) # Commented out
                        error_warning_summary[f"{level}: {message}"] += 1

                except ValueError as ve:
                    print(
                        f"Warning: Skipping line {line_num} due to data conversion error (e.g., date): {ve} - Line: {line[:100]}...",
                        file=sys.stderr,
                    )
                    malformed_lines += 1
                    continue
                except Exception as inner_e:
                    print(
                        f"ERROR: Unexpected error processing *matched* line {line_num}: {inner_e}",
                        file=sys.stderr,
                    )
                    print(f"DEBUG: Problematic line content: {line[:200]}", file=sys.stderr)
                    traceback.print_exc(file=sys.stderr)
                    malformed_lines += 1
                    continue

            print(f"DEBUG: Finished processing loop. Processed {processed_lines} valid format lines.", file=sys.stderr)

    except FileNotFoundError:
        print(f"Error: Log file not found at '{log_file_path}'", file=sys.stderr)
        return None
    except UnicodeDecodeError as ude:
        print(f"Error: Could not decode file '{log_file_path}' with encoding '{file_encoding}'.", file=sys.stderr)
        print(f"Details: {ude}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"FATAL Error during file processing: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return None

    print(f"DEBUG: Preparing analysis dictionary. Skipped {malformed_lines} lines.", file=sys.stderr)
    analysis = {
        "log_file": log_file_path,
        "start_date": first_timestamp.strftime("%Y-%m-%d %H:%M:%S") if first_timestamp else "N/A",
        "end_date": last_timestamp.strftime("%Y-%m-%d %H:%M:%S") if last_timestamp else "N/A",
        "total_queries": len(queries),
        "unique_queries": len(set(queries)),
        "top_queries": Counter(queries).most_common(top_n),
        "total_logins_overall": sum(total_logins_per_day.values()),
        "unique_logins_overall": len(all_unique_logins),
        "logins_per_day": {
            date: {"total": total_logins_per_day[date], "unique": len(users), "users": sorted(list(users))}
            for date, users in logins_per_day.items()
        },
        "total_errors_warnings": len(errors_warnings),
        "top_errors_warnings_summary": error_warning_summary.most_common(top_n),
        "all_errors_warnings_lines": errors_warnings,
        "total_signups": len(signups),
        "unique_signups": sorted(list(signups)),
        "total_chats_started": chats_started,
        "malformed_lines_skipped": malformed_lines,
        "processed_lines_count": processed_lines,
    }
    print("DEBUG: Returning analysis dictionary.", file=sys.stderr)
    return analysis


# --- print_analysis function remains the same ---
def print_analysis(analysis, top_n=10, show_all_errors=False):
    """Prints the analysis results in a readable format."""
    print("DEBUG: Inside print_analysis function.", file=sys.stderr)
    if not analysis:
        print("Error: Analysis data is missing, cannot generate report.", file=sys.stderr)
        return

    try:
        # --- Print results to Standard Output ---
        print("-" * 80)
        print(f"Log Analysis Report for: {analysis['log_file']}")
        print(f"Log Date Range: {analysis['start_date']} to {analysis['end_date']}")
        print(f"Lines Matching Format: {analysis['processed_lines_count']}")
        print(f"Malformed/Skipped/Error Lines: {analysis['malformed_lines_skipped']}")
        print("-" * 80)
        sys.stdout.flush()

        print("\n--- Query Summary ---")
        print(f"Total Queries: {analysis['total_queries']}")
        print(f"Unique Queries: {analysis['unique_queries']}")
        print(f"\nTop {min(top_n, len(analysis['top_queries']))} Most Common Queries:")
        if analysis["top_queries"]:
            for query, count in analysis["top_queries"]:
                print(f"  ({count} times) '{query}'")
        else:
            print("  No valid queries found.")
        sys.stdout.flush()

        print("\n--- Login Summary ---")
        print(f"Total Login Events (Overall): {analysis['total_logins_overall']}")
        print(f"Unique Users Logged In (Overall): {analysis['unique_logins_overall']}")
        print("\nLogins Per Day:")
        if analysis["logins_per_day"]:
            for date in sorted(analysis["logins_per_day"].keys()):
                stats = analysis["logins_per_day"][date]
                print(
                    f"  {date}: Total Logins = {stats['total']}, Unique Users = {stats['unique']}"
                )
        else:
            print("  No valid login events found.")
        sys.stdout.flush()

        print("\n--- Error/Warning Summary ---")
        print(f"Total Errors/Warnings Logged (from valid lines): {analysis['total_errors_warnings']}")
        print(
            f"\nTop {min(top_n, len(analysis['top_errors_warnings_summary']))} Most Common Error/Warning Types:"
        )
        if analysis["top_errors_warnings_summary"]:
            for msg, count in analysis["top_errors_warnings_summary"]:
                print(f"  ({count} times) {msg}")
        else:
            print("  No valid errors or warnings found.")
        sys.stdout.flush()

        if show_all_errors and analysis["all_errors_warnings_lines"]:
            print("\nFull Error/Warning Log Lines (from valid lines):")
            for line in analysis["all_errors_warnings_lines"]:
                print(f"  {line}")
            sys.stdout.flush()

        print("\n--- Additional Stats ---")
        print(f"Total New User Signups: {analysis['total_signups']}")
        if analysis["unique_signups"]:
            print("  New Users (email):")
            for user in analysis["unique_signups"]:
                print(f"    - {user}")
        else:
            print("  No valid signups found.")
        print(f"Total New Chats Started: {analysis['total_chats_started']}")
        sys.stdout.flush()

        print("-" * 80)
        sys.stdout.flush()

    except Exception as e:
        print(f"\nFATAL ERROR occurred within print_analysis function: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)


# --- Main Execution ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Analyze expert-system chat server log files."
    )
    parser.add_argument("logfile", help="Path to the log file to analyze.")
    parser.add_argument("-n", "--top", type=int, default=10, help="Number of top queries/errors to display")
    parser.add_argument("--all-errors", action="store_true", help="Display all individual error/warning log lines.")

    args = parser.parse_args()

    print("DEBUG: Starting main execution block.", file=sys.stderr)
    results = analyze_log_file(args.logfile, top_n=args.top)

    print("DEBUG: analyze_log_file returned. Checking results...", file=sys.stderr)
    if results:
        print("DEBUG: Results object exists. Calling print_analysis...", file=sys.stderr)
        print_analysis(results, top_n=args.top, show_all_errors=args.all_errors)
        print("DEBUG: print_analysis finished.", file=sys.stderr)
    else:
        print("\nAnalysis could not be completed due to errors reported above.", file=sys.stderr)

    print("--- SCRIPT FINISHED (stdout) ---")
    sys.stdout.flush()

    print("DEBUG: End of script.", file=sys.stderr)

