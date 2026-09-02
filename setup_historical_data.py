import subprocess
import sys
import time


def run_step(
    name,
    script
):

    print(
        "\n"
        + "=" * 70
    )

    print(
        f"Running: {name}"
    )

    print(
        "=" * 70
    )

    start = time.time()

    subprocess.run(
        [
            sys.executable,
            script
        ],
        check=True
    )

    runtime = round(
        time.time()
        - start,
        1
    )

    print(
        f"\n✅ Completed: {name}"
    )

    print(
        f"Runtime: {runtime}s"
    )


def main():

    overall_start = time.time()

    steps = [

        (
            "Import Historical Events",
            "training/import_historical_events.py"
        ),

        (
            "Build Historical Team Intelligence",
            "training/build_historical_team_intelligence.py"
        ),

        (
            "Build Historical Advanced Features",
            "training/build_historical_advanced_features.py"
        )
    ]

    print(
        "\n"
        + "=" * 70
    )

    print(
        "TURNAROUND IQ - HISTORICAL SETUP"
    )

    print(
        "=" * 70
    )

    for name, script in steps:

        run_step(
            name,
            script
        )

    total_runtime = round(
        time.time()
        - overall_start,
        1
    )

    print(
        "\n"
        + "=" * 70
    )

    print(
        "HISTORICAL SETUP COMPLETE"
    )

    print(
        "=" * 70
    )

    print(
        f"Total Runtime: {total_runtime}s"
    )

    print(
        "\n✅ Historical database ready."
    )


if __name__ == "__main__":

    main()
