"""CLI tool for satellite Doppler shift computation."""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.live import Live
from rich.table import Table

from doppler_core.doppler import compute_doppler, compute_doppler_series
from doppler_core.models import GroundStation, TLEData, parse_tle_file
from doppler_core.propagator import load_satellite, predict_passes

console = Console()

# Local ground station config file
_STATIONS_DIR = Path.home() / ".doppler"
_STATIONS_FILE = _STATIONS_DIR / "stations.json"


def _load_local_stations() -> dict:
    """Load ground stations from local JSON config."""
    if _STATIONS_FILE.exists():
        return json.loads(_STATIONS_FILE.read_text())
    return {}


def _save_local_stations(stations: dict) -> None:
    """Save ground stations to local JSON config."""
    _STATIONS_DIR.mkdir(parents=True, exist_ok=True)
    _STATIONS_FILE.write_text(json.dumps(stations, indent=2))


def _load_tles(tle: Optional[str], tle_file: Optional[str]) -> list[TLEData]:
    """Load TLE data from either inline string or file."""
    if tle_file:
        content = Path(tle_file).read_text()
        tles = parse_tle_file(content)
        if not tles:
            console.print("[red]No valid TLEs found in file.[/red]")
            sys.exit(1)
        return tles
    elif tle:
        lines = tle.replace("\\n", "\n").strip().splitlines()
        lines = [l.strip() for l in lines if l.strip()]
        if len(lines) == 2:
            return [TLEData(name=f"SAT-{lines[0][2:7].strip()}", line1=lines[0], line2=lines[1])]
        elif len(lines) >= 3:
            return [TLEData(name=lines[0], line1=lines[1], line2=lines[2])]
        else:
            console.print("[red]Invalid TLE format. Provide name + line1 + line2.[/red]")
            sys.exit(1)
    else:
        console.print("[red]Provide either --tle or --tle-file.[/red]")
        sys.exit(1)


def _resolve_ground_station(
    station_name: Optional[str], lat: Optional[float], lon: Optional[float], alt: float
) -> GroundStation:
    """Resolve ground station from name or coordinates."""
    if station_name:
        stations = _load_local_stations()
        if station_name not in stations:
            console.print(f"[red]Ground station '{station_name}' not found.[/red]")
            console.print("[dim]Use 'doppler config add-station' to add one.[/dim]")
            sys.exit(1)
        s = stations[station_name]
        return GroundStation(
            name=station_name,
            latitude_deg=s["latitude_deg"],
            longitude_deg=s["longitude_deg"],
            elevation_m=s.get("elevation_m", 0.0),
        )
    elif lat is not None and lon is not None:
        return GroundStation(latitude_deg=lat, longitude_deg=lon, elevation_m=alt)
    else:
        console.print("[red]Provide --ground-station NAME or --lat/--lon.[/red]")
        sys.exit(1)


@click.group()
def cli():
    """Satellite Doppler Shift Calculator."""
    pass


# --- Compute ---


@cli.command()
@click.option("--tle", type=str, default=None, help="Inline TLE (name\\nline1\\nline2)")
@click.option("--tle-file", type=click.Path(exists=True), default=None, help="Path to TLE file")
@click.option("--freq", type=float, required=True, help="Transmitted frequency in Hz")
@click.option("--lat", type=float, default=None, help="Ground station latitude (degrees)")
@click.option("--lon", type=float, default=None, help="Ground station longitude (degrees)")
@click.option("--alt", type=float, default=0.0, help="Ground station altitude (meters)")
@click.option("--ground-station", "station_name", type=str, default=None, help="Named ground station")
def compute(tle, tle_file, freq, lat, lon, alt, station_name):
    """Compute Doppler shift for satellite(s) at current time."""
    tles = _load_tles(tle, tle_file)
    gs = _resolve_ground_station(station_name, lat, lon, alt)

    table = Table(title="Doppler Shift Computation")
    table.add_column("Satellite", style="cyan")
    table.add_column("Az (deg)", justify="right")
    table.add_column("El (deg)", justify="right")
    table.add_column("Range (km)", justify="right")
    table.add_column("Range Rate (km/s)", justify="right")
    table.add_column("Doppler (Hz)", justify="right", style="green")
    table.add_column("Rx Freq (Hz)", justify="right", style="yellow")

    for t in tles:
        result = compute_doppler(t, gs, freq)
        table.add_row(
            result.satellite_name,
            f"{result.azimuth_deg:.1f}",
            f"{result.elevation_deg:.1f}",
            f"{result.range_km:.1f}",
            f"{result.range_rate_km_s:.4f}",
            f"{result.doppler_shift_hz:+.1f}",
            f"{result.received_frequency_hz:.3f}",
        )

    console.print()
    console.print(f"[dim]Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}[/dim]")
    console.print(f"[dim]Ground Station: {gs.name} ({gs.latitude_deg:.4f}N, {gs.longitude_deg:.4f}E, {gs.elevation_m:.0f}m)[/dim]")
    console.print(f"[dim]Tx Frequency: {freq:,.0f} Hz[/dim]")
    console.print(table)


