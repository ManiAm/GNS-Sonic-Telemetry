
# gNMI in SONiC: Architecture and Implementation

The gNMI specification defines the protocol, transport mechanism (gRPC over HTTP/2), and the set of RPC operations available to clients such as `Get`, `Set`, and `Subscribe`. However, the specification does not dictate how a network operating system must implement these operations internally. Each vendor or network operating system is responsible for implementing the server-side architecture that processes gNMI requests and retrieves or modifies the corresponding device data.

In SONiC, implementing gNMI requires bridging two different architectural models. On the client side, gNMI requests follow OpenConfig YANG models, which represent device configuration and operational data as hierarchical data trees. Internally, however, SONiC stores its configuration and operational state in a centralized Redis database architecture. As a result, SONiC must translate between the hierarchical YANG data model used by gNMI clients and the table-based Redis schema used internally. This translation layer is implemented through `Translib`, which converts YANG-based requests into operations on SONiC’s Redis databases.

## Evolution of Management Interfaces in SONiC

Early versions of SONiC were primarily managed through the Linux shell or by directly modifying the underlying Redis configuration database (CONFIG_DB). While effective for manual configuration, these methods did not provide a standardized or programmatic management interface suitable for large-scale automation.

As SONiC adoption expanded into hyper-scale data centers, operators required standardized management interfaces capable of supporting telemetry streaming, structured configuration, and automation frameworks. This need led to the gradual introduction of a management architecture built around YANG models and modern APIs.

**Phase 1**: The Telemetry Container

The first step in this evolution was the introduction of the telemetry container. Its primary responsibility was to export operational statistics such as interface counters and hardware metrics to external telemetry collectors. At this stage, the functionality was limited to streaming read-only telemetry data, which is why the container was originally named telemetry.

**Phase 2**: Management Framework Introduction

As operational requirements grew, SONiC needed to support not only telemetry but also standardized configuration interfaces. This led to the development of the Management Framework, which introduced structured APIs based on YANG models. The framework enabled multiple management interfaces including REST APIs, modern CLI implementations, and gNMI to interact with the same underlying data models.

**Phase 3**: Modern Container Separation

In modern SONiC releases, the management architecture is separated into multiple containers to improve modularity, reliability, and scalability.

- `gnmi` container: This container hosts the gRPC server that implements the full gNMI protocol. It processes all gNMI operations, including configuration updates (Set), state queries (Get), and telemetry streaming (Subscribe). All gNMI traffic is handled exclusively by this container.

- `mgmt-framework` container: This container provides REST-based management interfaces, primarily implementing RESTCONF over HTTPS. It also serves as the backend for the modern Klish CLI used in SONiC. Unlike the `gnmi` container, it does not run a gNMI server.

```text
admin@sonic:~$ docker ps

CONTAINER ID   IMAGE                                COMMAND                  CREATED      STATUS      PORTS    NAMES
ac44509f23a0   docker-snmp:latest                   "/usr/bin/docker-snm…"   2 days ago   Up 2 days            snmp
0750813c0cd7   docker-platform-monitor:latest       "/usr/bin/docker_ini…"   2 days ago   Up 2 days            pmon
1b028cd43318   docker-sonic-mgmt-framework:latest   "/usr/local/bin/supe…"   2 days ago   Up 2 days            mgmt-framework
23fe8bbac22a   docker-lldp:latest                   "/usr/bin/docker-lld…"   2 days ago   Up 2 days            lldp
7032bc63ca54   docker-sonic-gnmi:latest             "/usr/local/bin/supe…"   2 days ago   Up 2 days            gnmi
242694cfa411   docker-eventd:latest                 "/usr/local/bin/supe…"   2 days ago   Up 2 days            eventd
75a9a4f32543   docker-gbsyncd-vs:latest             "/usr/local/bin/supe…"   2 days ago   Up 2 days            gbsyncd
bd63fe1196a4   docker-fpm-frr:latest                "/usr/bin/docker_ini…"   2 days ago   Up 2 days            bgp
b692bf92bdb3   docker-router-advertiser:latest      "/usr/bin/docker-ini…"   2 days ago   Up 2 days            radv
e15fd17c17e7   docker-syncd-vs:latest               "/usr/local/bin/supe…"   2 days ago   Up 2 days            syncd
2f1da17957bc   docker-teamd:latest                  "/usr/local/bin/supe…"   2 days ago   Up 2 days            teamd
1999ddccb9b1   docker-sysmgr:latest                 "/usr/local/bin/supe…"   2 days ago   Up 2 days            sysmgr
60c105b25f2d   docker-orchagent:latest              "/usr/bin/docker-ini…"   2 days ago   Up 2 days            swss
df25ca7083c4   docker-database:latest               "/usr/local/bin/dock…"   2 days ago   Up 2 days            database
```

