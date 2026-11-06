# YANG-to-Redis Translation in SONiC

## The Translation Problem

gNMI and RESTCONF clients send requests using **YANG paths**. Internally, SONiC stores everything in **Redis tables**. Something has to translate between the two.

SONiC accepts two styles of YANG path. The first uses **OpenConfig models** — vendor-neutral, standardized paths:

```text
/openconfig-interfaces:interfaces/interface[name=Ethernet0]/config/mtu  →  9100
```

The second uses **native `sonic-*` models** — paths that mirror the Redis schema directly:

```text
/sonic-port:sonic-port/PORT/PORT_LIST[name=Ethernet0]/mtu  →  9100
```

Both represent the same data, but CONFIG_DB stores it as:

```text
PORT|Ethernet0  →  { "mtu": "9100" }
```

For **OpenConfig paths**, the translation is significant — different hierarchy, different key format, sometimes different field names. Translib uses **annotation files** and **transformers** to bridge the gap. For **native `sonic-*` paths**, the model structure already mirrors Redis, so Translib passes the data through with minimal conversion.

The sections below explain how this translation works — primarily for OpenConfig paths, since that is where the heavy lifting happens — along with the models involved, their versioning, and how to extend them.

## What Gets Translated

When an OpenConfig path arrives, three aspects may need translation:

| Aspect           | OpenConfig side | Redis side |
| ---------------- | --------------- | ---------- |
| **Path → Table** | `/openconfig-acl:acl/acl-sets/acl-set[name=MyACL][type=ACL_IPV4]` | `ACL_TABLE\|MyACL` |
| **Field names**  | `description` | `policy_desc` |
| **Field values** | `ACL_IPV4` (enum) | `L3` (string) |

Some mappings are simple renames. Others require logic — for example, an OpenConfig interface path must resolve which Redis table to use (`PORT`, `PORTCHANNEL`, `VLAN`, or `LOOPBACK`) based on the interface name prefix.

## OpenConfig and gNSI Models

SONiC ships 17 vendor-neutral OpenConfig and gNSI models. These define the standardized YANG paths that gNMI and RESTCONF clients can use when they choose the OpenConfig path style.

| Model | Area |
| ----- | ---- |
| `openconfig-interfaces` | Interface configuration and state |
| `openconfig-if-ethernet` | Ethernet-specific interface parameters |
| `openconfig-if-ip` | IPv4 / IPv6 interface addressing |
| `openconfig-acl` | Access control lists and rules |
| `openconfig-lacp` | Link Aggregation Control Protocol |
| `openconfig-lldp` | Link Layer Discovery Protocol |
| `openconfig-p4rt` | P4Runtime programmable forwarding pipeline |
| `openconfig-platform` | Hardware platform and component inventory |
| `openconfig-platform-boot-loader` | Boot loader version and management |
| `openconfig-platform-transceiver` | Optical transceiver monitoring |
| `openconfig-sampling-sflow` | sFlow sampling configuration |
| `openconfig-system` | Hostname, NTP, AAA, DNS, logging, CPU/memory |
| `ietf-yang-library` | YANG module set capability reporting (RFC 7895) |
| `gnsi-authz` | gRPC-level authorization policies |
| `gnsi-certz` | Certificate management |
| `gnsi-credentialz` | Credential rotation and management |
| `gnsi-pathz` | Path-level access control |

These top-level models import 52 shared dependency modules from the `common/` directory (IETF base types, OpenConfig submodules for platform components, type libraries).

## OpenConfig Model Mapping

Most network-related OpenConfig models are backed entirely by Redis. Translib translates the YANG path into the appropriate Redis keys and queries the corresponding database tables.

- **openconfig-interfaces**: Interface configuration is stored in `CONFIG_DB`; operational state (admin/oper status) is read from `APPL_DB`; aggregation (LAG) state comes from `STATE_DB`; counters come from `COUNTERS_DB`.
- **openconfig-acl**: ACL definitions and rules are mapped to `ACL_TABLE` and `ACL_RULE` in `CONFIG_DB`.
- **openconfig-lldp**: Neighbor information is read from LLDP tables populated by the `lldp` container (primarily `APPL_DB` / `STATE_DB`).
- **openconfig-mclag** *(SONiC-defined extension, not an official OpenConfig model)*: Configuration (domain, peer-link, keepalive) is stored in `CONFIG_DB`; operational state (oper-status, role) is read from `STATE_DB`.

### The `openconfig-system` Exception