# --- Track ---


@cli.command()
@click.option("--tle", type=str, default=None, help="Inline TLE (name\\nline1\\nline2)")
@click.option("--tle-file", type=click.Path(exists=True), default=None, help="Path to TLE file")
@click.option("--freq", type=float, required=True, help="Transmitted frequency in Hz")
@click.option("--lat", type=float, default=None, help="Ground station latitude (degrees)")
@click.option("--lon", type=float, default=None, help="Ground station longitude (degrees)")
@click.option("--alt", type=float, default=0.0, help="Ground station altitude (meters)")
@click.option("--ground-station", "station_name", type=str, default=None, help="Named ground station")
@click.option("--interval", type=float, default=1.0, help="Update interval in seconds")
def track(tle, tle_file, freq, lat, lon, alt, station_name, interval):
    """Live-track satellite Doppler shift (Ctrl+C to stop)."""
    tles = _load_tles(tle, tle_file)
    gs = _resolve_ground_station(station_name, lat, lon, alt)

    console.print(f"[bold]Tracking {len(tles)} satellite(s) at {freq:,.0f} Hz[/bold]")
    console.print(f"[dim]Ground Station: {gs.name} | Interval: {interval}s[/dim]")
    console.print("[dim]Press Ctrl+C to stop[/dim]\n")

    def make_table() -> Table:
        table = Table(title=f"Live Tracking - {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}")
        table.add_column("Satellite", style="cyan")
        table.add_column("Az", justify="right")
        table.add_column("El", justify="right")
        table.add_column("Range (km)", justify="right")
        table.add_column("Rate (km/s)", justify="right")
        table.add_column("Doppler (Hz)", justify="right", style="green")
        table.add_column("Rx Freq (Hz)", justify="right", style="yellow")
        table.add_column("Status", justify="center")

        for t in tles:
            result = compute_doppler(t, gs, freq)
            status = (
                "[green]VISIBLE[/green]"
                if result.elevation_deg > 0
                else "[dim]below horizon[/dim]"
            )
            table.add_row(
                result.satellite_name,
                f"{result.azimuth_deg:.1f}",
                f"{result.elevation_deg:.1f}",
                f"{result.range_km:.1f}",
                f"{result.range_rate_km_s:.4f}",
                f"{result.doppler_shift_hz:+.1f}",
                f"{result.received_frequency_hz:.3f}",
                status,
            )
        return table

    try:
        with Live(make_table(), console=console, refresh_per_second=2) as live:
            while True:
                time.sleep(interval)
                live.update(make_table())
    except KeyboardInterrupt:
        console.print("\n[yellow]Tracking stopped.[/yellow]")


# --- Passes ---


