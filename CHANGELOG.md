## v0.3.0 (March 27, 2025)

- Extract background process management and related complexities from the `track_resources` decorator into the `ResourceTracker` class to track resource usage of a process and/or the system in a non-blocking way.
- Add unit tests for the `ResourceTracker` class, including checks for deadlocks and partially started trackers.
- Improve documentation

## v0.2.1 (March 21, 2025)

- Fix don't always round up CPU/GPU recommendations
- Improve error message on missing historical data
- Improve documentation

## v0.2.0 (March 21, 2025)

Relatively major package rewrite to support alternative tracker implementations (other than directly reading from `/proc`). No breaking changes in the public API on Linux.

- Add tracker implementation using `psutil` to support MacOS and Windows
- Fix data issues with the `/proc` implementation after validating with the `psutil` version (e.g. number of processes reported)
- Refactor code for better maintainability
- Add additional unit tests:
    - Tracker implementation using `procfs`
    - Tracker implementation using `psutil`
    - Consistency between tracker implementations
    - Metaflow decorators
- Extend CI/CD pipeline:
    - Test on Linux, MacOS, and Windows
    - Test multiple Python versions (3.9, 3.10, 3.11, 3.12, 3.13)
- Improve documentation

## v0.1.2 (March 18, 2025)

- Add experimental psutil support
- Add server info card for operating system

## v0.1.1 (March 17, 2025)

- Fix rounding down recommended vCPUs with <0.5 load
- Add info popups with more details and disclaimers for recommendations
- Add detection for shared server environments
- Add potential cost savings card
- Improve documentation

## v0.1.0 (March 12, 2025)

Initial PyPI release of `resource-tracker` with the following features:

- Detect if the system is running on a cloud provider, and if so, detect the provider, region, and instance type
- Detect main server hardware (CPU count, memory amount, disk space, GPU count and VRAM amount)
- Track system-wide resource usage:
    - Process count
    - CPU usage (user + system time, relative vCPU percentage)
    - Memory usage (total, free, used, buffers, cached, active anon, inactive anon pages)
    - Disk I/O (read and write bytes)
    - Disk space usage (total, used, free)
    - Network I/O (receive and transmit bytes)
    - GPU and VRAM usage (using `nvidia-smi`)
- Track resource usage of a process and its descendant processes:
    - Descendant process count
    - CPU usage (user + system time, relative vCPU percentage)
    - Memory usage (based on proportional set sizes)
    - Disk I/O (read and write bytes)
    - GPU and VRAM usage (using `nvidia-smi pmon`)
- Add Metaflow plugin for tracking resource usage of a step:
    - Track process and system resource usage for the duration of the step
    - Generate a card with the resource usage data
    - Suggest `@resources` decorator for future runs
    - Find cheapest cloud instance type for a step
