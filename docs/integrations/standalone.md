# Resource Tracker in Python

After [installing](/#installation) the zero-dependency `resource-tracker` Python package, you can start using it right away by initializing a `ResourceTracker` object and later calling its methods to summarize the resource usage.

Quick example featuring the most common use cases:

```python
from resource_tracker import ResourceTracker

tracker = ResourceTracker()
# your compute-heavy code
tracker.stop()

# your analytics code utilizing the collected data
tracker.process_metrics
tracker.system_metrics
tracker.get_combined_metrics()

# or more conveniently get combined statistics
tracker.stats()

# get recommendations for resource allocation and cloud server type
tracker.recommend_resources()
tracker.recommend_server()

# generate a HTML report on resource usage and recommendations
report = tracker.report()
report.save("report.html")
report.browse()
```

## Background Details

The `ResourceTracker` class runs trackers in the background. The underlying
`ProcessTracker` and `SystemTracker` classes log resource usage to a temporary
file, both using either `procfs` or `psutil` under the hood -- depending on
which is available, with a preference for `psutil` when both are present.

The `ResourceTracker` instance gives you access to the collected data in
real-time, or after stopping the trackers via the `process_metrics` and
`system_metrics` properties, or the `get_combined_metrics` method. Each of them
is a `TinyDataFrame` object, which is essentially a dictionary of lists, with
additional methods for e.g. printing and saving to a CSV file. See the
[standalone.py](https://github.com/SpareCores/resource-tracker/tree/main/examples/standalone.py)
for a more detailed actual usage example.

It's possible to track only the system-wide or process resource usage by the
related init parameters of `ResourceTracker`, just like controlling the sampling
interval, or how to start (e.g. spawn or fork) the subprocesses of the trackers.

For even more control, you can use the underlying `ProcessTracker` and
`SystemTracker` classes directly, which are not starting and handling new
processes in the background, but simply log resource usage to the standard
output or a file. For example, to track only the system-wide resource usage, you
can use the `SystemTracker` class:

```python
from resource_tracker import SystemTracker
tracker = SystemTracker()
```

`SystemTracker` tracks system-wide resource usage, including CPU, memory, GPU, network
traffic, disk I/O and space usage every 1 second, and write CSV to the standard
output stream by default. Example output:

```sh
# "timestamp","processes","utime","stime","cpu_usage","memory_free","memory_used","memory_buffers","memory_cached","memory_active","memory_inactive","disk_read_bytes","disk_write_bytes","disk_space_total_gb","disk_space_used_gb","disk_space_free_gb","net_recv_bytes","net_sent_bytes","gpu_usage","gpu_vram","gpu_utilized"
# 1741785685.6762981,1147955,40,31,0.7098,37828072,26322980,16,1400724,13080320,1009284,86016,401408,5635.25,3405.81,2229.44,10382,13140,0.24,1034.0,1
# 1741785686.676473,1147984,23,49,0.7199,37836696,26316404,16,1398676,13071060,1009284,86016,7000064,5635.25,3405.81,2229.44,1369,1824,0.15,1033.0,1
# 1741785687.6766264,1148012,38,34,0.7199,37850036,26301016,16,1400724,13043036,1009284,40960,49152,5635.25,3405.81,2229.44,10602,9682,0.26,1029.0,1
```

The default stream can be redirected to a file by passing a path to the `csv_file_path`
argument, and can use different intervals for sampling via the `interval`
argument.

The `ProcessTracker` class tracks resource usage of a running process (defaults to
the current process) and optionally all its children (recursively), in a similar
manner, although somewhat limited in functionality, as e.g. `nvidia-smi pmon`
can only track up-to 4 GPUs, and network traffic monitoring is not available.

Helper functions are also provided, e.g. `get_process_stats` and `get_system_stats`
from both the `tracker_procfs` and `tracker_psutil` modules, which are used
internally by the above classes after diffing values between subsequent calls.

See more details in the [API
References](https://sparecores.github.io/resource-tracker/reference/resource_tracker/tracker/).

## Discovery Helpers

The packages also comes with helpers for discovering the cloud environment and
basic server hardware specs. Quick example on an AWS EC2 instance:

```python
from resource_tracker import get_cloud_info, get_server_info
get_cloud_info()
# {'vendor': 'aws', 'instance_type': 'g4dn.xlarge', 'region': 'us-west-2', 'discovery_time': 0.1330404281616211}
get_server_info()
# {'vcpus': 4, 'memory_mb': 15788.21, 'gpu_count': 1, 'gpu_names': ['Tesla T4'], 'gpu_memory_mb': 15360.0}
```

Spare Cores integration can do further lookups for the current server type, e.g.
to calculate the cost of running the current job and recommend cheaper cloud
server types for future runs.
