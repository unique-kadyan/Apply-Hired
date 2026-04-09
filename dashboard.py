"""Rich CLI dashboard for viewing and managing job applications."""

import json
import webbrowser

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.columns import Columns
from rich.prompt import Prompt, IntPrompt, Confirm
from rich.text import Text

from tracker import get_jobs, get_stats, get_job_by_id, update_job_status
from cover_letter import generate_cover_letter

console = Console()


def _score_color(score: float) -> str:
    if score >= 0.7:
        return "bold green"
    elif score >= 0.5:
        return "yellow"
    elif score >= 0.3:
        return "dim yellow"
    return "red"


def _status_color(status: str) -> str:
    return {
        "new": "cyan",
        "saved": "blue",
        "applied": "green",
        "interview": "bold magenta",
        "rejected": "red",
        "offer": "bold green",
    }.get(status, "white")


def show_stats():
    """Display dashboard statistics."""
    stats = get_stats()

    cards = [
        Panel(f"[bold cyan]{stats['total']}[/]", title="Total Jobs"),
        Panel(f"[bold yellow]{stats['new']}[/]", title="New"),
        Panel(f"[bold blue]{stats['saved']}[/]", title="Saved"),
        Panel(f"[bold green]{stats['applied']}[/]", title="Applied"),
        Panel(f"[bold magenta]{stats['interview']}[/]", title="Interviews"),
        Panel(f"[bold]{stats['avg_score']:.1%}[/]", title="Avg Score"),
    ]
    console.print(Columns(cards, equal=True, expand=True))

    if stats["by_source"]:
        source_table = Table(title="Jobs by Source", show_lines=False)
        source_table.add_column("Source", style="cyan")
        source_table.add_column("Count", justify="right")
        for source, count in stats["by_source"].items():
            source_table.add_row(source, str(count))
        console.print(source_table)

    if stats["top_companies"]:
        console.print(
            Panel(
                ", ".join(stats["top_companies"]),
                title="Top Matching Companies",
                border_style="green",
            )
        )


def show_jobs(status: str = None, min_score: float = 0.0, limit: int = 30):
    """Display jobs in a table."""
    jobs = get_jobs(status=status, min_score=min_score, limit=limit)

    if not jobs:
        console.print("[dim]No jobs found with the given filters.[/]")
        return

    table = Table(title=f"Jobs ({len(jobs)} results)", show_lines=True, expand=True)
    table.add_column("ID", style="dim", width=4, justify="right")
    table.add_column("Score", width=6, justify="center")
    table.add_column("Title", min_width=25)
    table.add_column("Company", min_width=15)
    table.add_column("Source", width=10)
    table.add_column("Salary", width=15)
    table.add_column("Status", width=10)

    for job in jobs:
        score = job["score"]
        table.add_row(
            str(job["id"]),
            Text(f"{score:.0%}", style=_score_color(score)),
            job["title"][:40],
            job["company"][:20],
            job["source"],
            (job["salary"] or "-")[:15],
            Text(job["status"], style=_status_color(job["status"])),
        )

    console.print(table)


def show_job_detail(job_id: int):
    """Show full details of a single job."""
    job = get_job_by_id(job_id)
    if not job:
        console.print(f"[red]Job #{job_id} not found.[/]")
        return

    score = job["score"]
    score_details = json.loads(job.get("score_details", "{}"))

    console.print(Panel(
        f"[bold]{job['title']}[/]\n"
        f"[cyan]{job['company']}[/] | {job['location']} | {job['source']}\n"
        f"Salary: {job['salary'] or 'Not specified'}\n"
        f"Posted: {job['date_posted'] or 'Unknown'}\n"
        f"Status: [{_status_color(job['status'])}]{job['status']}[/]\n"
        f"Score: [{_score_color(score)}]{score:.0%}[/] "
        f"(local: {score_details.get('local_score', 'N/A')}, ai: {score_details.get('ai_score', 'N/A')})\n"
        f"URL: {job['url']}",
        title=f"Job #{job['id']}",
        border_style="cyan",
    ))

    # AI analysis if available
    if score_details.get("ai_reasons"):
        console.print(Panel(
            "\n".join(f"  - {r}" for r in score_details["ai_reasons"]),
            title="AI Match Analysis",
            border_style="green",
        ))
    if score_details.get("ai_missing_skills"):
        console.print(Panel(
            ", ".join(score_details["ai_missing_skills"]),
            title="Missing Skills",
            border_style="yellow",
        ))

    # Description
    desc = job.get("description", "")
    if desc:
        console.print(Panel(desc[:1500], title="Description", border_style="dim"))

    # Cover letter
    if job.get("cover_letter"):
        console.print(Panel(job["cover_letter"], title="Cover Letter", border_style="blue"))


def interactive_menu():
    """Interactive CLI menu for managing applications."""
    while True:
        console.print("\n[bold cyan]--- Job Application Bot ---[/]")
        console.print("1. Dashboard Stats")
        console.print("2. View All Jobs")
        console.print("3. View Top Matches (score > 50%)")
        console.print("4. View by Status")
        console.print("5. Job Detail")
        console.print("6. Update Job Status")
        console.print("7. Generate Cover Letter")
        console.print("8. Open Job URL")
        console.print("0. Back / Exit")

        choice = Prompt.ask("\nChoice", choices=["0", "1", "2", "3", "4", "5", "6", "7", "8"], default="1")

        if choice == "0":
            break
        elif choice == "1":
            show_stats()
        elif choice == "2":
            show_jobs()
        elif choice == "3":
            show_jobs(min_score=0.5)
        elif choice == "4":
            status = Prompt.ask("Status", choices=["new", "saved", "applied", "interview", "rejected"])
            show_jobs(status=status)
        elif choice == "5":
            job_id = IntPrompt.ask("Job ID")
            show_job_detail(job_id)
        elif choice == "6":
            job_id = IntPrompt.ask("Job ID")
            status = Prompt.ask("New status", choices=["new", "saved", "applied", "interview", "rejected", "offer"])
            notes = Prompt.ask("Notes (optional)", default="")
            update_job_status(job_id, status, notes)
            console.print(f"[green]Job #{job_id} updated to '{status}'[/]")
        elif choice == "7":
            job_id = IntPrompt.ask("Job ID")
            job_data = get_job_by_id(job_id)
            if job_data:
                from scrapers import Job
                job_obj = Job(
                    title=job_data["title"],
                    company=job_data["company"],
                    location=job_data["location"],
                    url=job_data["url"],
                    source=job_data["source"],
                    description=job_data.get("description", ""),
                    tags=json.loads(job_data.get("tags", "[]")),
                )
                letter = generate_cover_letter(job_obj)
                console.print(Panel(letter, title="Generated Cover Letter", border_style="green"))
                if Confirm.ask("Save this cover letter?"):
                    from tracker import _get_conn
                    conn = _get_conn()
                    conn.execute("UPDATE jobs SET cover_letter = ? WHERE id = ?", (letter, job_id))
                    conn.commit()
                    conn.close()
                    console.print("[green]Cover letter saved![/]")
        elif choice == "8":
            job_id = IntPrompt.ask("Job ID")
            job_data = get_job_by_id(job_id)
            if job_data and job_data.get("url"):
                webbrowser.open(job_data["url"])
                console.print(f"[green]Opened: {job_data['url']}[/]")
