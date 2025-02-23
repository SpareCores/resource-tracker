from functools import wraps
from os import getpid


class track_resources:
    """Track resources used in a step."""

    def __call__(self, step_fn):
        @wraps(step_fn)
        def step_wrapper(step_obj):
            print(f"Tracking resources in {getpid()}")
            step_result = step_fn(step_obj)
            print(f"Resources tracked in {getpid()}")
            return step_result

        return step_wrapper
