"""Command line interface for :mod:`ror_downloader`."""

import click
from more_click import verbose_option

__all__ = [
    "main",
]


@click.group()
def main() -> None:
    """CLI for ror_downloader."""


@main.command()
@verbose_option
def version() -> None:
    """Print the current version."""
    from .api import get_version_info

    status = get_version_info(download=False)
    if status.date is not None:
        click.secho(f"{status.version}, released on {status.date.isoformat()}", fg="green")
    else:
        click.secho(f"{status.version}", fg="green")


@main.command()
@click.option("--force", is_flag=True)
def cache(force: bool) -> None:
    """Download, parse, and cache ROR."""
    from .api import get_organizations

    get_organizations(force=force)


if __name__ == "__main__":
    main()
