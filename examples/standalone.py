from time import sleep

from resource_tracker import ResourceTracker

# both process-level and system-wide trackers will start automatically in the background by default
tracker = ResourceTracker()

# there is no collected data so far
tracker.process_metrics

# retry after a bit and see not much usage yet
sleep(1)
tracker.process_metrics

# reserve some memory and run a compute-heavy task
big_array = bytearray(500 * 1024 * 1024)  # 500 MB
total = 0
for i in range(int(1e7)):
    total += i**3
# memory and CPU usage should be increased at the process level
tracker.process_metrics.tail(1)
# check on the system-wide usage as well
tracker.system_metrics

# clean up
del big_array
tracker.stop()

# review collected data again
tracker.process_metrics
tracker.system_metrics

# average CPU usage
sum(tracker.process_metrics["utime"]) / len(tracker.process_metrics["utime"])
# peak memory usage in MiB
max(tracker.process_metrics["memory"]) / 1024
