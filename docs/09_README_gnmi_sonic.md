
# gNMI in SONiC: Architecture and Implementation

This document builds on the concepts covered in the [gNMI guide](./08_README_gnmi.md). The gNMI specification defines the protocol, transport mechanism (gRPC over HTTP/2), and the set of RPC operations available to clients such as `Get`, `Set`, and `Subscribe`. However, the specification does not dictate how a network operating system must implement these operations internally. Each vendor or network operating system is responsible for implementing the server-side architecture that processes gNMI requests and retrieves or modifies the corresponding device data.

## Evolution of Management Interfaces in SONiC

Early versions of SONiC were primarily managed through the Linux shell or by directly modifying the underlying Redis configuration database (CONFIG_DB). While effective for manual configuration, these methods did not provide a standardized or programmatic management interface suitable for large-scale automation.

As SONiC adoption expanded into hyper-scale data centers, operators required standardized management interfaces capable of supporting telemetry streaming, structured configuration, and automation frameworks. This need led to the gradual introduction of a management architecture built around YANG models and modern APIs.

**Phase 1**: The Telemetry Container

The first step in this evolution was the introduction of the telemetry container. Its primary responsibility was to export operational statistics such as interface counters and hardware metrics to external telemetry collectors. At this stage, the functionality was limited to streaming read-only telemetry data, which is why the container was originally named telemetry.

**Phase 2**: Management Framework Introduction

As operational requirements grew, SONiC needed to support not only telemetry but also standardized configuration interfaces. This led to the development of the Management Framework, which introduced structured APIs based on YANG models. The framework enabled multiple management interfaces including REST APIs, modern CLI implementations, and gNMI to interact with the same underlying data models.

**Phase 3**: Modern Container Separation

In modern SONiC releases, the management architecture is separated into multiple containers to improve modularity, reliability, and scalability.

- `gnmi` container: Hosts the gRPC server that implements the full gNMI protocol, handling configuration updates (`Set`), state queries (`Get`), and telemetry streaming (`Subscribe`).

- `mgmt-framework` container: Provides REST-based management interfaces, primarily implementing RESTCONF over HTTPS. It also serves as the backend for the modern Klish CLI used in SONiC. This container does not run a gNMI server.

```text
admin@sonic:~$ docker ps

CONTAINER ID   IMAGE                                COMMAND                  CREATED      STATUS      PORTS    NAMES
ac44509f23a0   docker-snmp:latest                   "/usr/bin/docker-snm…"   2 days ago   Up 2 days            snmp
0750813c0cd7   docker-platform-monitor:latest       "/usr/bin/docker_ini…"   2 days ago   Up 2 days            pmon
1b028cd43318   docker-sonic-mgmt-framework:latest   "/usr/local/bin/supe…"   2 days ago   Up 2 days            mgmt-framework
23fe8bbac22a   docker-lldp:latest                   "/usr/bin/docker-lld…"   2 days ago   Up 2 days            lldp
7032bc63ca54   docker-sonic-gnmi:latest              "/usr/local/bin/supe…"   2 days ago   Up 2 days            gnmi
242694cfa411   docker-eventd:latest                  "/usr/local/bin/supe…"   2 days ago   Up 2 days            eventd
75a9a4f32543   docker-gbsyncd-vs:latest              "/usr/local/bin/supe…"   2 days ago   Up 2 days            gbsyncd
bd63fe1196a4   docker-fpm-frr:latest                 "/usr/bin/docker_ini…"   2 days ago   Up 2 days            bgp
b692bf92bdb3   docker-router-advertiser:latest       "/usr/bin/docker-ini…"   2 days ago   Up 2 days            radv
e15fd17c17e7   docker-syncd-vs:latest                "/usr/local/bin/supe…"   2 days ago   Up 2 days            syncd
2f1da17957bc   docker-teamd:latest                   "/usr/local/bin/supe…"   2 days ago   Up 2 days            teamd
1999ddccb9b1   docker-sysmgr:latest                  "/usr/local/bin/supe…"   2 days ago   Up 2 days            sysmgr
60c105b25f2d   docker-orchagent:latest               "/usr/bin/docker-ini…"   2 days ago   Up 2 days            swss
df25ca7083c4   docker-database:latest               "/usr/local/bin/dock…"   2 days ago   Up 2 days            database
```