@cli.command()
@click.option("--tle", type=str, default=None, help="Inline TLE (name\\nline1\\nline2)")
@click.option("--tle-file", type=click.Path(exists=True), default=None, help="Path to TLE file")
@click.option("--lat", type=float, default=None, help="Ground station latitude (degrees)")
@click.option("--lon", type=float, default=None, help="Ground station longitude (degrees)")
@click.option("--alt", type=float, default=0.0, help="Ground station altitude (meters)")
@click.option("--ground-station", "station_name", type=str, default=None, help="Named ground station")
@click.option("--days", type=int, default=3, help="Number of days to predict")
@click.option("--min-el", type=float, default=10.0, help="Minimum elevation in degrees")
def passes(tle, tle_file, lat, lon, alt, station_name, days, min_el):
    """Predict upcoming satellite passes."""
    tles = _load_tles(tle, tle_file)
    gs = _resolve_ground_station(station_name, lat, lon, alt)

    now = datetime.now(timezone.utc)
    end = now + timedelta(days=days)

    for t in tles:
        sat = load_satellite(t)
        pass_list = predict_passes(sat, gs, now, end, min_elevation_deg=min_el)

        table = Table(title=f"Passes for {t.name} (next {days} days, min el {min_el}deg)")
        table.add_column("#", justify="right", style="dim")
        table.add_column("AOS (UTC)", style="cyan")
        table.add_column("Max El (UTC)")
        table.add_column("LOS (UTC)", style="cyan")
        table.add_column("Max El (deg)", justify="right", style="green")
        table.add_column("Duration", justify="right")

        if not pass_list:
            console.print(f"[yellow]No passes found for {t.name}[/yellow]")
            continue

        for idx, p in enumerate(pass_list, 1):
            mins = int(p.duration_seconds // 60)
            secs = int(p.duration_seconds % 60)
            table.add_row(
                str(idx),
                p.aos_time.strftime("%Y-%m-%d %H:%M:%S"),
                p.max_elevation_time.strftime("%H:%M:%S"),
                p.los_time.strftime("%Y-%m-%d %H:%M:%S"),
                f"{p.max_elevation_deg:.1f}",
                f"{mins}m {secs}s",
            )

        console.print(table)


# --- Fetch ---


@cli.command()
@click.option("--norad-id", type=int, default=None, help="NORAD catalog number")
@click.option("--group", type=str, default=None, help="Celestrak group (e.g., 'stations', 'active')")
@click.option("--output", type=click.Path(), default=None, help="Save TLE to file")
def fetch(norad_id, group, output):
    """Fetch live TLE data from Celestrak."""
    import asyncio
    from services.tle_fetcher import TLEFetcher

    async def _fetch():
        fetcher = TLEFetcher()
        if norad_id:
            tles = [await fetcher.fetch_by_norad_id(norad_id)]
        elif group:
            tles = await fetcher.fetch_by_group(group)
        else:
            console.print("[red]Provide --norad-id or --group.[/red]")
            sys.exit(1)
        return tles

    try:
        tles = asyncio.run(_fetch())
    except Exception as e:
        console.print(f"[red]Fetch failed: {e}[/red]")
        sys.exit(1)

    if output:
        content = ""
        for tle in tles:
            content += f"{tle.name}\n{tle.line1}\n{tle.line2}\n"
        Path(output).write_text(content)
        console.print(f"[green]Saved {len(tles)} TLE(s) to {output}[/green]")
    else:
        for tle in tles:
            console.print(f"[cyan]{tle.name}[/cyan]")
            console.print(f"  {tle.line1}")
            console.print(f"  {tle.line2}")
        console.print(f"\n[dim]{len(tles)} satellite(s) fetched[/dim]")


# --- Serve ---


@cli.command()
@click.option("--host", type=str, default="0.0.0.0", help="Host to bind to")
@click.option("--port", type=int, default=8000, help="Port to bind to")
@click.option("--reload", is_flag=True, help="Enable auto-reload for development")
def serve(host, port, reload):
    """Start the API server."""
    import uvicorn

    console.print(f"[bold]Starting API server on {host}:{port}[/bold]")
    uvicorn.run("api.main:app", host=host, port=port, reload=reload)


# --- Config (ground station management) ---


@cli.group()
def config():
    """Manage local configuration (ground stations)."""
    pass


@config.command("add-station")
@click.option("--name", required=True, help="Station name")
@click.option("--lat", type=float, required=True, help="Latitude (degrees)")
@click.option("--lon", type=float, required=True, help="Longitude (degrees)")
@click.option("--alt", type=float, default=0.0, help="Altitude (meters)")
def add_station(name, lat, lon, alt):
    """Add a named ground station to local config."""
    stations = _load_local_stations()
    stations[name] = {"latitude_deg": lat, "longitude_deg": lon, "elevation_m": alt}
    _save_local_stations(stations)
    console.print(f"[green]Added ground station '{name}' ({lat}, {lon}, {alt}m)[/green]")


@config.command("list-stations")
def list_stations():
    """List saved ground stations."""
    stations = _load_local_stations()
    if not stations:
        console.print("[dim]No ground stations saved. Use 'doppler config add-station'.[/dim]")
        return

    table = Table(title="Saved Ground Stations")
    table.add_column("Name", style="cyan")
    table.add_column("Latitude", justify="right")
    table.add_column("Longitude", justify="right")
    table.add_column("Altitude (m)", justify="right")

    for name, s in stations.items():
        table.add_row(name, f"{s['latitude_deg']:.4f}", f"{s['longitude_deg']:.4f}", f"{s.get('elevation_m', 0):.0f}")

    console.print(table)


@config.command("remove-station")
@click.option("--name", required=True, help="Station name to remove")
def remove_station(name):
    """Remove a ground station from local config."""
    stations = _load_local_stations()
    if name not in stations:
        console.print(f"[red]Ground station '{name}' not found.[/red]")
        sys.exit(1)
    del stations[name]
    _save_local_stations(stations)
    console.print(f"[green]Removed ground station '{name}'[/green]")


if __name__ == "__main__":
    cli()
