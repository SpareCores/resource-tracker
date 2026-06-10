"""Subprocess entry point for background ResourceTracker workers.

On Windows, ``ResourceTracker`` starts tracker workers via ``python -m
resource_tracker._tracker_worker`` so the user's main script is not re-imported
during multiprocessing bootstrap.
"""

import argparse


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "tracker_type",
        choices=["process", "system"],
        help="Which tracker to run in the background.",
    )
    parser.add_argument("--start-time", type=float, required=True)
    parser.add_argument("--interval", type=float, required=True)
    parser.add_argument("--output-file", required=True)
    parser.add_argument("--error-file", required=True)
    parser.add_argument("--pid", type=int)
    parser.add_argument(
        "--children",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Track child processes (process tracker only).",
    )
    args = parser.parse_args(argv)

    if args.tracker_type == "process" and args.pid is None:
        parser.error("--pid is required for the process tracker")

    from .tracker import _run_tracker

    kwargs = {
        "start_time": args.start_time,
        "interval": args.interval,
        "output_file": args.output_file,
    }
    if args.tracker_type == "process":
        kwargs["pid"] = args.pid
        kwargs["children"] = args.children

    _run_tracker(
        args.tracker_type,
        error_queue=None,
        error_file=args.error_file,
        **kwargs,
    )


if __name__ == "__main__":
    main()
