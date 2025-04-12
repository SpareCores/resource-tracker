# Resource Tracking examples

This folder includes example scripts demonstrating the use of the
`resource_tracker` Python package in general and the `track_resources` decorator
in Metaflow.

## Standalone

The `resource_tracker` package provides the following classes that can be used to track
resources of a running process (and its children) or system-wide resources.

* `PidTracker`: Track resources of a running process and its children.
* `SystemTracker`: Track system-wide resources.

### benchmark.py

This script compares the performance of the `procfs` and `psutil` implementations
of the `get_pid_stats` function.

Example run:

```sh
python benchmark.py --pid `pgrep -f "chrome" | head -2 | tail -1`
```

## Metaflow

### 1-minimal.py

This script demonstrates the use of the `track_resources` decorator on a single
step, which burns CPU on a single core for a bit, and also reserves 500 MB of
memory.

Example run:

```sh
cd examples/metaflow
python 1-minimal.py run
```

Once the script finished, you can visualize the resource usage by checking the
Metaflow UI, or search for the generated HTML in your local enviromment, e.g.:

```sh
python 1-minimal.py card view do_heavy_computation
```

To load the collected data in Python, you can access the artifact of the step:

```python
from metaflow import Flow

Flow("MinimalFlow").latest_run.data.resource_tracker_data
```

This latter is a dictionary of `TinyDataFrame` objects, which are a thin wrapper
around a dictionary of column vectors. To get a quick overview of the data, you
can use the `print` method, printing the first 10 rows in a human-readable table:

```python
df = Flow("MinimalFlow").latest_run.data.resource_tracker_data["pid_tracker"]
print(df)
```

The `1-minimal-failed.py` script is a variation of the previous example that
raises an error right before finishing the step. This is to demonstrate that the
resource tracking and related card generation still works even if an error occurs
in the step.

### 2-multi-cpu.py

This script extends the previous example by running the same step on 6 cores.

Example run:

```sh
cd examples/metaflow
python 2-multi-cpu.py run
```

### 3-gpu.py

This script runs two math operations on the GPU for a few seconds.

Example run:

```sh
python 3-gpu.py --environment=pypi run
python 3-gpu.py card view do_heavy_computation
```

### 4-gbm.py

This script implements a more realistic example of a machine learning pipeline
using XGBoost, by downloading training data then training a model using either
CPU or GPU depending on whether the machine has a GPU available.

Example run and checking the resource usage both for the data loading and model
training steps:

```sh
python 4-gbm.py --environment=pypi run
python 4-gbm.py card view start
python 4-gbm.py card view train_model
```
