# Resource Tracking examples

This folder includes example scripts demonstrating the use of the
`resource_tracker` Python package in general and the `track_resources` decorator
in Metaflow.

## Standalone 

The `resource_tracker` package provides the following classes that can be used to track
resources of a running process (and its children) or system-wide resources.

* `PidTracker`: Track resources of a running process and its children.
* `SystemTracker`: Track system-wide resources.

## Metaflow

### 1-single-step.py

This script demonstrates the use of the `track_resources` decorator on a single
step, which burns CPU on a single core, then on 6 cores, and also reserves 500
MB of memory.

Example run:

```sh
cd examples/metaflow
python 1-single-step.py run
```

Once the script finished, you can visualize the resource usage by checking the
Metaflow UI, or search for the generated HTML in your local enviromment, e.g.:

```sh
xdg-open .metaflow/mf.cards/ResourceTrackingFlow/runs/$(cat .metaflow/ResourceTrackingFlow/latest_run)/steps/do_heavy_computation/tasks/2/cards/tracked_resources-resource_tracker_do_heavy_computation*.html
```

To load the collected data in Python, you can access the artifact of the step:

```python
from metaflow import Flow


Flow("ResourceTrackingFlow").latest_run.data.resource_tracker_data
```

This latter is a dictionary of `TinyDataFrame` objects, which are a thin wrapper
around a dictionary of column vectors. To get a quick overview of the data, you
can use the `print` method, printing the first 10 rows in a human-readable table:

```python
df = Flow("ResourceTrackingFlow").latest_run.data.resource_tracker_data
print(df)
```

### 2-gpu.py

This script demonstrates the monitoring of GPU usage using the `track_resources`
decorator. It runs two ~heavy computations on the GPU for a few seconds.

Example run:

```sh
python 2-gpu.py --environment=pypi run
```
