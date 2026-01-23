"""Command line interface for :mod:`ror_downloader`."""

import click

__all__ = [
    "main",
]


@click.command()
@click.option("--force", is_flag=True)
def main(force: bool) -> None:
    """CLI for ror_downloader."""
    from .api import get_organizations

    get_organizations(force=force)


if __name__ == "__main__":
    main()