Most OpenConfig models are backed entirely by Redis, but `openconfig-system` is a hybrid. Configuration and structured operational state (hostname, NTP, AAA, management interface parameters) are stored in Redis and exposed through standard Translib mappings. However, certain elements — CPU utilization, memory usage, filesystem statistics — correspond to native OS metrics that do not originate in Redis. When these paths are requested, Translib invokes specialized backend handlers that query the Linux system directly, reading from kernel-provided files such as `/proc/stat` and `/proc/meminfo`.

## Annotation Files

Because OpenConfig paths and Redis tables have different structures, SONiC uses **annotation files** (`*-annot.yang`) to define the mapping rules. These files only exist for OpenConfig models — native `sonic-*` paths do not need them because their structure already mirrors Redis.

Each annotation file uses YANG `deviation` statements to attach SONiC-specific extensions to the corresponding OpenConfig model elements. Here is a simplified example from the ACL annotation file:

```yang
deviation /oc-acl:acl/oc-acl:acl-sets/oc-acl:acl-set {
    deviate add {
        sonic-ext:table-name "ACL_TABLE";
        sonic-ext:key-transformer "acl_set_key_xfmr";
    }
}

deviation /oc-acl:acl/oc-acl:acl-sets/oc-acl:acl-set/oc-acl:config/oc-acl:description {
    deviate add {
        sonic-ext:field-name "policy_desc";
    }
}
```

The first deviation tells Translib that the OpenConfig `acl-set` list maps to the Redis `ACL_TABLE`, with a custom Go function (`acl_set_key_xfmr`) to translate the key. The second deviation renames the `description` field to `policy_desc`.