Separating these interfaces ensures that heavy traffic on one interface such as large REST API workloads does not interfere with real-time telemetry streaming handled by the gNMI service.

## SONiC gNMI Architecture

The interaction between clients, containers, and internal data storage follows a layered architecture.

```text
┌─────────────┐
│   Client    │
└──────┬──────┘
       │ gNMI RPC (Get/Set/Subscribe)
       ▼
┌─────────────────┐
│  gnmi container │  ← gNMI/gRPC server
└────────┬────────┘
         │
         │ Uses TranslClient
         ▼
┌─────────────────┐
│    translib     │  ← Translation layer
│  (YANG ↔ Redis) │
└────────┬────────┘
         │
         │ Reads/Writes
         ▼
┌─────────────────┐
│   Redis DBs     │  ← CONFIG_DB, STATE_DB, APPL_DB, COUNTERS_DB, etc.
└─────────────────┘
```

In parallel, the mgmt-framework container also interacts with Translib when handling RESTCONF requests. Because both gNMI and RESTCONF use the same translation layer, SONiC maintains consistent behavior across different management interfaces.

```text
┌───────────────────────────┐
│ mgmt-framework container  │  ← RESTCONF server (REST API only)
└───────────┬───────────────┘
            │
            │ Also uses translib
            ▼
   ┌─────────────────┐
   │     translib    │
   └─────────────────┘
```

## Request Processing and Data Flow

When a gNMI client sends a request to a SONiC device, the request follows a structured processing pipeline.

### Client Request

A management system sends a gNMI Remote Procedure Call (RPC), such as `Get`, `Set`, or `Subscribe`, to the SONiC switch. The request is sent over gRPC, typically using a configurable port.

### gnmi container

The request is received by the gRPC server running inside the `gnmi` container. This container implements the gRPC server responsible for handling all gNMI operations.

### Translib (Translation Layer)

The gRPC server forwards the request to Translib, which is the core translation component of the SONiC management architecture. Translib performs several critical functions:

- Translating OpenConfig YANG paths into SONiC Redis table and key structures
- Validating requests against YANG models and enforcing schema constraints
- Processing configuration changes and operational queries
- Supporting subscription logic for telemetry streaming
- Providing a common API shared by both the gNMI and RESTCONF management interfaces

