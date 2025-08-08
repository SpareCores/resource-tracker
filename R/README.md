# Resource Tracker for R

This R package provides raw access to the `resource-tracker` Python module via
the `reticulate` R package along with a convenience `R6` wrapper for the
`ResourceTracker` class with the most common methods, such as starting and
stopping the tracker, collecting samples, and generating reports.

## Installation

This package requires Python to be installed along with the `resource-tracker`
Python module, which can be installed from R via:

```r
reticulate::py_install('resource-tracker')
```

Note that on MacOS and Windows, you also need to install `psutil` that's used
under the hood to collect metrics. On Linux, it's optional, and can rely on the
`/proc` filesystem when using a modern kernel. For more details, see the
[installation instructions for the Python package](/#installation).

Once the Python dependencies are resolved, you can either install the R package
from CRAN:

```r
install.packages('resource.tracker')
```

Or the most recent (development version) from GitHub:

```r
remotes::install_github('SpareCores/resource-tracker', subdir = 'R')
```

## Getting started

Load the package and start the resource tracker:

```r
library(resource.tracker)
tracker <- ResourceTracker$new()
```

This now runs in the background, not blocking your R session.

Let's simulate some work for some seconds with the below, inefficient rolling
mean implementation:

```r
numbers <- 1:1e6
window <- 3
rollavg <- sapply(
  seq_len(length(numbers) - window + 1),
  function(i) mean(numbers[i:(i + window - 1)]))
```

It's time to check on the aggregated statistics of the resources used:

```r
tracker$stats()
# List of 9
#  $ process_cpu_usage        :List of 2
#   ..$ mean: num 1.12
#   ..$ max : num 1.14
#  $ process_memory           :List of 2
#   ..$ mean: num 728783
#   ..$ max : num 798130
#  $ process_gpu_usage        :List of 2
#   ..$ mean: num 0
#   ..$ max : num 0
#  $ process_gpu_vram         :List of 2
#   ..$ mean: num 0
#   ..$ max : num 0
#  $ process_gpu_utilized     :List of 2
#   ..$ mean: num 0
#   ..$ max : num 0
#  $ system_disk_space_used_gb:List of 1
#   ..$ max: num 2560
#  $ system_net_recv_bytes    :List of 1
#   ..$ sum: num 1840217
#  $ system_net_sent_bytes    :List of 1
#   ..$ sum: num 1843725
#  $ timestamp                :List of 1
#   ..$ duration: num 7

```

Or get recommendations on hardware requirements for the next run:

```r
tracker$recommend_resources()
# List of 4
#  $ cpu   : int 1
#  $ memory: int 1024
#  $ gpu   : int 0
#  $ vram  : int 0

tracker$recommend_server()
# List of 50
#  $ vendor_id            : chr "upcloud"
#  $ server_id            : chr "DEV-1xCPU-1GB-10GB"
#  $ description          : chr "Developer 1 vCPUs, 1 GB RAM"
#  $ family               : chr "Developer"
#  $ vcpus                : int 1
#  $ hypervisor           : chr "KVM"
#  $ cpu_allocation       : chr "Shared"
#  $ cpu_cores            : int 1
#  $ cpu_architecture     : chr "x86_64"
#  $ cpu_manufacturer     : chr "AMD"
#  $ cpu_family           : chr "EPYC"
#  $ cpu_model            : chr "7542"
#  $ cpu_l1_cache         : int 131072
#  $ cpu_l2_cache         : int 524288
#  $ cpu_l3_cache         : int 16777216
#  $ cpu_flags            : chr [1:88] "fpu" "vme" "de" "pse" ...
#  $ memory_amount        : int 1024
#  $ storage_size         : int 10
#  $ inbound_traffic      : num 0
#  $ outbound_traffic     : num 1024
#  $ ipv4                 : int 1
#  $ price                : num 0.0052
#  ...
```

Or look at the collected samples:

```r
tracker$system_metrics
# 'data.frame':   7 obs. of  21 variables:
#  $ timestamp          : POSIXct, format: "2025-08-08 00:02:28" "2025-08-08 00:02:29" ...
#  $ processes          : num  697 696 694 693 694 694 693
#  $ utime              : num  3.01 2.25 2.3 2.15 2.9 1.44 1.36
#  $ stime              : num  0.51 0.57 0.55 0.24 0.89 0.83 0.36
#  $ cpu_usage          : num  3.52 2.82 2.85 2.39 3.79 ...
#  $ memory_free        : num  8279604 8254872 8298804 8247688 8200296 ...
#  $ memory_used        : num  23920048 23946512 23901264 23951016 23993224 ...
#  $ memory_buffers     : num  2992 2992 2992 2992 2992 ...
#  $ memory_cached      : num  33344236 33342504 33343820 33345184 33350368 ...
#  $ memory_active      : num  47841676 47860856 47855900 47877072 47989240 ...
#  $ memory_inactive    : num  106028 106028 106028 106028 106028 ...
#  $ disk_read_bytes    : num  1138688 819200 24576 126976 36352000 ...
#  $ disk_write_bytes   : num  942080 0 8585216 61440 20480 ...
#  $ disk_space_total_gb: num  3700 3700 3700 3700 3700 ...
#  $ disk_space_used_gb : num  2560 2560 2560 2560 2560 ...
#  $ disk_space_free_gb : num  1140 1140 1140 1140 1140 ...
#  $ net_recv_bytes     : num  710628 1204 7685 4553 1094516 ...
#  $ net_sent_bytes     : num  710504 1463 7042 8261 1085653 ...
#  $ gpu_usage          : num  0.06 0.13 0.11 0.05 0.03 0.02 0.02
#  $ gpu_vram           : num  571 562 558 558 558 558 558
#  $ gpu_utilized       : num  1 1 1 1 1 1 1

tracker$process_metrics
# 'data.frame':   7 obs. of  12 variables:
#  $ timestamp   : POSIXct, format: "2025-08-08 00:02:28" "2025-08-08 00:02:29" ...
#  $ pid         : num  941247 941247 941247 941247 941247 ...
#  $ children    : num  4 4 4 4 4 4 4
#  $ utime       : num  1.01 1.02 1.01 1 0.99 1.04 1.01
#  $ stime       : num  0.1 0.12 0.07 0.13 0.14 0.09 0.09
#  $ cpu_usage   : num  1.11 1.14 1.08 1.13 1.13 1.13 1.1
#  $ memory      : num  646973 668091 680918 724281 798130 ...
#  $ read_bytes  : num  0 0 0 0 0 0 0
#  $ write_bytes : num  0 0 0 0 0 0 0
#  $ gpu_usage   : num  0 0 0 0 0 0 0
#  $ gpu_vram    : num  0 0 0 0 0 0 0
#  $ gpu_utilized: num  0 0 0 0 0 0 0

tracker$get_combined_metrics()
# 'data.frame':   7 obs. of  32 variables:
#  $ timestamp                 : POSIXct, format: "2025-08-08 00:02:28" "2025-08-08 00:02:29" ...
#  $ system_processes          : num  697 696 694 693 694 694 693
#  $ system_utime              : num  3.01 2.25 2.3 2.15 2.9 1.44 1.36
#  $ system_stime              : num  0.51 0.57 0.55 0.24 0.89 0.83 0.36
#  $ system_cpu_usage          : num  3.52 2.82 2.85 2.39 3.79 ...
#  $ system_memory_free        : num  8279604 8254872 8298804 8247688 8200296 ...
#  $ system_memory_used        : num  23920048 23946512 23901264 23951016 23993224 ...
#  $ system_memory_buffers     : num  2992 2992 2992 2992 2992 ...
#  $ system_memory_cached      : num  33344236 33342504 33343820 33345184 33350368 ...
#  $ system_memory_active      : num  47841676 47860856 47855900 47877072 47989240 ...
#  $ system_memory_inactive    : num  106028 106028 106028 106028 106028 ...
#  $ system_disk_read_bytes    : num  1138688 819200 24576 126976 36352000 ...
#  $ system_disk_write_bytes   : num  942080 0 8585216 61440 20480 ...
#  $ system_disk_space_total_gb: num  3700 3700 3700 3700 3700 ...
#  $ system_disk_space_used_gb : num  2560 2560 2560 2560 2560 ...
#  $ system_disk_space_free_gb : num  1140 1140 1140 1140 1140 ...
#  $ system_net_recv_bytes     : num  710628 1204 7685 4553 1094516 ...
#  $ system_net_sent_bytes     : num  710504 1463 7042 8261 1085653 ...
#  $ system_gpu_usage          : num  0.06 0.13 0.11 0.05 0.03 0.02 0.02
#  $ system_gpu_vram           : num  571 562 558 558 558 558 558
#  $ system_gpu_utilized       : num  1 1 1 1 1 1 1
#  $ process_pid               : num  941247 941247 941247 941247 941247 ...
#  $ process_children          : num  4 4 4 4 4 4 4
#  $ process_utime             : num  1.01 1.02 1.01 1 0.99 1.04 1.01
#  $ process_stime             : num  0.1 0.12 0.07 0.13 0.14 0.09 0.09
#  $ process_cpu_usage         : num  1.11 1.14 1.08 1.13 1.13 1.13 1.1
#  $ process_memory            : num  646973 668091 680918 724281 798130 ...
#  $ process_read_bytes        : num  0 0 0 0 0 0 0
#  $ process_write_bytes       : num  0 0 0 0 0 0 0
#  $ process_gpu_usage         : num  0 0 0 0 0 0 0
#  $ process_gpu_vram          : num  0 0 0 0 0 0 0
#  $ process_gpu_utilized      : num  0 0 0 0 0 0 0
```

Note that the `system_metrics` and `process_metrics` are properties of the
`ResourceTracker` object, while `get_combined_metrics` is a method that takes
optional parameters (e.g. to render more human-friendly names or return all
values in bytes) and returns a `data.frame`.

And finally, let's generate a report and open it in your browser:

```r
report <- tracker$report()
report$browse()
```

For an example HTML report, see <a href="https://sparecores.com/assets/slides/example-resource-tracker-report-in-metaflow.html" target="_blank">this Metaflow card</a>.

## Advanced usage

Not all features are exposed via the `ResourceTracker` class. For example, you
could snapshot a `ResourceTracker` object to a string or compressed file and
later restore it. To access these features, open a GitHub issue or you could use
the Python API directly via the `resource.tracker::resource_tracker` Python
module reference.