For straightforward one-to-one mappings, these declarative annotations are sufficient. For complex translations that require programmatic logic, Translib delegates to **transformers** — see [Transformers](#transformers) below.

The annotation files in the repository:

```text
openconfig-acl-annot.yang
openconfig-interfaces-annot.yang
openconfig-mclag-annot.yang
openconfig-platform-annot.yang
openconfig-sampling-sflow-annot.yang
openconfig-system-annot.yang
sonic-showtech-annot.yang
```

## SONiC Extension Definitions

The `sonic-ext:xxx` are custom YANG extensions defined in the [`sonic-extension`](https://github.com/sonic-net/sonic-mgmt-common/blob/master/models/yang/sonic/common/sonic-extension.yang) module. These extensions bridge standard YANG and SONiC's Redis architecture. For background on how YANG extensions work in general, see [Extension in YANG](05a_README_yang_syntax.md#extension-in-yang).

The extensions fall into two categories: **declarative mappings** that Translib resolves directly, and **transformer registrations** that point to Go functions for programmatic logic.

**Declarative mapping extensions:**

| Extension | Purpose | Example |
| --------- | ------- | ------- |
| `sonic-ext:table-name` | Maps a YANG list to a Redis table | `sonic-ext:table-name "ACL_TABLE"` |
| `sonic-ext:field-name` | Maps a YANG leaf to a Redis field name | `sonic-ext:field-name "policy_desc"` |
| `sonic-ext:db-name` | Specifies which Redis database to use | `sonic-ext:db-name "APPL_DB"` |
| `sonic-ext:key-delim` | Overrides the default `\|` key delimiter | `sonic-ext:key-delim ":"` |

**Transformer registration extensions:**

| Extension | Purpose | Example |
| --------- | ------- | ------- |
| `sonic-ext:key-transformer` | Registers Go code for key translation | `sonic-ext:key-transformer "acl_set_key_xfmr"` |
| `sonic-ext:field-transformer` | Registers Go code for field value translation | `sonic-ext:field-transformer "intf_mtu_xfmr"` |
| `sonic-ext:table-transformer` | Registers Go code for table selection | `sonic-ext:table-transformer "intf_table_xfmr"` |
| `sonic-ext:subtree-transformer` | Registers Go code for an entire subtree | `sonic-ext:subtree-transformer "intf_eth_port_config_xfmr"` |

By default, SONiC YANG models target CONFIG_DB with `|` as the key delimiter. The `db-name` extension overrides the target database, and `key-delim` overrides the delimiter. This allows a single YANG model to span multiple Redis databases — essential because SONiC distributes data across CONFIG_DB, STATE_DB, APPL_DB, and COUNTERS_DB.

> **Note:** The `sonic-extension` module also defines validation extensions (`sonic-ext:custom-validation`, `sonic-ext:dependent-on`) used in native `sonic-*.yang` models for CONFIG_DB enforcement. These are covered in [YANG Validation in SONiC](05c_README_yang_validation_sonic.md).

## Transformers

When a declarative mapping extension (such as `sonic-ext:field-name`) is not enough, the annotation file uses a transformer registration extension (such as `sonic-ext:field-transformer`) instead. This registers the name of a Go function that Translib calls at runtime to perform the translation programmatically.

Each transformer is a Go function registered by name using `XlateFuncBind()` during `init()`. For example, the interfaces transformer file registers over 30 functions:

```go
func init() {
    XlateFuncBind("intf_table_xfmr", intf_table_xfmr)
    XlateFuncBind("YangToDb_intf_mtu_xfmr", YangToDb_intf_mtu_xfmr)
    XlateFuncBind("DbToYang_intf_mtu_xfmr", DbToYang_intf_mtu_xfmr)
    // ...
}
```

Transformers are **bidirectional**. A `Set` request calls the `YangToDb` direction (YANG path → Redis key/value), while a `Get` request calls the `DbToYang` direction (Redis → YANG response). Translib's core entry points — `XlateToDb()` and `XlateFromDb()` — dispatch to the appropriate direction automatically.

There are four transformer types, from most granular to broadest:

| Type | When to use | Example |
| ---- | ----------- | ------- |
| **Key transformer** | The YANG list key differs from the Redis table key | `acl_set_key_xfmr` — combines the ACL name and type fields into one Redis key |
| **Field transformer** | A single field needs value conversion | `intf_mtu_xfmr` — handles MTU default value on delete |
| **Table transformer** | The target Redis table depends on the data | `intf_table_xfmr` — selects `PORT`, `PORTCHANNEL`, `VLAN`, or `LOOPBACK` based on the interface name prefix |
| **Subtree transformer** | An entire YANG subtree maps to Redis in a non-trivial way | `intf_eth_port_config_xfmr` — handles the full Ethernet port config container as a unit |

At startup, Translib loads the annotation files, discovers which transformer name is attached to each YANG path, and looks up the corresponding Go function from the `XlateFuncBind` registry. The transformer source files live alongside the rest of the Translib code:

```text
src/sonic-mgmt-common/translib/transformer/
├── xfmr_intf.go        → Interface transformers (PORT, PORTCHANNEL, VLAN, LOOPBACK)
├── xfmr_mclag.go       → MCLAG transformers
├── xfmr_sflow.go       → sFlow transformers
├── xfmr_system.go      → System transformers (hostname, NTP, CPU/memory)
├── xfmr_platform.go    → Platform/hardware transformers
├── sw_vlan.go          → VLAN transformers
├── sw_portchannel.go   → PortChannel transformers
└── xfmr_showtech.go    → Show-tech transformers
```

## Source Location

The management framework models live in the [sonic-mgmt-common](https://github.com/sonic-net/sonic-mgmt-common) submodule:

```text
src/sonic-mgmt-common/models/yang/
├── *.yang           → 17 top-level models (OpenConfig, gNSI, IETF)
├── annotations/     → 7 annotation files (*-annot.yang)
├── common/          → 52 shared dependencies (IETF types, OpenConfig submodules)
├── extensions/      → 2 deviations + 1 SONiC-defined YANG extension (openconfig-mclag)
├── sonic/           → 4 SONiC-specific models (mgmt framework)
│   └── common/      → 2 shared definitions (sonic-extension, sonic-common)
└── version.xml      → Bundle version definition
```

## YANG Model Versioning

SONiC tracks the version of its YANG model bundle using the file [version.xml](https://github.com/sonic-net/sonic-mgmt-common/blob/master/models/yang/version.xml), which follows a `Major.Minor.Patch` versioning scheme.

**Major version** increases when changes are not backward compatible, such as deleting nodes, renaming elements, or modifying key attributes.

**Minor version** increases when backward-compatible API changes are introduced, such as adding new data nodes, expanding value ranges, or adding new enum/identity values.

**Patch version** increases for cosmetic changes that do not alter the API, such as description updates, backward-compatible validation refinements, or marking a node as deprecated.

This versioning system allows management systems to detect model changes and maintain compatibility with evolving APIs.

## Augmenting or Adding Northbound YANG Models

OpenConfig models are industry-standardized specifications maintained by the OpenConfig working group. However, SONiC allows vendors and developers to **augment existing OpenConfig models** (adding vendor-specific leaves or containers via YANG `augment` statements) or **define entirely new vendor-specific YANG models** under their own namespace. Both approaches expose new paths through gNMI and RESTCONF using the same translation pipeline:

- Write the `.yang` model (an augmentation of an existing model, or a new vendor-specific model).
- Create an accompanying `-annot.yang` annotation file describing how fields map to Redis.
- Implement a transformer in Go that handles the YANG-to-Redis translation for the new paths. Without a registered transformer, the new paths will return empty data even if the YANG model and Redis tables both exist.
- Integrate the model into the SONiC build so the gNMI service recognizes the new paths.

This mechanism enables developers to expose custom telemetry metrics or configuration parameters through the same standardized gNMI interface.
