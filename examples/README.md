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
python 1-single-step.py card view do_heavy_computation
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

This script demonstrates the monitoring of GPU utilization using the
`track_resources` decorator. It runs two math operations on the GPU for a
few seconds.

Example run:

```sh
python 2-gpu.py --environment=pypi run
python 2-gpu.py card view do_heavy_computation
```

### 3-gbm.py

This script implements a more realistic example of a machine learning pipeline
using XGBoost, by downloading training data then training a model using either
CPU or GPU depending on whether the machine has a GPU available.

Example run and checking the resource usage both for the data loading and model
training steps:

```sh
python 3-gbm.py --environment=pypi run
python 3-gbm.py card view start
python 3-gbm.py card view train_model
```
