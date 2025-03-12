# resource-tracker

A Python package for tracking resource usage of processes and system-wide,
with a focus on batch jobs like Metaflow steps.

## Installation

You can install the stable version of the package from PyPI:

```sh
pip install resource-tracker
```

Development version can be installed directly from the repository:

```sh
pip install git+https://github.com/sparecores/resource-tracker.git
```

## Standalone Usage

The package comes with helper functions and classes for tracking resource usage,
such as `PidTracker` and `SystemTracker`:

```python
from resource_tracker import SystemTracker
tracker = SystemTracker()
```

Would track system-wide resource usage, including CPU, memory, GPU, network
traffic, disk I/O and space usage every 1 second, and write CSV to the standard
output stream by default, e.g.:

```sh
"timestamp","processes","utime","stime","cpu_usage","memory_free","memory_used","memory_buffers","memory_cached","memory_active_anon","memory_inactive_anon","disk_read_bytes","disk_write_bytes","disk_space_total_gb","disk_space_used_gb","disk_space_free_gb","net_recv_bytes","net_sent_bytes","gpu_usage","gpu_vram","gpu_utilized"
1741785685.6762981,1147955,40,31,0.7098,37828072,26322980,16,1400724,13080320,1009284,86016,401408,5635.25,3405.81,2229.44,10382,13140,0.24,1034.0,1
1741785686.676473,1147984,23,49,0.7199,37836696,26316404,16,1398676,13071060,1009284,86016,7000064,5635.25,3405.81,2229.44,1369,1824,0.15,1033.0,1
1741785687.6766264,1148012,38,34,0.7199,37850036,26301016,16,1400724,13043036,1009284,40960,49152,5635.25,3405.81,2229.44,10602,9682,0.26,1029.0,1
```

This can be redirected to a file by passing a path to the `csv_file_path`
argument, and can use different intervals for sampling via the `interval`
argument.

The `PidTracker` class tracks resource usage of a running process and its
children recursively in a similar manner, although somewhat limited in
functionality, as e.g. `nvidia-smi pmon` can only track up-to 4 GPUs, and
network traffic monitoring is not available.

Helpers functions are also provided for tracking memory usage, e.g.
`get_pid_stats` and `get_system_stats` for current process and system-wide stats
-- which are used internally by the above classes after diffing values between
subsequent calls. See more details in the
[API References](https://sparecores.github.io/resource-tracker/reference/resource_tracker/tracker/.

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

## Metaflow Integration

The package also comes with a Metaflow extension for tracking resource usage of
Metaflow steps, including the visualization of the collected data in a card with
recommended `@resources` and cheapest cloud server type for future runs.

To get started, import the `track_resources` decorator from `metaflow` and use it to decorate your
Metaflow steps:

```python
from metaflow import Flow, FlowSpec, step, track_resources

class ResourceTrackingFlow(FlowSpec):
    @step
    def start(self):
        print("Starting step")
        self.next(self.my_sleeping_data)

    @track_resources
    @step
    def my_sleeping_data(self):
        data = bytearray(500 * 1024 * 1024)  # 500MB
        sleep(3)
        self.next(self.end)

    @step
    def end(self):
        print("Step finished")
        pass

if __name__ == "__main__":
    ResourceTrackingFlow()
```

Example output in the means of a Metaflow card:

![Resource Tracking Card in Metaflow](https://sparecores.github.io/resource-tracker/track_resources-card-example.png)

Find more examples in the [examples](https://github.com/SpareCores/resource-tracker/tree/main/examples) directory, including multiple Metaflow flows with different resource usage patterns, e.g. GPU jobs as well.


