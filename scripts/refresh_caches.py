from __future__ import annotations

import argparse
from pathlib import Path

from services.cache_refresh import refresh_all_pins


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh cached alerts for configured PIN codes.")
    parser.add_argument("--pin", dest="pin", help="Refresh a single PIN code instead of all configured pins")
    parser.add_argument(
        "--profiles",
        dest="profiles_path",
        type=Path,
        help="Override path to pincode_profiles.yaml",
    )
    parser.add_argument(
        "--settings",
        dest="settings_path",
        type=Path,
        help="Override path to cache_settings.yaml",
    )
    parser.add_argument(
        "--service",
        choices=["weather_alert", "seasonal_advisory", "feed_prices"],
        help="Refresh only one API service; omit to refresh all services",
    )
    args = parser.parse_args()

    refresh_all_pins(
        pin_profiles_path=args.profiles_path,
        cache_settings_path=args.settings_path,
        target_pin=args.pin,
        services=[args.service] if args.service else None,
    )


if __name__ == "__main__":
    main()