The Translib is implemented primarily in Go (Golang) and it is available in the [SONiC repository](https://github.com/sonic-net/sonic-mgmt-common/tree/master/translib).

### Redis Database Access

After translating the request, Translib interacts with SONiC’s centralized Redis database infrastructure. SONiC uses multiple Redis databases, each dedicated to a specific category of information.

- **CONFIG_DB**: Stores persistent configuration data. All configuration changes made through gNMI `Set` operations are written to this database.

- **STATE_DB**: Contains operational state information such as BGP neighbor status, hardware health indicators, temperature sensors, fan status, and other runtime metrics.

- **COUNTERS_DB**: Maintains hardware and interface counters including packet statistics, byte counters, drops, errors, queue metrics, and buffer watermarks.

- **APPL_DB**: Stores dynamic state managed by SONiC control-plane services, including routing table updates, MAC learning events, and other application-level data.

### Response to the Client

Once the requested data is retrieved or updated, Translib converts the Redis representation back into a YANG-compliant structure. The result is then serialized into either Protocol Buffers or JSON format and returned to the client through the gNMI server.

## The `openconfig-system` Model

SONiC stores most configuration and operational state in a set of Redis databases, including `CONFIG_DB`, `STATE_DB`, `APPL_DB`, and `COUNTERS_DB`. These databases act as the central data store for the system, allowing different containers and services within SONiC to exchange configuration and runtime information.

When a gNMI request reaches the gnmi container, the request is processed by the Translib translation layer. Translib interprets the requested YANG path and determines how the requested data should be retrieved (either from Redis or directly from the underlying Linux host).

Most network-related OpenConfig models are backed entirely by Redis. In these cases, Translib translates the YANG path into the appropriate Redis keys and queries the corresponding database tables.

- **openconfig-interfaces**: Interface configuration and state come from `APPL_DB` / `STATE_DB`; interface counters come from `COUNTERS_DB`.
- **openconfig-acl**: ACL definitions and rules are mapped to ACL tables in `CONFIG_DB` / `APPL_DB` via translib transformers.
- **openconfig-lldp**: Neighbor information is read from LLDP tables populated by the `lldp` container (primarily in `APPL_DB` / `STATE_DB`).
- **openconfig-mclag**: Multi‑chassis LAG configuration and state are served from `STATE_DB` (and related Redis tables) via translib.

The `openconfig-system` model differs slightly. It represents both device configuration and host-level system metrics:

Some portions of the model behave like other OpenConfig modules: configuration and structured operational state (such as hostname, NTP configuration, AAA settings, and management interface parameters) are stored in Redis and exposed through Translib mappings. These values are retrieved in the same way as other network configuration objects.

However, certain elements of the `openconfig-system` model correspond to native operating system metrics that do not originate in Redis. Examples include CPU utilization, memory usage, and filesystem statistics. When these paths are requested, Translib invokes specialized backend handlers that query the underlying Linux system directly. These handlers typically read from kernel-provided system files such as `/proc/stat` and `/proc/meminfo`, or from other host APIs that expose real-time resource utilization.

In practice, this means that the `openconfig-system` model uses a hybrid data retrieval approach. Configuration data and structured operational state generally flow through Redis, maintaining consistency with the rest of the SONiC architecture. In contrast, low-level host metrics bypass Redis and are obtained directly from the Linux operating system to provide accurate, real-time system information.

## YANG Models in SONiC

To enable translation between gNMI requests and SONiC’s internal data representation, SONiC relies on a collection of YANG models and mapping annotations. These models are stored in the [SONiC management repository](https://github.com/sonic-net/sonic-mgmt-common/tree/master/models/yang). The directory structure organizes models into several categories.

```text
yang/
├── annotations/     → Transformer annotations
├── common/          → Shared dependencies and submodules
├── extensions/      → YANG extensions
├── sonic/           → SONiC-specific models
├── testdata/        → Test models
└── version.xml      → Bundle version definition
```

### Standard OpenConfig Models

SONiC supports OpenConfig YANG models, which are vendor-neutral schemas used widely across the networking industry. These models define standardized paths and data structures that gNMI clients use when interacting with devices. Such files begin with the prefix `openconfig-`.

```text
openconfig-interfaces.yang
openconfig-platform.yang
openconfig-bgp.yang
```

### SONiC Native YANG Models

For SONiC-specific functionality that is not covered by existing OpenConfig models, the system defines native YANG modules within the `sonic/` directory. These models expose SONiC-specific configuration and operational data through the same YANG-based management framework.

```text
sonic-port.yang
sonic-acl.yang
sonic-interface.yang
```

### SONiC Annotation Files

Because SONiC stores configuration and state in Redis rather than directly in YANG structures, it uses annotation files (typically ending in `-annot.yang`). These files describe how individual YANG elements map to Redis tables and keys. Translib relies on these annotations to correctly translate requests between the YANG data model and the internal Redis schema.

```text
openconfig-acl-annot.yang
openconfig-interfaces-annot.yang
```

## YANG Model Versioning

SONiC tracks the version of its YANG model bundle using the file [version.xml](https://github.com/sonic-net/sonic-mgmt-common/blob/master/models/yang/version.xml), which follows a `Major.Minor.Patch` versioning scheme.

**Major version** increases when changes are not backward compatible, such as deleting nodes, renaming elements, or modifying key attributes.

**Minor version** increases when backward-compatible API changes are introduced, such as adding new data nodes or modules.

**Patch version** increases for cosmetic changes that do not alter the API, such as documentation updates or expanded value ranges.

This versioning system allows management systems to detect model changes and maintain compatibility with evolving APIs.

## Defining Custom YANG Models

OpenConfig allows vendors and developers to define custom YANG models. In SONiC, adding a new model requires several steps:

- Write the custom `.yang` model.
- Create an accompanying `-annot.yang` file describing how fields map to Redis.
- Integrate the model into the SONiC build so the gNMI service recognizes the new paths.

This mechanism enables developers to expose custom telemetry metrics or configuration parameters through the same standardized gNMI interface.