Separating these interfaces ensures that heavy traffic on one interface such as large REST API workloads does not interfere with real-time telemetry streaming handled by the gNMI service.

## SONiC gNMI Architecture

Implementing gNMI in SONiC requires bridging two different architectural models. On the client side, gNMI requests follow OpenConfig YANG models, which represent device configuration and operational data as hierarchical data trees. Internally, however, SONiC stores its configuration and operational state in a centralized Redis database architecture. The component responsible for bridging these two models is `Translib`, a translation layer that sits between the gNMI server and the Redis databases.

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
└────────┬────────┘
         │
         ├── CVL validates CONFIG_DB writes
         │
         │ Reads/Writes
         ▼
┌─────────────────┐
│   Redis DBs     │  ← CONFIG_DB, STATE_DB, APPL_DB, COUNTERS_DB, etc.
└─────────────────┘
```

In parallel, the mgmt-framework container also uses `Translib` when handling RESTCONF requests. Because both gNMI and RESTCONF share the same translation layer, SONiC maintains consistent behavior across management interfaces.

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

## YANG Models in SONiC

Before examining how requests are processed, it is important to understand the YANG models that drive the translation between gNMI and SONiC's internal data representation. These models are stored in the [SONiC management repository](https://github.com/sonic-net/sonic-mgmt-common/tree/master/models/yang), organized into several categories.

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

### Annotation Files

Because SONiC stores configuration and state in Redis rather than directly in YANG structures, it uses annotation files (typically ending in `-annot.yang`) to provide declarative mappings between YANG elements and Redis tables, keys, and fields. For straightforward one-to-one mappings, these annotations are sufficient on their own. For complex translations that require programmatic logic, Translib delegates the work to custom transformer code, as described in the next section.

```text
openconfig-acl-annot.yang
openconfig-interfaces-annot.yang
```

## Request Processing and Data Flow

When a gNMI client sends a request to a SONiC device, the request follows a structured processing pipeline through the components introduced above.

### Client Request

A management system sends a gNMI RPC such as `Get`, `Set`, or `Subscribe` to the SONiC switch over gRPC.

### gnmi Container

The request is received by the gRPC server running inside the `gnmi` container, which dispatches it to Translib for processing.

### Translib (Translation Layer)

Translib is the core translation component of the SONiC management architecture, implemented primarily in Go. It performs several critical functions:

- Translating OpenConfig YANG paths into SONiC Redis table and key structures
- Validating requests against YANG models and enforcing schema constraints
- Processing configuration changes and operational queries
- Supporting subscription logic for telemetry streaming
- Providing a common API shared by both the gNMI and RESTCONF management interfaces

The source code is available in the [SONiC repository](https://github.com/sonic-net/sonic-mgmt-common/tree/master/translib).

The translation between YANG paths and Redis operations is handled by **transformers**. A transformer is a Go module registered within Translib that defines how a specific YANG path maps to a Redis database, table, key, and field. For simple mappings, the default transformer uses the annotation files described earlier. For complex cases, developers write custom transformer code that implements the translation logic programmatically.

When a gNMI request arrives, Translib looks up the matching transformer based on the requested YANG path and delegates the Redis interaction to it.

Transformers are a critical implementation requirement. If a YANG model is added to SONiC but no corresponding transformer is registered, Translib will not return an error. Instead, it will return empty data for `Get` operations or silently fail to process `Set` operations. This means that adding a new YANG model requires both the model definition and a working transformer before the path becomes functional through gNMI or RESTCONF.

### CVL (Config Validation Library)

Before any configuration change reaches CONFIG_DB, SONiC validates it using the **Config Validation Library** (CVL). CVL is a separate component from Translib that enforces YANG schema constraints specifically on CONFIG_DB writes. Whenever a `Set` operation modifies configuration data -- whether initiated through gNMI, the CLI, `config reload`, or any other mechanism -- CVL checks the proposed change against the corresponding YANG model.

CVL enforces constraints such as mandatory fields, valid value ranges, `must` expressions, and `leafref` foreign-key relationships. If a proposed configuration change violates any constraint, CVL rejects the write before it reaches CONFIG_DB. This ensures that only schema-compliant configuration data is stored in Redis, regardless of which management interface initiated the change.

### Redis Database Access

After translating the request, Translib interacts with SONiC's centralized Redis database infrastructure. SONiC uses multiple Redis databases, each dedicated to a specific category of information.

- **CONFIG_DB**: Stores persistent configuration data. All configuration changes made through gNMI `Set` operations are written to this database.

- **STATE_DB**: Contains operational state information such as BGP neighbor status, hardware health indicators, temperature sensors, fan status, and other runtime metrics.

- **COUNTERS_DB**: Maintains hardware and interface counters including packet statistics, byte counters, drops, errors, queue metrics, and buffer watermarks.

- **APPL_DB**: Stores dynamic state managed by SONiC control-plane services, including routing table updates, MAC learning events, and other application-level data.

### Response to Client

Once the requested data is retrieved or updated, Translib converts the Redis representation back into a YANG-compliant structure. The result is then serialized and returned to the client through the gNMI server.


## OpenConfig Model Mapping

Most network-related OpenConfig models are backed entirely by Redis. Translib uses transformers to translate the YANG path into the appropriate Redis keys and query the corresponding database tables.

- **openconfig-interfaces**: Interface configuration and state come from `APPL_DB` / `STATE_DB`; interface counters come from `COUNTERS_DB`.
- **openconfig-acl**: ACL definitions and rules are mapped to ACL tables in `CONFIG_DB` / `APPL_DB` via transformers.
- **openconfig-lldp**: Neighbor information is read from LLDP tables populated by the `lldp` container (primarily in `APPL_DB` / `STATE_DB`).
- **openconfig-mclag**: Multi-chassis LAG configuration and state are served from `STATE_DB` (and related Redis tables) via transformers.

### The `openconfig-system` Exception

The `openconfig-system` model uses a hybrid data retrieval approach. Some portions behave like other OpenConfig modules: configuration and structured operational state (such as hostname, NTP configuration, AAA settings, and management interface parameters) are stored in Redis and exposed through Translib mappings.

However, certain elements correspond to native operating system metrics that do not originate in Redis. Examples include CPU utilization, memory usage, and filesystem statistics. When these paths are requested, Translib invokes specialized backend handlers that query the underlying Linux system directly, typically reading from kernel-provided files such as `/proc/stat` and `/proc/meminfo`.

## YANG Model Versioning

SONiC tracks the version of its YANG model bundle using the file [version.xml](https://github.com/sonic-net/sonic-mgmt-common/blob/master/models/yang/version.xml), which follows a `Major.Minor.Patch` versioning scheme.

**Major version** increases when changes are not backward compatible, such as deleting nodes, renaming elements, or modifying key attributes.

**Minor version** increases when backward-compatible API changes are introduced, such as adding new data nodes or modules.

**Patch version** increases for cosmetic changes that do not alter the API, such as documentation updates or expanded value ranges.

This versioning system allows management systems to detect model changes and maintain compatibility with evolving APIs.

## Defining Custom YANG Models

SONiC allows vendors and developers to define custom YANG models. Adding a new model requires several steps:

- Write the custom `.yang` model.
- Create an accompanying `-annot.yang` annotation file describing how fields map to Redis.
- Implement a transformer in Go that handles the YANG-to-Redis translation for the new paths. Without a registered transformer, the new paths will return empty data even if the YANG model and Redis tables both exist.
- Integrate the model into the SONiC build so the gNMI service recognizes the new paths.

This mechanism enables developers to expose custom telemetry metrics or configuration parameters through the same standardized gNMI interface.
