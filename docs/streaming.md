The `resource-tracker` Python package supports streaming resource usage data to
a remote location for central analysis, visualization, and future resource
allocation recommendations.

This can be used either directly from a standalone `ResourceTracker` instance,
or through one of the framework integrations supported by the package.

## Implementation Details

When streaming is enabled, `resource-tracker` performs the following steps in
the background automatically:

- At the start of the `ResourceTracker` instance, it sends a request to the
  configured streaming API to

    - Register the start of the workload run along with its optional metadata,
      such as host and cloud environment information, project/job/step name,
      etc.
    - Receive an object storage URI prefix and temporary credentials to upload
      batched resource usage data to the target object storage.

- It uploads resource usage data in batches, by default every 60 seconds.
- It also takes care of renewing the temporary credentials when needed.
- When the `ResourceTracker` instance is stopped, it sends a request to the
  streaming API to register the finish and exit code of the workload run.

## Data Collected

Information collected and shared with the configured streaming target includes:

- Basic hardware information (number of vCPUs, amount of memory, number of
  GPUs and VRAM amounts) of the host machine.
- When the cloud provider's metadata server endpoint is enabled and reachable
  from the host machine, and also supported by the `resource-tracker` package
  (e.g. AWS, GCP, Azure, UpCloud, Hetzner Cloud etc.), cloud environment
  information (cloud provider, region, instance type) is automatically detected.
- Resource usage data (CPU, memory, GPU, network, disk etc) is sampled at the
  configured interval, accompanied by the microsecond-precision measurement
  timestamps.
- Status (failure vs success) and actual exit code of the workload run.

No personally identifiable information (PII) is shared explicitly with the
configured target by default, but the user can opt-in to share additional
metadata, such as project/job/step name, hostname, instance id or serial number
of a physical machine, IP address etc.

That said, because the streaming mechanism relies on HTTP requests, the
receiving party will still see request-level network metadata and might log it
for security or auditing purposes, such as the source IP address of the machine
or its internet gateway, independently from the resource usage data itself.

## Targets

The streaming implementation is based on a thin API layer for

- authenticating the `resource-tracker` client,
- serving temporary and scoped credentials to upload resource usage data to a
  central object storage without further interaction with the API server,
- registering the workload metadata and its final status (success or failure) in
  a distributed and scalable database.

### Spare Cores Sentinel

The maintainers of the `resource-tracker` Python package operate the Spare Cores
Sentinel service, which is available at
[sentinel.sparecores.com](https://sentinel.sparecores.com) at no cost for
individual users. Shared team access is currently in closed beta, and we are
actively looking for early adopters and feedback -- please get in touch!

To get started, visit the website to register a free account, generate an API
key, and opt-in to the streaming feature by setting the `SENTINEL_API_KEY`
environment variable.

### Custom Targets

If you are unhappy with the Spare Cores Sentinel approach, you can provide your
own, similar API endpoint and rely on the existing `resource-tracker` mechanism
to stream the resource usage data to your own infrastructure.
