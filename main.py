#!/usr/bin/env python3
"""
Job Application Bot — Automatically searches, matches, and tracks remote jobs.
Usage:
    python main.py search        Search all job boards and score matches
    python main.py dashboard     Open interactive dashboard
    python main.py stats         Show quick stats
    python main.py top           Show top 10 matches
    python main.py auto          Run search + scheduler (every 6 hours)
    python main.py export        Export top jobs to CSV
"""

import csv
import logging
import os
import sys
import time
from datetime import datetime

# Fix Windows Unicode encoding for Rich
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import schedule
from rich.console import Console
from rich.panel import Panel

from config import SEARCH_PREFERENCES
from cover_letter import generate_cover_letter
from dashboard import interactive_menu, show_job_detail, show_jobs, show_stats
from matcher import rank_jobs
from scrapers import ALL_SCRAPERS, search_all_boards
from tracker import get_jobs, init_db, log_search_run, save_job

console = Console()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
logger = logging.getLogger("kalibr")


def run_search(generate_letters: bool = False):
    """Run a full job search across all boards."""
    console.print(Panel(
        "[bold cyan]Job Application Bot[/]\n"
        f"Searching for: {', '.join(SEARCH_PREFERENCES['target_roles'][:5])}\n"
        f"Sources: {', '.join(s.name for s in ALL_SCRAPERS)}",
        title="Search Starting",
        border_style="cyan",
    ))

    queries = SEARCH_PREFERENCES["target_roles"][:5]

    # Step 1: Fetch jobs
    console.print("[cyan]Searching job boards...[/]")
    all_jobs = search_all_boards(queries)
    console.print(f"[green]Found {len(all_jobs)} jobs across all boards[/]")

    if not all_jobs:
        console.print("[yellow]No jobs found. Try adjusting your search keywords.[/]")
        return

    # Step 2: Score and rank
    console.print("[cyan]Scoring and ranking jobs...[/]")
    ranked = rank_jobs(all_jobs)

    console.print(f"\n[green]{len(ranked)} jobs passed the minimum match threshold ({SEARCH_PREFERENCES['min_experience_match']:.0%})[/]")

    # Step 3: Save to DB + generate cover letters
    new_count = 0
    console.print("[cyan]Saving results...[/]")
    for job, score_data in ranked:
        letter = ""
        if generate_letters and score_data["final_score"] >= 0.5:
            letter = generate_cover_letter(job)

        if save_job(job, score_data, letter):
            new_count += 1

    # Log the search run
    log_search_run(
        queries=queries,
        total_found=len(all_jobs),
        total_matched=len(ranked),
        sources=[s.name for s in ALL_SCRAPERS],
    )

    console.print(Panel(
        f"[bold green]Search complete![/]\n"
        f"Total scraped: {len(all_jobs)}\n"
        f"Matched (>{SEARCH_PREFERENCES['min_experience_match']:.0%}): {len(ranked)}\n"
        f"New jobs saved: {new_count}\n"
        f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        title="Results",
        border_style="green",
    ))

    # Show top 10
    if ranked:
        console.print("\n[bold]Top 10 Matches:[/]")
        show_jobs(min_score=0.0, limit=10)


def run_auto():
    """Run search on a schedule (every 6 hours)."""
    console.print("[bold cyan]Starting auto mode — searching every 6 hours[/]")
    console.print("[dim]Press Ctrl+C to stop[/]\n")

    run_search()  # Run immediately first

    schedule.every(6).hours.do(run_search)

    try:
        while True:
            schedule.run_pending()
            time.sleep(60)
    except KeyboardInterrupt:
        console.print("\n[yellow]Auto mode stopped.[/]")


def export_csv(filepath: str = "data/top_jobs.csv"):
    """Export top jobs to CSV."""
    jobs = get_jobs(min_score=0.3, limit=100)
    if not jobs:
        console.print("[yellow]No jobs to export.[/]")
        return

    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "id", "title", "company", "location", "url", "source",
            "salary", "score", "status", "date_posted",
        ])
        writer.writeheader()
        for job in jobs:
            writer.writerow({k: job.get(k, "") for k in writer.fieldnames})

    console.print(f"[green]Exported {len(jobs)} jobs to {filepath}[/]")


def main():
    init_db()

    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    command = sys.argv[1].lower()

    if command == "search":
        generate_letters = "--letters" in sys.argv
        run_search(generate_letters=generate_letters)
    elif command == "dashboard":
        interactive_menu()
    elif command == "stats":
        show_stats()
    elif command == "top":
        show_jobs(min_score=0.5, limit=10)
    elif command == "auto":
        run_auto()
    elif command == "export":
        filepath = sys.argv[2] if len(sys.argv) > 2 else "data/top_jobs.csv"
        export_csv(filepath)
    elif command == "detail":
        if len(sys.argv) > 2:
            show_job_detail(int(sys.argv[2]))
        else:
            console.print("[red]Usage: python main.py detail <job_id>[/]")
    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
