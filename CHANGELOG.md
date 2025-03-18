## v0.1.2 (March 18, 2025)

- Experimental psutil support
- Add server info card for operating system

## v0.1.1 (March 17, 2025)

- Fix rounding down recommended vCPUs with <0.5 load
- Add info popups with more details and disclaimers for recommendations
- Detect if the server is shared with other tasks
- Add potential cost savings card
- Documentation improvements

## v0.1.0 (March 12, 2025)

Initial PyPI release of `resource-tracker` with the following features:

- Detect if the system is running on a cloud provider, and if so, detect the provider, region, and instance type.
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
- Metaflow plugin for tracking resource usage of a step:
    - Track process and system resource usage for the duration of the step
    - Generate a card with the resource usage data
    - Suggest `@resources` decorator for future runs
    - Find cheapest cloud instance type for a step
