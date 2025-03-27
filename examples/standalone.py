from time import sleep

from resource_tracker import ResourceTracker

# both process-level and system-wide trackers will start automatically in the background by default
tracker = ResourceTracker()

# there is no collected data so far
tracker.pid_tracker

# retry after a bit and see not much usage yet
sleep(1)
tracker.pid_tracker

# reserve some memory and run a compute-heavy task
big_array = bytearray(500 * 1024 * 1024)  # 500 MB
total = 0
for i in range(int(1e7)):
    total += i**3
# memory and CPU usage should be increased at the process level
tracker.pid_tracker.tail(1)
# check on the system-wide usage as well
tracker.system_tracker

# clean up
del big_array
tracker.stop()

# review collected data again
tracker.pid_tracker
tracker.system_tracker

# average CPU usage
sum(tracker.pid_tracker["utime"]) / len(tracker.pid_tracker["utime"])
# peak memory usage in MiB
max(tracker.pid_tracker["memory"]) / 1024
